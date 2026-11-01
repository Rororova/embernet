"""Static-obstacle routing from a drone's own incident version; no fleet or truth input."""

from dataclasses import dataclass
from heapq import heappop, heappush
from math import dist, inf


@dataclass(frozen=True)
class Box:
    name: str
    low: tuple
    high: tuple

    def inflated(self, margin):
        low = tuple(v - margin for v in self.low)
        high = (*(v + margin for v in self.high[:2]), self.high[2] + margin)
        return Box(self.name, low, high)


# Conservative boxes from triangle-level bounds of the authored assemblies; see context.
TOWER = Box("tower", (128.0, 133.0, 0.0), (172.0, 173.0, 108.0))
WEST_BLOCK = Box("west-block", (-5.0, 130.0, 0.0), (82.0, 192.0, 62.0))
NORTHWEST_BLOCK = Box("northwest-block", (-5.0, 190.0, 0.0), (82.0, 232.0, 28.0))
EAST_BLOCK = Box("east-block", (198.0, 134.0, 0.0), (245.0, 162.0, 50.0))
NORTHEAST_BLOCK = Box("northeast-block", (198.0, 164.0, 0.0), (245.0, 240.0, 35.0))
MID_BLOCK = Box("mid-block", (98.0, 134.0, 0.0), (128.0, 232.0, 18.0))
CITY_OBSTACLES = (TOWER, WEST_BLOCK, NORTHWEST_BLOCK, EAST_BLOCK, NORTHEAST_BLOCK, MID_BLOCK)
ROUTE_MARGIN = 7.0
ARRIVAL_RADIUS = 4.5


def segment_clear(start, end, boxes, margin=ROUTE_MARGIN):
    """Slab test of a 3D segment against inflated axis-aligned boxes."""
    for box in boxes:
        grown = box.inflated(margin) if margin else box
        t0, t1 = 0.0, 1.0
        for a, b, low, high in zip(start, end, grown.low, grown.high):
            span = b - a
            if abs(span) < 1e-9:
                if a < low or a > high:
                    break
                continue
            first, second = sorted(((low - a) / span, (high - a) / span))
            t0, t1 = max(t0, first), min(t1, second)
            if t0 > t1:
                break
        else:
            return False
    return True


def clearance(position, boxes):
    """Metres from a point to the nearest box surface."""
    best = inf
    for box in boxes:
        offset = [max(low - p, 0.0, p - high) for p, low, high in zip(position, box.low, box.high)]
        best = min(best, sum(v * v for v in offset) ** 0.5)
    return best


def route(start, goal, boxes=CITY_OBSTACLES, margin=ROUTE_MARGIN):
    """Next waypoint on a shortest path through corners of tall inflated boxes."""
    if segment_clear(start, goal, boxes, margin):
        return [tuple(goal)]
    altitude = max(start[2], goal[2])
    blocking = [b for b in boxes if b.high[2] + margin >= min(start[2], goal[2])]
    pad = margin + 1.0
    corners = [
        (x, y, altitude)
        for b in blocking
        for x in (b.low[0] - pad, b.high[0] + pad)
        for y in (b.low[1] - pad, b.high[1] + pad)
        if not any(
            o.low[0] - margin < x < o.high[0] + margin
            and o.low[1] - margin < y < o.high[1] + margin
            and o.low[2] <= altitude <= o.high[2] + margin
            for o in boxes
        )
    ]
    # Climbing in place is the fallback when the straight line only clips a roof.
    nodes = [tuple(start), (start[0], start[1], altitude), *corners, tuple(goal)]
    target = len(nodes) - 1
    distances, previous, queue = {0: 0.0}, {}, [(0.0, 0)]
    while queue:
        cost, node = heappop(queue)
        if node == target:
            break
        if cost > distances.get(node, inf):
            continue
        for other in range(len(nodes)):
            if other == node or not segment_clear(nodes[node], nodes[other], boxes, margin):
                continue
            total = cost + dist(nodes[node], nodes[other])
            if total < distances.get(other, inf):
                distances[other], previous[other] = total, node
                heappush(queue, (total, other))
    if target not in previous:
        return [tuple(start)]
    path, node = [], target
    while node != 0:
        path.append(nodes[node])
        node = previous[node]
    return path[::-1]


def standoff(position, slot, boxes=CITY_OBSTACLES, *, ring=20.0):
    """A per-slot hold from the drone's own incident estimate, outside every box."""
    x, y, z = position
    column = slot % 3 - 1
    row = slot // 3
    if z <= 25:
        # Ground incidents are worked from above their local building heights.
        hold = (x + column * 8.0, y - 6.0 - row * 8.0, max(z + 24.0, 34.0) + row * 3.0)
    else:
        # Elevated facade incidents are approached from the open south side.
        hold = (x + column * 10.0, y - ring - row * 8.0, z + 2.0 + slot * 1.5)
    # A clicked fire can sit on any roof; lift the hold clear of whatever is under it.
    lift = [
        box.high[2] + ROUTE_MARGIN + 2.0 + slot * 1.5
        for box in boxes
        if box.low[0] - ROUTE_MARGIN <= hold[0] <= box.high[0] + ROUTE_MARGIN
        and box.low[1] - ROUTE_MARGIN <= hold[1] <= box.high[1] + ROUTE_MARGIN
        and hold[2] <= box.high[2] + ROUTE_MARGIN
    ]
    return (hold[0], hold[1], max([hold[2], *lift]))

"""Burned-in observer layer. Markers are projected from measured poses, never animated."""

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).parent / "ui/fonts/Rajdhani-SemiBold.ttf"
WIDTH, HEIGHT = 960, 540
MAP_SIZE, MAP_MARGIN = 150, 10
INCIDENT_COLORS = {
    "cleared": "#7dff6b",
    "escalated": "#7dff6b",
    "deferred": "#ffb020",
    "assigned": "#ff4d3a",
    "confirmed": "#ff4d3a",
}


@lru_cache(maxsize=8)
def font(size):
    return ImageFont.truetype(str(FONT), size)


@lru_cache(maxsize=1024)
def stamp(text, color, size, outlined):
    """Rasterize a label once; FreeType outlines dominate frame cost when redrawn."""
    face = font(size)
    box = face.getbbox(text, stroke_width=2)
    width, height = max(1, box[2] - box[0] + 4), max(1, box[3] - box[1] + 4)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(image).text(
        (2 - box[0], 2 - box[1]), text, fill=color, font=face,
        stroke_width=2 if outlined else 0, stroke_fill="#000000",
    )
    return image


def put_text(image, position, text, color, size=14, outlined=True):
    label = stamp(text, color, size, outlined)
    image.paste(label, (int(position[0]), int(position[1])), label)


class Projector:
    """Pinhole model matching the render camera's focal length and aperture."""

    def __init__(self, eye, focus, up, focal=24.0, aperture=20.955, size=(WIDTH, HEIGHT)):
        self.eye = np.asarray(eye, float)
        forward = np.asarray(focus, float) - self.eye
        self.forward = forward / np.linalg.norm(forward)
        right = np.cross(self.forward, up)
        self.right = right / np.linalg.norm(right)
        self.up = np.cross(self.right, self.forward)
        self.scale = focal / aperture * size[0]
        self.size = size

    def __call__(self, point):
        offset = np.asarray(point, float) - self.eye
        depth = float(offset @ self.forward)
        if depth < 0.5:
            return None
        return (
            self.size[0] / 2 + self.scale * float(offset @ self.right) / depth,
            self.size[1] / 2 - self.scale * float(offset @ self.up) / depth,
            depth,
        )

    def ray(self, u, v):
        """Unit direction through a normalized image point; the inverse of __call__."""
        x = (u * self.size[0] - self.size[0] / 2) / self.scale
        y = (self.size[1] / 2 - v * self.size[1]) / self.scale
        direction = self.forward + self.right * x + self.up * y
        return direction / np.linalg.norm(direction)

    def visible(self, point, margin=0):
        result = self(point)
        return (
            result is not None
            and -margin <= result[0] <= self.size[0] + margin
            and -margin <= result[1] <= self.size[1] + margin
        )


def pick_point(projector, u, v, ground_at, boxes, size, margin=8.0, step=2.0, reach=1600.0):
    """First ground or building surface under a clicked pixel, or None outside the mission area."""
    direction = projector.ray(u, v)
    for distance in np.arange(step, reach, step):
        x, y, z = projector.eye + direction * distance
        ground = ground_at(x, y) if ground_at else 0.0
        hit = z <= ground + 1.0 or any(
            box.low[0] <= x <= box.high[0] and box.low[1] <= y <= box.high[1] and box.low[2] <= z <= box.high[2]
            for box in boxes
        )
        if hit:
            if not (margin <= x <= size - margin and margin <= y <= size - margin):
                return None
            return (float(x), float(y), float(max(z, ground + 1.0)))
    return None


def _map_point(position, world_size):
    scale = MAP_SIZE / world_size
    left, top = WIDTH - MAP_SIZE - MAP_MARGIN, HEIGHT - MAP_SIZE - MAP_MARGIN
    return left + position[0] * scale, top + MAP_SIZE - position[1] * scale


def draw_overlay(frame, projector, mission, positions, *, phase="", selected=None):
    """Return an annotated copy; the aircraft pixels underneath remain the render."""
    image = Image.fromarray(frame).convert("RGB")
    canvas = ImageDraw.Draw(image, "RGBA")
    fires = {fire.id: fire for fire in mission.world.fires.values()}
    drones = mission.drones_view()
    positions = {key: tuple(float(v) for v in value) for key, value in positions.items()}

    for row in mission.incidents_view():
        if row["status"] in ("cleared", "escalated"):
            continue
        at = projector(row["position"])
        color = INCIDENT_COLORS.get(row["status"], "#ffffff")
        if at and projector.visible(row["position"]):
            x, y = at[:2]
            canvas.polygon([(x, y - 9), (x + 9, y), (x, y + 9), (x - 9, y)], outline=color, width=2)
            kind = "SURVIVOR?" if row["kind"] == "person" else "FIRE"
            put_text(
                image,
                (x + 12, y - 16),
                f"{kind} {row['id']} {row['status']} · {len(row['committed'])} committed",
                color,
            )

    for index, row in enumerate(drones):
        position, color = positions[row["id"]], row["color"]
        at = projector(position)
        if at is None or not projector.visible(position, 30):
            continue
        x, y, depth = at
        goal = projector(row["goal"])
        if goal:
            canvas.line([(x, y), goal[:2]], fill=color + "90", width=1)
        if row["working"] in fires and projector(fires[row["working"]].position):
            target = projector(fires[row["working"]].position)
            canvas.line([(x, y), target[:2]], fill="#37c8ffd0", width=3)
        radius = max(9, min(24, 300 / depth))
        canvas.ellipse((x - radius, y - radius, x + radius, y + radius), outline=color, width=2)
        if selected == row["id"]:
            canvas.ellipse((x - radius - 4, y - radius - 4, x + radius + 4, y + radius + 4), outline="#ffffff", width=1)
        link = "" if row["connected"] else " · NO LINK"
        # Stagger labels so a tight formation stays readable.
        lift = 16 + 16 * (index % 3) if depth > 60 else 12
        canvas.line([(x, y - radius), (x + radius, y - radius - lift + 8)], fill=color, width=1)
        put_text(image, (x + radius + 2, y - radius - lift), f"{row['id']} {row['task']}{link}", color)

    # Top-down map: fleet positions against the same obstacle boxes used for routing.
    left, top = WIDTH - MAP_SIZE - MAP_MARGIN, HEIGHT - MAP_SIZE - MAP_MARGIN
    size = mission.c.size
    canvas.rectangle((left, top, left + MAP_SIZE, top + MAP_SIZE), fill="#061018c8", outline="#4a6470")
    for box in mission.obstacles:
        (a, b), (c, d) = _map_point(box.low, size), _map_point(box.high, size)
        canvas.rectangle((max(a, left), max(d, top), min(c, left + MAP_SIZE), min(b, top + MAP_SIZE)), fill="#2c3d47")
    for fire in fires.values():
        if fire.active:
            x, y = _map_point(fire.position, size)
            r = 2 + 5 * fire.fraction
            canvas.ellipse((x - r, y - r, x + r, y + r), fill="#ff4d3a")
    for row in drones:
        x, y = _map_point(positions[row["id"]], size)
        canvas.ellipse((x - 3, y - 3, x + 3, y + 3), fill=row["color"])

    rows = mission.log.rows
    headline = [r for r in rows if r["kind"] not in ("delivered", "knowledge", "commitment", "scenario")][-3:]
    canvas.rectangle((0, HEIGHT - 66, WIDTH - MAP_SIZE - 2 * MAP_MARGIN, HEIGHT), fill="#000000a8")
    for index, row in enumerate(headline):
        put_text(
            image,
            (10, HEIGHT - 62 + index * 20),
            f"{row['time']:6.1f}s  {row['drone']}  {row['text'][:88]}",
            "#f2f6f8",
            outlined=False,
        )
    canvas.rectangle((0, 0, 330, 26), fill="#000000a8")
    put_text(image, (8, 3), f"t={mission.time:6.1f}s  {phase}"[:52], "#ffffff", 17, False)
    put_text(image, (338, 5), "aircraft shells 3x scale · physics unscaled", "#ffffff")
    return np.asarray(image)

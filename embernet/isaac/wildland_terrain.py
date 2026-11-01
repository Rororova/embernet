"""Deterministic wildland terrain, ground masks and plant placement; no Kit or USD imports."""

from itertools import pairwise

import numpy as np

WILDLAND_SIZE = 800
HOME = (360.0, 300.0)
# The live mission flies a 240 m box; its origin sits here on the wildland map.
MISSION_ORIGIN = (278.0, 270.0)
MISSION_SIZE = 240.0
MISSION_RELIEF = 16.0
IGNITION = (428.0, 404.0)
PAD_RADIUS = 46.0
FIRE_ROAD = ((360.0, 300.0), (470.0, 420.0), (640.0, 470.0), (720.0, 620.0), (690.0, 840.0), (560.0, 1010.0))
RIDGE = ((-300.0, 1050.0), (1500.0, 620.0))
MEADOW = (340.0, 290.0, 92.0)

_rng = np.random.default_rng(2718)
_wavelengths = np.geomspace(1100.0, 14.0, 72)
_angles = _rng.uniform(0, 2 * np.pi, 72)
_phases = _rng.uniform(0, 2 * np.pi, 72)
_amplitudes = 0.018 * _wavelengths**0.95 * _rng.uniform(0.7, 1.3, 72)
_kx = 2 * np.pi * np.cos(_angles) / _wavelengths
_ky = 2 * np.pi * np.sin(_angles) / _wavelengths


def _smooth(edge0, edge1, value):
    t = np.clip((np.asarray(value, dtype=float) - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)


def _waves(x, y, first=0, last=72):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    total = np.zeros(np.broadcast(x, y).shape)
    for i in range(first, last):
        total += _amplitudes[i] * np.cos(_kx[i] * x + _ky[i] * y + _phases[i])
    return total


def _segment_distance(x, y, points):
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    best = np.full(np.broadcast(x, y).shape, np.inf)
    for (ax, ay), (bx, by) in pairwise(points):
        dx, dy = bx - ax, by - ay
        t = np.clip(((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy), 0, 1)
        best = np.minimum(best, np.hypot(x - ax - t * dx, y - ay - t * dy))
    return best


def road_distance(x, y):
    # A little meander keeps the graded road from reading as straight CAD segments.
    return _segment_distance(np.asarray(x) + 7 * np.sin(np.asarray(y) / 41), y, FIRE_ROAD)


def meadow_mask(x, y):
    cx, cy, radius = MEADOW
    edge = np.hypot(np.asarray(x) - cx, (np.asarray(y) - cy) * 1.25) + 0.9 * _waves(x, y, 30, 52)
    return 1 - _smooth(radius * 0.72, radius * 1.12, edge)


def burn_mask(x, y):
    """Blackened ground already behind the front; the head runs up-slope to the north-east."""
    dx, dy = np.asarray(x) - (IGNITION[0] + 14), np.asarray(y) - (IGNITION[1] + 12)
    u, v = (dx * 0.72 + dy * 0.69) / 62, (dy * 0.72 - dx * 0.69) / 46
    return 1 - _smooth(0.74, 1.08, np.hypot(u, v) + 0.012 * _waves(x, y, 28, 56))


def terrain_height(x, y):
    """Metres above the map datum at ENU x/y, usable for any array shape."""
    x, y = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    relief = _waves(x, y)
    broad = _waves(x, y, 0, 18)
    ridge = 88 * np.exp(-((_segment_distance(x, y, RIDGE) / 235) ** 2))
    creek = np.sin(x / 83) * 34 + 0.33 * x + 142 - y
    gully = -9 * np.exp(-((creek / 20) ** 2))
    radius = np.hypot(x - WILDLAND_SIZE / 2, y - WILDLAND_SIZE / 2)
    mountains = 190 * _smooth(520, 1500, radius) * (
        0.72 + 0.28 * np.sin(np.arctan2(y - WILDLAND_SIZE / 2, x - WILDLAND_SIZE / 2) * 5)
    )
    height = 40 + relief + ridge + gully + mountains
    calm = meadow_mask(x, y)
    height = height * (1 - calm) + (40 + broad * 0.7 + ridge + gully) * calm
    pad = 40 + float(_waves(HOME[0], HOME[1], 0, 18)) * 0.7 + float(
        88 * np.exp(-((_segment_distance(HOME[0], HOME[1], RIDGE) / 235) ** 2))
    )
    graded = 1 - _smooth(4.5, 13, road_distance(x, y))
    height = height * (1 - graded * 0.82) + (40 + broad + ridge) * graded * 0.82
    flat = 1 - _smooth(PAD_RADIUS, PAD_RADIUS * 2.4, np.hypot(x - HOME[0], y - HOME[1]))
    height = height * (1 - flat) + pad * flat
    # Flight lanes clear the canopy because relief is compressed under the mission box only.
    beyond = np.maximum(
        np.abs(x - MISSION_ORIGIN[0] - MISSION_SIZE / 2), np.abs(y - MISSION_ORIGIN[1] - MISSION_SIZE / 2)
    )
    inside = 1 - _smooth(MISSION_SIZE / 2 + 8, MISSION_SIZE / 2 + 170, beyond)
    calm = pad + MISSION_RELIEF * np.tanh((height - pad) / MISSION_RELIEF)
    return height * (1 - inside) + calm * inside


def mission_ground(x, y):
    """Ground height at live-mission coordinates, whose origin is the pad surface."""
    wx, wy = x + MISSION_ORIGIN[0], y + MISSION_ORIGIN[1]
    return float(terrain_height(wx, wy) - terrain_height(*HOME))


def terrain_normal(x, y, step=2.0):
    dx = (terrain_height(np.asarray(x) + step, y) - terrain_height(np.asarray(x) - step, y)) / (2 * step)
    dy = (terrain_height(x, np.asarray(y) + step) - terrain_height(x, np.asarray(y) - step)) / (2 * step)
    normal = np.stack([-dx, -dy, np.ones_like(dx)], axis=-1)
    return normal / np.linalg.norm(normal, axis=-1, keepdims=True)


def grid_axis():
    """2.5 m in the mission square, widening geometrically to a 1 km visual horizon."""
    inner = np.arange(0, WILDLAND_SIZE + 2.5, 2.5)
    spacing = 2.5 * 1.09 ** np.arange(1, 42)
    outward = np.cumsum(spacing)
    return np.concatenate([-outward[::-1], inner, WILDLAND_SIZE + outward])


def ground_masks(size=2048):
    """RGBA layer weights over the mission square: grass, rocky soil, road dirt, char."""
    axis = (np.arange(size) + 0.5) / size * WILDLAND_SIZE
    x, y = np.meshgrid(axis, axis)
    masks = np.zeros((size, size, 4), dtype=np.float32)
    for row in range(0, size, 256):
        px, py = x[row : row + 256], y[row : row + 256]
        slope = np.sqrt(np.maximum(terrain_normal(px, py)[..., 2] ** -2 - 1, 0))
        speckle = _waves(px, py, 44, 72)
        grass = np.maximum(meadow_mask(px, py), 0.2 * _smooth(0.4, 3.2, _waves(px, py, 34, 58)))
        rock = _smooth(0.5, 0.95, slope + 0.02 * speckle)
        road = 1 - _smooth(3.4, 6.5, road_distance(px, py) + 0.35 * speckle)
        char = burn_mask(px, py)
        masks[row : row + 256] = np.stack(
            [grass * (1 - rock) * (1 - road), rock, road, char], axis=-1
        )
    return masks


def forest_density(x, y):
    """0–1 relative tree density; open meadow, road corridors and bare slopes stay thin."""
    slope = np.sqrt(np.maximum(terrain_normal(x, y, 4.0)[..., 2] ** -2 - 1, 0))
    patches = 0.62 + 0.42 * np.tanh(_waves(x, y, 12, 30) / 9)
    density = patches * (1 - meadow_mask(x, y)) * (1 - _smooth(0.65, 1.05, slope)) * (1 - burn_mask(x, y))
    density = density * _smooth(9, 18, road_distance(x, y))
    return np.clip(density * _smooth(PAD_RADIUS * 1.6, PAD_RADIUS * 3, np.hypot(np.asarray(x) - HOME[0], np.asarray(y) - HOME[1])), 0, 1)


def jittered_points(rng, extent, spacing):
    x0, y0, x1, y1 = extent
    cols, rows = int((x1 - x0) / spacing), int((y1 - y0) / spacing)
    x, y = np.meshgrid(x0 + spacing * np.arange(cols), y0 + spacing * np.arange(rows))
    x = x.ravel() + rng.uniform(0, spacing, x.size)
    y = y.ravel() + rng.uniform(0, spacing, y.size)
    return x, y


def _choose(rng, weights):
    weights = np.maximum(np.asarray(weights, dtype=float), 1e-6)
    cumulative = np.cumsum(weights / weights.sum(axis=0), axis=0)
    picks = rng.random(weights.shape[1])
    return np.argmax(cumulative >= picks[None, :] - 1e-9, axis=0)


def place_trees(seed=7, spacing=7.5, margin=160.0, belt=700.0):
    """Stems with species index by elevation/moisture; density thins in the outer visual belt."""
    rng = np.random.default_rng(seed)
    x, y = jittered_points(
        rng, (-margin, -margin, WILDLAND_SIZE + margin, WILDLAND_SIZE + margin), spacing
    )
    inside = (x > 0) & (x < WILDLAND_SIZE) & (y > 0) & (y < WILDLAND_SIZE)
    keep = rng.random(x.size) < forest_density(x, y) * np.where(inside, 1.0, 0.6)
    x, y = x[keep], y[keep]
    far_x, far_y = jittered_points(rng, (-belt, -belt, WILDLAND_SIZE + belt, WILDLAND_SIZE + belt), 19.0)
    half = WILDLAND_SIZE / 2
    outside = np.maximum(np.abs(far_x - half), np.abs(far_y - half)) > half + margin
    far_x, far_y = far_x[outside], far_y[outside]
    far_keep = (rng.random(far_x.size) < 0.8) & (road_distance(far_x, far_y) > 12)
    x, y = np.concatenate([x, far_x[far_keep]]), np.concatenate([y, far_y[far_keep]])
    z = terrain_height(x, y)
    high = _smooth(58, 120, z)
    wet = _smooth(-6, 9, _waves(x, y, 8, 26))
    # Douglas fir, yellow pine, white pine, spruce, red cedar, black oak, aspen.
    species = _choose(
        rng,
        [
            1.0 - 0.3 * high,
            0.9 * (1 - wet),
            0.25 + 0.3 * high,
            0.05 + 0.75 * high,
            0.45 * wet,
            0.55 * (1 - high) * (1 - 0.5 * wet),
            0.35 * (1 - high) * wet,
        ],
    )
    return {
        "x": x,
        "y": y,
        "z": z - rng.uniform(0.05, 0.3, x.size),
        "yaw": rng.uniform(0, 360, x.size),
        "scale": rng.lognormal(0.0, 0.2, x.size).clip(0.55, 1.45),
        "species": species,
    }


def place_understory(seed=11, spacing=4.2):
    """Shrubs, ferns, boulders and woody debris under and between the stems."""
    rng = np.random.default_rng(seed)
    x, y = jittered_points(rng, (0, 0, WILDLAND_SIZE, WILDLAND_SIZE), spacing)
    forest = forest_density(x, y)
    road = road_distance(x, y)
    pad = np.hypot(x - HOME[0], y - HOME[1])
    keep = (rng.random(x.size) < 0.1 + 0.42 * forest) & (road > 6) & (pad > PAD_RADIUS * 1.4)
    x, y, forest = x[keep], y[keep], forest[keep]
    return {
        "x": x,
        "y": y,
        "z": terrain_height(x, y) - 0.05,
        "yaw": rng.uniform(0, 360, x.size),
        "scale": rng.lognormal(-0.1, 0.32, x.size).clip(0.35, 1.9),
        "forest": forest,
        "roll": rng.random(x.size),
    }


def place_grass(seed=13, spacing=1.15, radius=210.0):
    """Dense clumps only in the hero meadow and near the fire, where cameras see them closely."""
    rng = np.random.default_rng(seed)
    centres = [(MEADOW[0], MEADOW[1], radius), (IGNITION[0], IGNITION[1], radius)]
    rows = []
    for cx, cy, reach in centres:
        x, y = jittered_points(rng, (cx - reach, cy - reach, cx + reach, cy + reach), spacing)
        near = np.hypot(x - cx, y - cy) < reach
        rows.append((x[near], y[near]))
    wide_x, wide_y = jittered_points(rng, (0, 0, WILDLAND_SIZE, WILDLAND_SIZE), 2.6)
    rows.append((wide_x, wide_y))
    x = np.concatenate([r[0] for r in rows])
    y = np.concatenate([r[1] for r in rows])
    cover = np.maximum(meadow_mask(x, y), 0.34) * (1 - burn_mask(x, y))
    keep = (
        (rng.random(x.size) < cover)
        & (road_distance(x, y) > 4.5)
        & (np.hypot(x - HOME[0], y - HOME[1]) > PAD_RADIUS * 0.8)
    )
    x, y = x[keep], y[keep]
    return {
        "x": x,
        "y": y,
        "z": terrain_height(x, y) - 0.03,
        "yaw": rng.uniform(0, 360, x.size),
        "scale": rng.uniform(0.7, 1.35, x.size),
        "normal": terrain_normal(x, y),
        "roll": rng.random(x.size),
    }

"""Authored triangle assets shared by the live renderer and Rerun; no simulator logic."""

import json
import math
import struct
from pathlib import Path

import numpy as np

ASSETS = Path(__file__).parent / "assets"


class Mesh:
    def __init__(self):
        self.vertices, self.colors = [], []

    def tri(self, a, b, c, color):
        self.vertices.extend([a, b, c])
        self.colors.extend([color, color, color])

    def quad(self, a, b, c, d, color):
        self.tri(a, b, c, color)
        self.tri(a, c, d, color)

    def box(self, center, size, color):
        x, y, z = center
        a, b, c = np.array(size) / 2
        points = [
            (x + sx * a, y + sy * b, z + sz * c)
            for sx, sy, sz in [
                (-1, -1, -1),
                (1, -1, -1),
                (1, 1, -1),
                (-1, 1, -1),
                (-1, -1, 1),
                (1, -1, 1),
                (1, 1, 1),
                (-1, 1, 1),
            ]
        ]
        for ids in [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]:
            self.quad(*(points[k] for k in ids), color)

    def tube(self, a, b, radius, color, sides=10, top_radius=None):
        a, b = np.array(a, float), np.array(b, float)
        axis = b - a
        axis /= max(np.linalg.norm(axis), 1e-8)
        reference = np.array([0, 0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0, 0])
        u = np.cross(axis, reference)
        u /= np.linalg.norm(u)
        v = np.cross(axis, u)
        top_radius = radius if top_radius is None else top_radius
        for k in range(sides):
            p, q = 2 * math.pi * k / sides, 2 * math.pi * (k + 1) / sides
            da, db = u * math.cos(p) + v * math.sin(p), u * math.cos(q) + v * math.sin(q)
            self.quad(a + da * radius, a + db * radius, b + db * top_radius, b + da * top_radius, color)
            self.tri(a, a + db * radius, a + da * radius, color)
            self.tri(b, b + da * top_radius, b + db * top_radius, color)

    def merge(self, other, position=(0, 0, 0), scale=1, angle=0, tint=1):
        vertices = np.asarray(other.vertices, dtype=np.float32) * scale
        rotation = np.array(
            [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
        )
        self.vertices.extend(vertices @ rotation.T + np.asarray(position))
        colors = np.asarray(other.colors, dtype=float)
        colors[:, :3] = np.clip(colors[:, :3] * tint, 0, 255)
        self.colors.extend(colors.astype(np.uint8))

    def arrays(self):
        positions = np.asarray(self.vertices, dtype="<f4")
        triangles = positions.reshape(-1, 3, 3)
        normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-8)
        return positions, np.repeat(normals, 3, axis=0).astype("<f4"), np.asarray(self.colors, dtype=np.uint8)

    def save(self, path, name):
        positions, normals, colors = self.arrays()
        # glTF vertex colors are linear; authored palette values above are sRGB.
        linear = colors.copy()
        rgb = colors[:, :3].astype(float) / 255
        linear[:, :3] = np.rint(
            np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4) * 255
        ).astype(np.uint8)
        colors = linear
        # Rerun's GLB importer requires an explicit triangle index accessor.
        arrays = [positions, normals, colors, np.arange(len(positions), dtype="<u4")]
        blobs, views, offset = [], [], 0
        for index, array in enumerate(arrays):
            blob = array.tobytes()
            views.append(
                {
                    "buffer": 0,
                    "byteOffset": offset,
                    "byteLength": len(blob),
                    "target": 34963 if index == 3 else 34962,
                }
            )
            blob += b"\x00" * ((-len(blob)) % 4)
            blobs.append(blob)
            offset += len(blob)
        document = {
            "asset": {"version": "2.0", "generator": "EMBERNET authored geometry"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0, "name": name}],
            "buffers": [{"byteLength": offset}],
            "bufferViews": views,
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,
                    "count": len(positions),
                    "type": "VEC3",
                    "min": positions.min(0).tolist(),
                    "max": positions.max(0).tolist(),
                },
                {"bufferView": 1, "componentType": 5126, "count": len(normals), "type": "VEC3"},
                {
                    "bufferView": 2,
                    "componentType": 5121,
                    "count": len(colors),
                    "type": "VEC4",
                    "normalized": True,
                },
                {"bufferView": 3, "componentType": 5125, "count": len(positions), "type": "SCALAR"},
            ],
            "materials": [
                {
                    "name": "Surface colors",
                    "pbrMetallicRoughness": {
                        "baseColorFactor": [1, 1, 1, 1],
                        "metallicFactor": 0.08,
                        "roughnessFactor": 0.8,
                    },
                    "doubleSided": True,
                }
            ],
            "meshes": [
                {
                    "primitives": [
                        {
                            "attributes": {"POSITION": 0, "NORMAL": 1, "COLOR_0": 2},
                            "indices": 3,
                            "material": 0,
                        }
                    ]
                }
            ],
        }
        header = json.dumps(document, separators=(",", ":")).encode()
        header += b" " * ((-len(header)) % 4)
        binary = b"".join(blobs)
        total = 12 + 8 + len(header) + 8 + len(binary)
        Path(path).write_bytes(
            struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(header), b"JSON")
            + header
            + struct.pack("<I4s", len(binary), b"BIN\x00")
            + binary
        )
        return {"name": name, "triangles": len(positions) // 3, "bytes": total}


def pine(seed=0):
    rng = np.random.default_rng(seed)
    mesh = Mesh()
    mesh.tube((0, 0, 0), (0, 0, 16), 0.3, (77, 61, 42, 255), 8, top_radius=0.10)
    for tier in range(6):
        base = 2.0 + tier * 2.0
        radius = 3.5 - tier * 0.44
        peak = (rng.uniform(-0.2, 0.2), rng.uniform(-0.2, 0.2), base + 5.8)
        count = 13
        ring = []
        for k in range(count):
            a = k * 2 * math.pi / count
            r = radius * rng.uniform(0.72, 1.12)
            ring.append((math.cos(a) * r, math.sin(a) * r, base + rng.uniform(-0.8, 0.5)))
        for k in range(count):
            color = np.array([51, 81, 56, 255]) + np.array([tier * 3, tier * 3, tier * 2, 0])
            color[:3] = np.clip(color[:3] * rng.uniform(0.83, 1.16), 0, 255)
            mesh.tri(ring[k], ring[(k + 1) % count], peak, color.astype(np.uint8))
            mesh.tri((0, 0, base + 0.4), ring[(k + 1) % count], ring[k], (38, 62, 42, 255))
        for k in range(2):
            a = k * math.pi * 0.4 + tier
            endpoint = (math.cos(a) * radius * 0.9, math.sin(a) * radius * 0.9, base - 0.25)
            mesh.tube((0, 0, base + 0.6), endpoint, 0.06, (76, 66, 45, 255), 5, top_radius=0.02)
    return mesh


def drone():
    mesh = Mesh()
    carbon, shell, metal = (37, 45, 48, 255), (214, 221, 212, 255), (105, 122, 129, 255)
    mesh.box((0, 0, 0.08), (1.35, 2.2, 0.48), carbon)
    mesh.box((0, 0, 0.38), (1.17, 1.65, 0.28), shell)
    mesh.box((0, -0.06, 0.57), (0.95, 1.05, 0.16), (219, 132, 68, 255))
    for x in [-0.43, 0.43]:
        for y in np.linspace(-0.6, 0.6, 7):
            mesh.box((x, y, 0.54), (0.065, 0.075, 0.02), carbon)
    for x, y in [(-1.65, -1.65), (1.65, -1.65), (-1.65, 1.65), (1.65, 1.65)]:
        mesh.tube((x * 0.16, y * 0.16, 0.15), (x, y, 0.25), 0.12, carbon, 8)
        mesh.tube((x * 0.3, y * 0.3, -0.13), (x, y, 0.12), 0.055, metal, 6)
        mesh.tube((x, y, 0.17), (x, y, 0.52), 0.23, carbon, 14)
        mesh.tube((x, y, 0.52), (x, y, 0.62), 0.095, metal, 10)
        for angle in [0, math.pi / 2]:
            dx, dy = math.cos(angle) * 0.9, math.sin(angle) * 0.9
            mesh.quad(
                (x - dx - 0.09, y - dy, 0.63),
                (x + dx, y + dy - 0.09, 0.63),
                (x + dx + 0.09, y + dy, 0.66),
                (x - dx, y - dy + 0.09, 0.66),
                (51, 60, 59, 255),
            )
        light = (224, 79, 59, 255) if y < 0 else (119, 195, 154, 255)
        mesh.box((x, y - 0.24, 0.31), (0.2, 0.06, 0.09), light)
    # Underslung suppressant tank, pump plumbing and three-axis camera pod.
    mesh.tube((0, -0.65, -0.50), (0, 0.7, -0.50), 0.38, (195, 209, 205, 255), 18)
    for y in [-0.45, 0.46]:
        mesh.tube((0, y - 0.055, -0.50), (0, y + 0.055, -0.50), 0.4, metal, 16)
    mesh.tube((0, 0.7, -0.5), (0, 0.7, -1.08), 0.075, metal, 8)
    mesh.tube((0, 0.7, -1.05), (0, 0.7, -1.25), 0.12, carbon, 8)
    mesh.box((0, -1.13, -0.37), (0.5, 0.34, 0.4), metal)
    mesh.tube((0, -1.15, -0.4), (0, -1.38, -0.4), 0.14, carbon, 14)
    mesh.tube((0, -1.38, -0.4), (0, -1.43, -0.4), 0.1, (46, 112, 139, 255), 14)
    for x in [-0.75, 0.75]:
        for y in [-0.7, 0.7]:
            mesh.tube((x * 0.7, y, 0.05), (x, y, -1.12), 0.055, carbon, 8)
        mesh.tube((x, -1.3, -1.12), (x, 1.3, -1.12), 0.065, metal, 8)
    mesh.tube((0.38, 0.6, 0.52), (0.38, 0.6, 1.15), 0.035, carbon, 6)
    mesh.box((0.38, 0.6, 1.2), (0.1, 0.1, 0.12), shell)
    return mesh


def person():
    mesh = Mesh()
    mesh.tube((0, 0, 0.92), (0, 0, 1.52), 0.19, (195, 87, 40, 255), 10, top_radius=0.25)
    mesh.tube((0, 0, 1.54), (0, 0, 1.89), 0.16, (211, 171, 130, 255), 10)
    for x in [-0.15, 0.15]:
        mesh.tube((x, 0, 0.95), (x * 1.25, 0, 0.12), 0.09, (47, 58, 69, 255), 8)
        mesh.box((x * 1.25, -0.08, 0.08), (0.19, 0.35, 0.16), (38, 43, 42, 255))
        mesh.tube((x * 1.7, 0, 1.45), (x * 2.7, -0.03, 0.98), 0.065, (199, 99, 54, 255), 8)
    return mesh


def terrain_height(x, y):
    base = -0.7 - 1.1 * math.sin(x * 0.025) * math.sin(y * 0.027)
    edge = max(0, abs(x - 160) - 180, abs(y - 160) - 180)
    return base + edge * 0.2 + math.sin(x * 0.014 + y * 0.012) * edge * 0.06


def forest_scene(seed=41):
    rng = np.random.default_rng(seed)
    mesh = Mesh()
    n = 75
    grid = np.linspace(-140, 460, n)

    def vertex(x, y):
        return (x, y, terrain_height(x, y))

    for x in range(n - 1):
        for y in range(n - 1):
            a, b, c, d = (
                vertex(grid[x], grid[y]),
                vertex(grid[x + 1], grid[y]),
                vertex(grid[x + 1], grid[y + 1]),
                vertex(grid[x], grid[y + 1]),
            )
            points = [a, b, c, a, c, d]
            mesh.vertices.extend(points)
            for px, py, pz in points:
                path_distance = abs(px - (160 + 20 * math.sin(py * 0.014)))
                road = np.clip((12 - path_distance) / 5, 0, 1)
                variation = (
                    0.95 + 0.06 * math.sin(px * 0.07 + math.sin(py * 0.03)) + 0.04 * math.sin(py * 0.11)
                )
                color = np.array([67, 82, 47], float) * (1 - road) + np.array([118, 109, 83]) * road
                mesh.colors.append([*np.clip(color * variation, 0, 255).astype(np.uint8), 255])
    trees = []
    prototypes = [pine(k) for k in range(3)]
    for k in range(940):
        x, y = rng.uniform(-85, 405), rng.uniform(30, 430)
        if abs(x - (160 + 20 * math.sin(y * 0.014))) < 12 or (x - 248) ** 2 + (y - 280) ** 2 < 30**2:
            continue
        if min((x - 96) ** 2 + (y - 108.8) ** 2, (x - 220.8) ** 2 + (y - 214.4) ** 2) < 14**2:
            continue
        scale = rng.uniform(0.62, 1.4)
        angle = rng.uniform(0, math.tau)
        z = terrain_height(x, y)
        mesh.merge(prototypes[k % 3], (x, y, z), scale, angle, rng.uniform(0.82, 1.15))
        trees.append([round(float(v), 3) for v in (x, y, z, scale, angle)])
    # Field support area with service pads, road, field station and water storage.
    for k in range(6):
        x = 320 * (k + 0.5) / 6
        mesh.box((x, 15, -0.1), (14, 14, 0.3), (139, 147, 132, 255))
        mesh.box((x - 2, 15, 0.08), (0.65, 5, 0.05), (232, 229, 204, 255))
        mesh.box((x + 2, 15, 0.08), (0.65, 5, 0.05), (232, 229, 204, 255))
        mesh.box((x, 15, 0.08), (4.6, 0.65, 0.05), (232, 229, 204, 255))
        for side in [-1, 1]:
            mesh.box((x + side * 6.3, 15, 0.15), (0.25, 12, 0.05), (220, 151, 71, 255))
    mesh.box((160, -18, 2), (24, 12, 4), (196, 194, 174, 255))
    mesh.box((160, -18, 4.25), (26, 14, 0.5), (83, 93, 88, 255))
    for x in [152, 160, 168]:
        mesh.box((x, -24.05, 2.4), (4, 0.08, 1.6), (64, 103, 119, 255))
    mesh.box((174, -17, 2), (1.4, 5, 4), (74, 82, 78, 255))
    for x in [130, 137]:
        mesh.tube((x, -16, 0), (x, -16, 6), 2.3, (175, 189, 186, 255), 20)
        mesh.tube((x, -16, 6), (x, -16, 6.3), 2.4, (112, 133, 136, 255), 20)
    for x in [117, 204]:
        mesh.tube((x, -18, 0), (x, -18, 13), 0.16, (97, 110, 109, 255), 8)
        mesh.box((x, -18, 13), (2.5, 1, 0.4), (214, 214, 186, 255))
    return mesh, trees


def build_assets():
    ASSETS.mkdir(parents=True, exist_ok=True)
    forest, trees = forest_scene()
    reports = [
        forest.save(ASSETS / "forest.glb", "EMBERNET forest and field station"),
        drone().save(ASSETS / "drone.glb", "EMBERNET suppression quadrotor"),
        person().save(ASSETS / "person.glb", "Synthetic person"),
    ]
    manifest = {
        "seed": 41,
        "coordinate_system": "right-handed Z-up, metres",
        "assets": reports,
        "trees": trees,
        "lake": {"x": 248, "y": 280, "radius": 25},
        "license": "Original EMBERNET procedural geometry; Three.js separately licensed MIT",
    }
    (ASSETS / "manifest.json").write_text(json.dumps(manifest, separators=(",", ":")), encoding="utf-8")
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    build_assets()

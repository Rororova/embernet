"""Detailed geometry in native Rerun, sharing the live view's actual GLB assets."""

import json
import math
import struct

import numpy as np

from .visual_assets import ASSETS, Mesh, terrain_height


def shared_mesh(rr, name):
    """Decode authored GLB arrays directly for Rerun's generated-mesh path."""
    payload = (ASSETS / name).read_bytes()
    size = struct.unpack_from("<I", payload, 12)[0]
    document = json.loads(payload[20 : 20 + size])
    start = 20 + size + 8

    def array(index, dtype, width):
        accessor = document["accessors"][index]
        view = document["bufferViews"][accessor["bufferView"]]
        return np.frombuffer(
            payload, dtype=dtype, count=accessor["count"] * width, offset=start + view["byteOffset"]
        ).reshape(-1, width)

    colors = array(2, np.uint8, 4).copy()
    linear = colors[:, :3] / 255
    colors[:, :3] = np.rint(
        np.where(linear <= 0.0031308, linear * 12.92, 1.055 * linear ** (1 / 2.4) - 0.055) * 255
    ).astype(np.uint8)
    return rr.Mesh3D(
        vertex_positions=array(0, "<f4", 3),
        vertex_normals=array(1, "<f4", 3),
        vertex_colors=colors,
        triangle_indices=array(3, "<u4", 1).reshape(-1, 3),
    )


class SceneLogger:
    def __init__(self, rr, recording, sim):
        self.rr, self.rec = rr, recording
        self.previous = {}
        self.subjects = set()
        self.fire_ids = set()
        recording.log("world/forest", shared_mesh(rr, "forest.glb"), static=True)
        aircraft = shared_mesh(rr, "drone.glb")
        for key in sim.states:
            recording.log(f"world/aircraft/{key}/model", aircraft, static=True)

    def log(self, sim):
        rr, rec = self.rr, self.rec
        for key, state in sim.states.items():
            position = np.asarray(state.position)
            previous = self.previous.get(key, position)
            motion = position - previous
            yaw = math.atan2(-motion[0], motion[1]) if np.linalg.norm(motion[:2]) > 0.1 else 0
            self.previous[key] = position.copy()
            rec.log(
                f"world/aircraft/{key}",
                rr.Transform3D(translation=position, quaternion=[0, 0, math.sin(yaw / 2), math.cos(yaw / 2)]),
            )
            rec.log(
                f"world/aircraft/{key}/label",
                rr.Points3D(
                    [[0, 0, 3.7]], radii=0.02, colors=[[235, 230, 207]], labels=[f"{key} · {state.task}"]
                ),
            )
            discharge = getattr(sim, "_discharging", {}).get(key)
            if discharge:
                start = position + np.array([0, 0, -1.2])
                target = np.asarray(discharge["target"], float)
                target[2] = terrain_height(*target[:2]) + 0.1
                rec.log(
                    f"world/suppression/{key}",
                    rr.LineStrips3D([[start, target]], colors=[[180, 226, 237, 230]], radii=0.14),
                )
                phases = (np.linspace(0, 1, 45) + sim.time * 0.6) % 1
                drops = start[None] + (target - start)[None] * phases[:, None]
                drops[:, :2] += np.column_stack([np.sin(phases * 54 + sim.time), np.cos(phases * 42)]) * 0.3
                rec.log(
                    f"world/suppression/{key}/droplets",
                    rr.Points3D(drops, radii=0.10, colors=[[197, 235, 240, 190]]),
                )
            else:
                rec.log(f"world/suppression/{key}", rr.Clear(recursive=True))
        active_ids = set()
        for fire in sim.fires:
            root = f"world/fire/{fire.id}"
            if fire.remaining <= 0.2:
                if fire.id in self.fire_ids:
                    rec.log(root, rr.Clear(recursive=True))
                continue
            active_ids.add(fire.id)
            flames = Mesh()
            radius = fire.radius
            for k in range(18):
                angle = k * 2.39996
                r = radius * math.sqrt((k + 0.5) / 18) * 0.85
                x = fire.x + math.cos(angle) * r
                y = fire.y + math.sin(angle) * r
                base = terrain_height(x, y) + 0.05
                height = (2.8 + fire.severity * 4) * (1 + 0.18 * math.sin(sim.time * 5 + k))
                peak = (x + math.sin(sim.time * 3 + k) * 0.6, y + 0.3, base + height)
                width = max(0.5, radius * 0.28)
                for n in range(5):
                    a = n * math.tau / 5
                    b = (n + 1) * math.tau / 5
                    flames.tri(
                        (x + math.cos(a) * width, y + math.sin(a) * width, base),
                        (x + math.cos(b) * width, y + math.sin(b) * width, base),
                        peak,
                        (255, 186 if n % 2 else 100, 35, 235),
                    )
            vertices, normals, colors = flames.arrays()
            rec.log(
                root + "/flames",
                rr.Mesh3D(vertex_positions=vertices, vertex_normals=normals, vertex_colors=colors),
            )
            centers, half_sizes = [], []
            for k in range(18):
                phase = (k / 18 + sim.time * 0.035) % 1
                angle = k * 2.39996
                r = radius * (0.25 + phase * 0.6)
                centers.append(
                    [
                        fire.x + math.cos(angle) * r + phase * phase * 14,
                        fire.y + math.sin(angle) * r,
                        3 + phase * 35,
                    ]
                )
                half_sizes.append([2 + phase * 5, 2 + phase * 5, 1.3 + phase * 3])
            rec.log(
                root + "/smoke",
                rr.Ellipsoids3D(
                    centers=centers, half_sizes=half_sizes, colors=[[103, 113, 113, 70]] * len(centers)
                ),
            )
            rec.log(
                root + "/label",
                rr.Points3D(
                    [[fire.x, fire.y, 12]],
                    radii=0.02,
                    labels=[f"{fire.id} · severity {fire.severity:.2f}"],
                    colors=[[249, 202, 147]],
                ),
            )
        self.fire_ids = active_ids
        for subject in sim.subjects:
            root = f"world/subjects/{subject.id}"
            if subject.id not in self.subjects:
                if subject.kind == "person":
                    rec.log(root + "/model", shared_mesh(rr, "person.glb"), static=True)
                else:
                    rec.log(
                        root + "/model",
                        rr.Boxes3D(
                            centers=[[0, 0, 0.9]], half_sizes=[[0.9, 0.35, 0.45]], colors=[[157, 128, 85]]
                        ),
                        static=True,
                    )
                self.subjects.add(subject.id)
            rec.log(
                root, rr.Transform3D(translation=[subject.x, subject.y, terrain_height(subject.x, subject.y)])
            )
            rec.log(
                root + "/label",
                rr.Points3D(
                    [[0, 0, 3]],
                    radii=0.02,
                    colors=[[178, 207, 217]],
                    labels=[f"{subject.kind} · {'reached' if subject.responded_at else 'unreached'}"],
                ),
            )

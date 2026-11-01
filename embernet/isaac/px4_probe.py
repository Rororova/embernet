"""CPU protocol diagnostic before spending RTX time; not delivered Isaac physics."""

import json
import time

import numpy as np
from scipy.spatial.transform import Rotation

from .px4_bridge import PX4SITL


def run_probe(output):
    output.mkdir(parents=True, exist_ok=True)
    autopilot = PX4SITL(0, output / "vehicle-0")
    autopilot.start()
    p, v, omega = np.array([0.0, 0.0, 0.12]), np.zeros(3), np.zeros(3)
    rotation = Rotation.identity()
    inertia = np.array([0.029125, 0.029125, 0.055225])
    records = []
    start = time.monotonic()
    try:
        for index in range(10000):
            t = index / 250
            target = np.array([0, 0, 3] if t < 28 else [3, 0, 3])
            wrench = autopilot.step(t, p, v, rotation.as_quat(), rotation.apply(omega), target)
            acceleration = rotation.apply([0, 0, wrench[0]]) / 1.5 + [0, 0, -9.80665] - 0.08 * v
            v += acceleration / 250
            p += v / 250
            omega += (wrench[1:] - np.cross(omega, inertia * omega)) / inertia / 250
            rotation = rotation * Rotation.from_rotvec(omega / 250)
            if p[2] < 0.1:
                p[2], v[2] = 0.1, max(0.0, v[2])
            if not np.isfinite(p).all() or np.linalg.norm(p) > 60:
                raise RuntimeError(f"Diagnostic aircraft unstable: {p}")
            if index % 50 == 0:
                records.append(
                    {
                        "time": t,
                        "position": p.tolist(),
                        "target": target.tolist(),
                        "armed": autopilot.armed,
                        "offboard": autopilot.offboard_active,
                        "controls": autopilot.controls.tolist(),
                        "offset": None if autopilot.offset is None else autopilot.offset.tolist(),
                    }
                )
            if index % 1000 == 0:
                print(json.dumps(records[-1]), flush=True)
        report = {
            "diagnostic_only": True,
            "elapsed_seconds": time.monotonic() - start,
            "final_position": p.tolist(),
            "stats": autopilot.stats,
            "passed": bool(autopilot.stats["armed_seen"] and autopilot.stats["offboard_seen"] and p[2] > 2),
        }
        (output / "report.json").write_text(json.dumps(report, indent=2))
        return report
    finally:
        autopilot.close()
        (output / "telemetry.json").write_text(json.dumps(records, indent=2))

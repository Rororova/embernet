"""Actual PX4 motor outputs driving Isaac PhysX; no geometric-controller fallback."""

import json
import time

import numpy as np


def run_px4_trial(application, output, asset_root):
    import imageio.v2 as imageio
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    from PIL import Image

    from .native_airframe import create_airframe
    from .px4_bridge import PX4SITL
    from .scene import build_field_scene

    start = time.monotonic()
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    scene = build_field_scene(world.stage, asset_root)
    create_airframe(world.stage, "/World/Drone/body", (0, 0, 0.35))
    body = world.scene.add(RigidPrim("/World/Drone/body", name="px4_quad"))
    camera = rep.create.camera(position=(5, -8, 5), look_at=(1, 0, 2), focal_length=35)
    render = rep.create.render_product(camera, (960, 544))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(render)
    world.reset()
    for _ in range(8):
        world.render()
    autopilot = PX4SITL(0, output / "vehicle-0")
    autopilot.start()
    world.play()
    records, frames = [], []
    with (output / "telemetry.jsonl").open("w") as stream:
        try:
            for index in range(15000):
                t = index / 250
                positions, orientations = body.get_world_poses()
                p, q = positions[0], orientations[0][[1, 2, 3, 0]]
                velocity = body.get_velocities()[0]
                target = np.array([0, 0, 3] if t < 40 else [5, 0, 3])
                wrench = autopilot.step(t, p, velocity[:3], q, velocity[3:], target)
                body.apply_forces_and_torques_at_pos(
                    forces=np.array([[0, 0, wrench[0]]], np.float32),
                    torques=wrench[None, 1:].astype(np.float32),
                    is_global=False,
                )
                world.step(render=False)
                if index % 16 == 0:
                    world.render()
                if not np.isfinite(p).all() or p[2] < -0.5 or np.linalg.norm(p) > 50:
                    raise RuntimeError(f"PX4/PhysX flight left trial bounds: {p}")
                if index % 25 == 0:
                    row = {
                        "time": t,
                        "position": p.tolist(),
                        "quaternion_xyzw": q.tolist(),
                        "target": target.tolist(),
                        "controls": autopilot.controls.tolist(),
                        "armed": autopilot.armed,
                        "offboard": autopilot.offboard_active,
                    }
                    records.append(row)
                    stream.write(json.dumps(row) + "\n")
                if index % 64 == 0:
                    pixels = np.asarray(rgb.get_data())
                    if pixels.size:
                        frames.append(pixels[:, :, :3].copy())
            world.pause()
            for _ in range(4):
                world.render()
            Image.fromarray(np.asarray(rgb.get_data())[:, :, :3]).save(output / "rgb.png")
            if frames:
                imageio.mimwrite(
                    output / "px4-flight.mp4",
                    frames,
                    fps=250 / 64,
                    codec="libx264",
                    quality=8,
                    macro_block_size=1,
                )
            hover = [
                np.linalg.norm(np.asarray(r["position"]) - r["target"])
                for r in records
                if 35 <= r["time"] < 40
            ]
            final_error = float(np.linalg.norm(np.asarray(records[-1]["position"]) - records[-1]["target"]))
            report = {
                "engine": "Isaac Sim 6.2 / PhysX",
                "autopilot": "PX4 v1.14.3 SITL",
                "px4_running": True,
                "motor_source": "HIL_ACTUATOR_CONTROLS from PX4; no controller fallback",
                "hardware_actuation": False,
                "sim_time_seconds": float(world.current_time),
                "physics_hz": 250,
                "samples": len(records),
                "frames": len(frames),
                "hover_error_m": float(np.mean(hover)),
                "final_error_m": final_error,
                "final_position": records[-1]["position"],
                "mavlink": autopilot.stats,
                "scene": scene,
                "elapsed_seconds": time.monotonic() - start,
                "flight_pass": bool(
                    autopilot.stats["armed_seen"] and autopilot.stats["offboard_seen"] and final_error < 1.5
                ),
            }
            (output / "report.json").write_text(json.dumps(report, indent=2))
            return report
        finally:
            autopilot.close()

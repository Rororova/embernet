"""Three PhysX aircraft driven by local mission agents, with a bounded radio fault."""

import json
import time
from dataclasses import asdict, replace

import numpy as np

from ..contracts import Config
from .bridge import PhysicsMission
from .controller import GeometricController, rotation_xyzw
from .native_airframe import create_airframe
from .rotors import RotorAllocator
from .scene import build_field_scene


def run_fleet_trial(application, output, asset_root):
    import imageio.v2 as imageio
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    from PIL import Image

    from ..learning import PolicyRuntime

    start = time.monotonic()
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    scene = build_field_scene(world.stage, asset_root, offset=(40, 40, 0), clearing=(-30, 30, -22, 14))
    config = Config(drones=3, size=80, altitude=5, speed=3, max_water=0.5)
    homes = {f"E{i + 1:02}": (80 * (i + 0.5) / 3, 25, 0.35) for i in range(3)}
    policy = PolicyRuntime("/opt/mission.pt")
    mission = PhysicsMission(config, homes, policy)
    ids = sorted(homes)
    for key, home in homes.items():
        create_airframe(world.stage, f"/World/{key}/body", home)
    bodies = world.scene.add(RigidPrim([f"/World/{key}/body" for key in ids], name="fleet"))
    camera = rep.create.camera(position=(79, -3, 32), look_at=(40, 38, 4), focal_length=35)
    render = rep.create.render_product(camera, (1280, 720))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(render)
    world.reset()
    world.play()
    if list(bodies.prim_paths) != [f"/World/{key}/body" for key in ids]:
        raise RuntimeError("Physical body/agent identity order mismatch")
    controllers = [GeometricController(max_speed=3) for _ in ids]
    allocator = RotorAllocator()
    records, frames, commands = [], [], {}
    minimum_separation = float("inf")
    max_tilt = 0
    radio_audit = []
    with (output / "telemetry.jsonl").open("w") as stream:
        for index in range(9000):
            t = index / 250
            positions, orientations = bodies.get_world_poses()
            velocities = bodies.get_velocities()
            if not np.isfinite(positions).all() or np.any(positions[:, 2] < -0.5):
                raise RuntimeError("Invalid measured fleet state")
            if index % 125 == 0:
                for j, key in enumerate(ids):
                    mission.telemetry(key, position=positions[j], stamp=t, battery=1 - t / 850, water=0.5)
                mission.set_connection("E02", not (12 <= t < 22))
                commands = mission.tick(t)
                radio_audit.append(
                    {
                        "time": t,
                        "isolated": sorted(mission.mesh.isolated),
                        "deliveries": mission.last_deliveries,
                        "stats": asdict(mission.mesh.stats),
                    }
                )
                if t < 6:
                    for j, key in enumerate(ids):
                        commands[key] = replace(
                            commands[key],
                            target=(*homes[key][:2], 5 + j * 4),
                            reason="Independent takeoff before mission navigation",
                        )
                        mission.states[key].target = commands[key].target
            forces, torques, motors = [], [], []
            for j, key in enumerate(ids):
                q = orientations[j][[1, 2, 3, 0]]
                rotation = rotation_xyzw(q)
                command = commands[key]
                thrust, torque = controllers[j].wrench(
                    positions[j], velocities[j, :3], q, rotation.T @ velocities[j, 3:], command.target
                )
                rotor, actual = allocator.allocate(thrust, torque)
                forces.append(np.array([0, 0, actual[0]]) - rotation.T @ (0.12 * velocities[j, :3]))
                torques.append(actual[1:])
                motors.append(rotor.tolist())
                max_tilt = max(max_tilt, float(np.arccos(np.clip(rotation[2, 2], -1, 1))))
            bodies.apply_forces_and_torques_at_pos(
                forces=np.asarray(forces, np.float32),
                torques=np.asarray(torques, np.float32),
                is_global=False,
            )
            world.step(render=False)
            if index % 8 == 0:
                world.render()
            for j in range(3):
                for k in range(j):
                    minimum_separation = min(
                        minimum_separation, float(np.linalg.norm(positions[j] - positions[k]))
                    )
            if index % 25 == 0:
                row = {
                    "time": t,
                    "aircraft": {
                        key: {
                            "position": positions[j].tolist(),
                            "quaternion_xyzw": orientations[j][[1, 2, 3, 0]].tolist(),
                            "velocity": velocities[j, :3].tolist(),
                            "motors_rad_s": motors[j],
                            "command": asdict(commands[key]),
                            "connected": mission.states[key].connected,
                        }
                        for j, key in enumerate(ids)
                    },
                }
                records.append(row)
                stream.write(json.dumps(row) + "\n")
            if index % 48 == 0:
                pixels = np.asarray(rgb.get_data())
                if pixels.size:
                    frames.append(pixels[:, :, :3].copy())
    world.pause()
    for _ in range(8):
        world.render()
    Image.fromarray(np.asarray(rgb.get_data())[:, :, :3]).save(output / "rgb.png")
    if frames:
        imageio.mimwrite(output / "fleet.mp4", frames, fps=250 / 48, codec="libx264", quality=8)
    (output / "mission-events.json").write_text(json.dumps([e.to_dict() for e in mission.events], indent=2))
    (output / "radio-audit.json").write_text(json.dumps(radio_audit, indent=2))
    outage_deliveries = sum(len(r["deliveries"]["E02"]) for r in radio_audit if 12 <= r["time"] < 22)
    restored_deliveries = sum(len(r["deliveries"]["E02"]) for r in radio_audit if r["time"] >= 22)
    heights = {key: records[-1]["aircraft"][key]["position"][2] for key in ids}
    report = {
        "engine": "Isaac Sim 6.2.0 / PhysX",
        "controller": "Geometric rotor-wrench control",
        "mission_policy": "Existing V2 recurrent actor; not retrained in Isaac",
        "mission_inputs": "Own measured telemetry, own ledger and delivered mesh only",
        "incident_observations": 0,
        "scenario": "Three-aircraft search with E02 radio outage at 12–22 s",
        "physics_hz": 250,
        "physics_steps": 9000,
        "measured_sim_time_seconds": float(world.current_time),
        "duration_sim_seconds": 36,
        "samples": len(records),
        "frames": len(frames),
        "minimum_center_separation_m": minimum_separation,
        "maximum_tilt_deg": float(np.degrees(max_tilt)),
        "isolated_node_deliveries_during_outage": outage_deliveries,
        "isolated_node_deliveries_after_reconnect": restored_deliveries,
        "mesh_stats": asdict(mission.mesh.stats),
        "final_heights_m": heights,
        "scene": scene,
        "elapsed_seconds": time.monotonic() - start,
        "px4_running": False,
        "hardware_actuation": False,
        "payload_liters": 0,
        "fleet_pass": bool(
            minimum_separation > 1.5
            and all(2 < v < 20 for v in heights.values())
            and outage_deliveries == 0
            and restored_deliveries > 0
        ),
        "limitation": "Short no-incident navigation/mesh trial; not validation of fire decisions or real aircraft.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report

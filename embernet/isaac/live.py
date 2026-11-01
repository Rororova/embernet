"""One shared native physics world; HTTP is in a thread, Kit owns the main thread."""

import io
import json
import os
import sys
import time
import traceback
from dataclasses import asdict
from pathlib import Path
from queue import Empty

import numpy as np

from ..live_api import PhysicsHub, serve_transport


def run_world(app, hub):
    import imageio.v2 as imageio
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    from PIL import Image
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    from ..contracts import Config, Detection
    from ..learning import PolicyRuntime
    from .bridge import PhysicsMission
    from .controller import rotation_xyzw
    from .native_airframe import create_airframe
    from .px4_bridge import PX4SITL
    from .scene import build_field_scene

    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    scene = build_field_scene(
        world.stage, "/opt/embernet-assets", offset=(40, 40, 0), clearing=(-30, 30, -22, 14)
    )
    config = Config(drones=3, size=80, altitude=5, speed=3, max_water=6)
    homes = {f"E{i + 1:02}": (80 * (i + 0.5) / 3, 25, 0.35) for i in range(3)}
    mission = PhysicsMission(config, homes, PolicyRuntime("/opt/mission.pt"))
    ids = sorted(homes)
    for key, home in homes.items():
        create_airframe(world.stage, f"/World/{key}/body", home)
    bodies = world.scene.add(RigidPrim([f"/World/{key}/body" for key in ids], name="shared_fleet"))
    camera = rep.create.camera(position=(45, 20, 3), look_at=(40, 25, 0.35), focal_length=26)
    render = rep.create.render_product(camera, (1152, 648))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(render)
    camera_prim = camera.get_output_prims()["prims"][0]
    camera_op = UsdGeom.Xformable(camera_prim).MakeMatrixXform()
    world.reset()
    for _ in range(8):
        world.render()
    if list(bodies.prim_paths) != [f"/World/{key}/body" for key in ids]:
        raise RuntimeError("Aircraft identity mismatch")
    pilots = []
    paused = False
    view = {"camera": "follow", "drone": "E02", "distance": 5.0, "yaw": -120.0, "pitch": 24.0}
    operator_visuals = {}
    people = {}
    accepted = []
    ticks = 0
    min_separation = 1000.0
    events = []
    last_frame = 0.0
    commands = {}
    video = imageio.get_writer(
        hub.output / "session.mp4", fps=5, codec="libx264", quality=8, macro_block_size=1
    )
    telemetry = (hub.output / "telemetry.jsonl").open("w")
    physics_log = (hub.output / "physics.jsonl").open("w")
    command_log = (hub.output / "commands.jsonl").open("w")

    def visual(incident):
        path = "/World/OperatorReports/" + incident.id.replace("-", "_")
        root = UsdGeom.Xform.Define(world.stage, path)
        root.AddTranslateOp().Set(Gf.Vec3d(*incident.position))
        material = UsdShade.Material.Define(world.stage, path + "/Material")
        shader = UsdShade.Shader.Define(world.stage, path + "/Material/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set((0.75, 0.12, 0.015))
        shader.CreateInput("emissiveColor", Sdf.ValueTypeNames.Color3f).Set((1.8, 0.3, 0.01))
        material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        cones = []
        for j in range(9):
            cone = UsdGeom.Cone.Define(world.stage, path + f"/Flame{j}")
            cone.CreateRadiusAttr(incident.extent * (0.18 if j else 0.4))
            cone.CreateHeightAttr(2.5 if j else 3.8)
            angle = j * 2.39996
            cone.AddTranslateOp().Set(
                (np.cos(angle) * incident.extent * 0.45, np.sin(angle) * incident.extent * 0.45, 1.1)
            )
            scale = cone.AddScaleOp()
            UsdShade.MaterialBindingAPI.Apply(cone.GetPrim()).Bind(material)
            cones.append(scale)
        return root, cones

    def survivor(incident):
        from ..visual_assets import person

        path = "/World/SurvivorReports/" + incident.id.replace("-", "_")
        root = UsdGeom.Xform.Define(world.stage, path)
        root.AddTranslateOp().Set(Gf.Vec3d(incident.position[0] + 2, incident.position[1], 0))
        points, normals, colors = person().arrays()
        mesh = UsdGeom.Mesh.Define(world.stage, path + "/Person")
        mesh.CreatePointsAttr(points.tolist())
        mesh.CreateNormalsAttr(normals.tolist())
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateFaceVertexCountsAttr([3] * (len(points) // 3))
        mesh.CreateFaceVertexIndicesAttr(np.arange(len(points)).tolist())
        mesh.CreateSubdivisionSchemeAttr("none")
        srgb = colors[:, :3] / 255
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        mesh.CreateDisplayColorAttr(linear.tolist())
        mesh.GetDisplayColorPrimvar().SetInterpolation(UsdGeom.Tokens.vertex)
        return root

    try:
        for j in range(3):
            pilot = PX4SITL(j, hub.output / f"vehicle-{j}")
            pilots.append(pilot)
            pilot.start()
        world.play()
        while time.time() < hub.deadline:
            now = ticks / 250
            while True:
                try:
                    value = hub.queue.get_nowait()
                except Empty:
                    break
                result = "applied"
                action = value["action"]
                if action == "stop":
                    hub.deadline = min(hub.deadline, time.time() + 2)
                    result = "session ending"
                elif action == "pause":
                    paused = True
                elif action == "resume":
                    paused = False
                elif action == "camera":
                    view.update({k: value[k] for k in view})
                elif action == "mesh":
                    mission.set_connection(value["drone"], value["enabled"])
                elif action == "incident":
                    ledger = mission.agents["E01"].memory
                    if len(ledger.incidents) >= 12:
                        result = "rejected: twelve-report limit"
                    else:
                        report = ledger.observe(
                            Detection(
                                value["kind"],
                                (value["x"], value["y"], 0),
                                value["radius"],
                                value["severity"],
                                0.75,
                                now,
                                "operator",
                            ),
                            "E01",
                        )
                        if report.id not in operator_visuals and report.kind == "fire":
                            operator_visuals[report.id] = visual(report)
                        if value["kind"] == "person" and report.id not in people:
                            people[report.id] = survivor(report)
                        result = "operator report " + report.id
                elif action == "resolve":
                    report = mission.agents["E01"].memory.incidents.get(value["incident_id"])
                    if report is None:
                        result = "rejected: unknown report"
                    else:
                        report.status = "cleared"
                        report.observed_at = now
                entry = dict(value, simulation_time=now, result=result)
                command_log.write(json.dumps(entry) + "\n")
                command_log.flush()
                accepted.append(entry)
                events.append(
                    {
                        "time": now,
                        "message": result
                        if action in ("incident", "resolve")
                        else action + " " + value["drone"],
                    }
                )
            positions, orientations = bodies.get_world_poses()
            velocities = bodies.get_velocities()
            if (
                not np.isfinite(positions).all()
                or np.any(positions[:, 2] < -0.5)
                or np.max(np.abs(positions)) > 150
            ):
                raise RuntimeError("Measured aircraft left bounded physics world")
            for j in range(3):
                for k in range(j):
                    min_separation = min(min_separation, float(np.linalg.norm(positions[j] - positions[k])))
            if not paused:
                if ticks % 125 == 0:
                    for j, key in enumerate(ids):
                        mission.telemetry(
                            key, position=positions[j], stamp=now, battery=max(0.3, 1 - now / 850)
                        )
                    commands = mission.tick(now)
                    telemetry.write(
                        json.dumps(
                            {
                                "time": now,
                                "aircraft": {key: asdict(mission.states[key]) for key in ids},
                                "isolated": sorted(mission.mesh.isolated),
                                "deliveries": mission.last_deliveries,
                                "radio": asdict(mission.mesh.stats),
                            }
                        )
                        + "\n"
                    )
                    telemetry.flush()
                forces = []
                torques = []
                for j, key in enumerate(ids):
                    target = np.asarray(commands[key].target)
                    if now < 24:
                        target = np.array([*homes[key][:2], 5 + 4 * j])
                    # Apply independent geofence and per-aircraft altitude lanes even during return.
                    target = np.array([np.clip(target[0], 8, 72), np.clip(target[1], 20, 54), 5 + 4 * j])
                    q = orientations[j][[1, 2, 3, 0]]
                    wrench = pilots[j].step(
                        now, positions[j], velocities[j, :3], q, velocities[j, 3:], target
                    )
                    forces.append(
                        np.array([0, 0, wrench[0]]) - rotation_xyzw(q).T @ (0.12 * velocities[j, :3])
                    )
                    torques.append(wrench[1:])
                bodies.apply_forces_and_torques_at_pos(
                    forces=np.asarray(forces, np.float32),
                    torques=np.asarray(torques, np.float32),
                    is_global=False,
                )
                world.step(render=False)
                ticks += 1
                if ticks % 25 == 0:
                    physics_log.write(
                        json.dumps(
                            {
                                "time": now,
                                "positions": positions.tolist(),
                                "orientations_wxyz": orientations.tolist(),
                                "velocities_world": velocities.tolist(),
                                "controls": [p.controls.tolist() for p in pilots],
                                "forces_flu": np.asarray(forces).tolist(),
                                "torques_flu": np.asarray(torques).tolist(),
                            }
                        )
                        + "\n"
                    )
                    physics_log.flush()
            else:
                time.sleep(0.015)
            if time.monotonic() - last_frame > 0.2:
                j = ids.index(view["drone"])
                focus = positions[j].astype(float)
                if view["camera"] == "overview":
                    eye = np.array([82.0, -5.0, 40.0])
                    focus = np.array([40.0, 38.0, 4.0])
                else:
                    yaw, pitch = np.radians([view["yaw"], view["pitch"]])
                    d = view["distance"]
                    eye = focus + d * np.array(
                        [np.cos(yaw) * np.cos(pitch), np.sin(yaw) * np.cos(pitch), np.sin(pitch)]
                    )
                    eye[2] = max(0.8, eye[2])
                camera_op.Set(
                    Gf.Matrix4d()
                    .SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, focus)), Gf.Vec3d(0, 0, 1))
                    .GetInverse()
                )
                for key, (root, cones) in operator_visuals.items():
                    report = mission.agents["E01"].memory.incidents[key]
                    root.MakeVisible() if report.status != "cleared" else root.MakeInvisible()
                    for j, scale in enumerate(cones):
                        scale.Set((1, 1, 0.7 + 0.3 * np.sin(now * 5 + j)))
                for key, root in people.items():
                    root.MakeVisible() if mission.agents["E01"].memory.incidents[
                        key
                    ].status != "cleared" else root.MakeInvisible()
                world.render()
                pixels = np.asarray(rgb.get_data())
                jpeg = None
                if pixels.size:
                    frame = pixels[:, :, :3].copy()
                    image = Image.fromarray(frame)
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=85)
                    jpeg = buffer.getvalue()
                    video.append_data(frame)
                    if hub.frame_id % 25 == 0:
                        image.save(hub.output / "latest.jpg")
                rows = []
                for j, key in enumerate(ids):
                    rows.append(
                        dict(
                            asdict(mission.states[key]),
                            position=positions[j].tolist(),
                            armed=pilots[j].armed,
                            offboard=pilots[j].offboard_active,
                            actuator_packets=pilots[j].stats["actuator_packets"],
                        )
                    )
                phase = (
                    "Paused"
                    if paused
                    else "Swarm active"
                    if now >= 24 and all(p.armed and p.offboard_active for p in pilots)
                    else "PX4 preflight and takeoff"
                )
                hub.publish(
                    {
                        "phase": phase,
                        "time": now,
                        "paused": paused,
                        "drones": rows,
                        "incidents": mission.agents["E01"].memory.records(),
                        "events": events[-12:]
                        + [{"time": e.time, "message": e.text} for e in mission.events[-5:]],
                        "radio": asdict(mission.mesh.stats),
                        "camera": view,
                        "scene": scene,
                    },
                    jpeg,
                )
                last_frame = time.monotonic()
        return {
            "sim_time_seconds": ticks / 250,
            "px4": [p.stats for p in pilots],
            "minimum_separation_m": min_separation,
            "commands": accepted,
            "scene": scene,
            "physical_payload_kg": 0,
            "capacity": "scenario units; no physical release",
            "detector": "Operator reports only; no claimed neural severity or camera confirmation",
            "completed": True,
            "motor_source": "PX4 HIL_ACTUATOR_CONTROLS",
            "policy": "trained V2 mission actor with independent safety",
        }
    finally:
        for pilot in pilots:
            pilot.close()
        video.close()
        telemetry.close()
        physics_log.close()
        command_log.close()


def main():
    import argparse
    import multiprocessing

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--duration", type=int, default=600)
    args = parser.parse_args()
    if not args.run_id.replace("-", "").isalnum() or not 30 <= args.duration <= 600:
        raise ValueError("Invalid bounded session")
    output = Path("/runs") / args.run_id
    os.makedirs("/tmp/embernet-xdg", mode=0o700, exist_ok=True)
    context = multiprocessing.get_context("spawn")
    parent_connection, child_connection = context.Pipe()
    hub = PhysicsHub(parent_connection, output, args.duration)
    server = context.Process(
        target=serve_transport,
        args=(child_connection, os.environ["EMBERNET_CONTROL_HASH"], str(output), args.duration),
        daemon=True,
    )
    server.start()
    child_connection.close()
    import hashlib
    import platform
    import subprocess
    from importlib.metadata import version

    source = Path(__file__).parents[1]
    binary = Path("/opt/PX4-Autopilot/build/px4_sitl_default/bin/px4")
    provenance = {
        "runtime": version("isaacsim"),
        "python": platform.python_version(),
        "px4_commit": subprocess.run(
            ["git", "-C", "/opt/PX4-Autopilot", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip(),
        "px4_binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "source_sha256": {
            str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in source.rglob("*.py")
        },
        "mission_sha256": hashlib.sha256(Path("/opt/mission.pt").read_bytes()).hexdigest(),
    }
    (output / "runtime.json").write_text(json.dumps(provenance, indent=2))
    patch = subprocess.run(
        [
            "git",
            "-C",
            "/opt/PX4-Autopilot",
            "diff",
            "--ignore-submodules",
            "--",
            "platforms/posix/src/px4/common/tasks.cpp",
            "platforms/common/px4_work_queue/WorkQueueManager.cpp",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    (output / "px4-scheduling.patch").write_text(patch.stdout)
    console = (output / "kit-console.log").open("w", buffering=1)
    os.dup2(console.fileno(), sys.stdout.fileno())
    os.dup2(console.fileno(), sys.stderr.fileno())
    application = None
    try:
        if os.environ.get("EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED") != "YES":
            raise RuntimeError("NVIDIA license consent required")
        from isaacsim import SimulationApp

        application = SimulationApp(
            {
                "headless": True,
                "renderer": "RayTracedLighting",
                "width": 1152,
                "height": 648,
                "multi_gpu": False,
                "fast_shutdown": True,
            }
        )
        report = run_world(application, hub)
        (output / "report.json").write_text(json.dumps(report, indent=2))
        hub.publish(dict(hub.snapshot(), phase="Session ended"))
    except BaseException:
        (output / "exception.txt").write_text(traceback.format_exc())
        hub.publish(dict(hub.snapshot(), phase="Simulation stopped: see saved logs"))
        raise
    finally:
        console.flush()
        import shutil

        for log in Path("/usr/local/lib/python3.12/site-packages/isaacsim/kit/logs/Kit").rglob("*.log"):
            shutil.copy2(log, output / log.name)
        if application:
            application.close()


if __name__ == "__main__":
    main()

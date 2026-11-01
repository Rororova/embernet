"""Live Metro 30 city scenario; Kit owns physics, a spawned process owns transport."""

import io
import json
import os
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from itertools import combinations
from pathlib import Path
from queue import Empty

import numpy as np

from ..live_api import PhysicsHub, serve_transport
from .city_scene import FIRE_POSITION


def mesh_view(mission):
    active = set(mission.mesh.links(mission.states))
    links = []
    for a, b in combinations(sorted(mission.states), 2):
        queued = sum(1 for _, _, receiver, _, sender in mission.mesh.queue if {sender, receiver} == {a, b})
        links.append(
            {
                "a": a,
                "b": b,
                "active": (a, b) in active,
                "distance": round(
                    float(
                        np.linalg.norm(np.subtract(mission.states[a].position, mission.states[b].position))
                    ),
                    1,
                ),
                "queued": queued,
            }
        )
    return {
        "links": links,
        "traffic": mission.mesh.traffic[-10:],
        "isolated": sorted(mission.mesh.isolated),
        "queued": len(mission.mesh.queue),
    }


CAMERA_RELEASE_SECONDS = 20.0


def mission_camera(positions, incidents, previous, blend=0.08):
    """Frame the aircraft working the incident closely enough to see the airframes."""
    positions = np.asarray(positions, float)
    points = list(positions)
    if incidents:
        anchor = np.asarray(incidents[0], float)
        near = [p for p in positions if np.linalg.norm(p - anchor) < 45]
        points = [*near, anchor] if len(near) >= 2 else [*points, anchor]
    center = np.mean(points, axis=0)
    spread = float(np.max(np.linalg.norm(np.asarray(points) - center, axis=1)))
    distance = float(np.clip(spread * 1.6 + 16, 30, 230))
    eye = center + distance * np.array([-0.28, -0.9, 0.2])
    eye[2] = max(eye[2], 12.0)
    wanted = np.concatenate([eye, center])
    return wanted if previous is None else previous + (wanted - previous) * blend


CITY_VIEWS = {
    "bird": ((120.0, 120.0, 235.0), (120.0, 120.0, 0.0)),
    "overview": ((265.0, -35.0, 185.0), (120.0, 132.0, 58.0)),
    "fire": ((175.0, 92.0, 118.0), FIRE_POSITION),
}


def visibility_probe(world, stage, rgb, camera_op, hub, ids, positions, label, focal, aperture):
    """Prove rendered pixels sit at measured poses by differencing visible vs hidden aircraft."""
    from PIL import Image
    from pxr import Gf, UsdGeom

    from ..overlay import Projector

    results = []
    for j, key in enumerate(ids):
        focus = positions[j].astype(float)
        eye = focus + np.array([-4.0, -5.0, 2.5])
        camera_op.Set(
            Gf.Matrix4d()
            .SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, focus)), Gf.Vec3d(0, 0, 1))
            .GetInverse()
        )
        prim = UsdGeom.Imageable(stage.GetPrimAtPath(f"/World/{key}/body"))
        for _ in range(3):
            world.render()
        shown = np.asarray(rgb.get_data())[:, :, :3].astype(np.int16)
        prim.MakeInvisible()
        for _ in range(3):
            world.render()
        hidden = np.asarray(rgb.get_data())[:, :, :3].astype(np.int16)
        prim.MakeVisible()
        difference = np.abs(shown - hidden).sum(axis=2) > 45
        expected = Projector(eye, focus, (0, 0, 1), focal=focal, aperture=aperture)(focus)
        # Effects and accumulation change distant pixels; only the aircraft's own window counts.
        rows, columns = np.ogrid[: difference.shape[0], : difference.shape[1]]
        difference &= np.hypot(columns - expected[0], rows - expected[1]) <= 110
        ys, xs = np.nonzero(difference)
        centroid = [float(xs.mean()), float(ys.mean())] if len(xs) else None
        results.append(
            {
                "drone": key,
                "changed_pixels": int(difference.sum()),
                "centroid_px": centroid,
                "expected_px": [expected[0], expected[1]],
                "error_px": (
                    None if centroid is None else float(np.hypot(centroid[0] - expected[0], centroid[1] - expected[1]))
                ),
                "measured_position": positions[j].tolist(),
            }
        )
        Image.fromarray(shown.astype(np.uint8)).save(hub.output / f"visibility-{label}-{key}.jpg")
    (hub.output / f"visibility-{label}.json").write_text(json.dumps(results, indent=2))
    return results


def run_world(app, hub, drones=6, render_hz=15.0, policy_name="baseline", world_name="city"):
    import imageio.v2 as imageio
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    from PIL import Image
    from pxr import Gf, Usd, UsdGeom

    from ..learning import PolicyRuntime
    from ..mission_acceptance import evaluate
    from ..overlay import Projector, draw_overlay, pick_point
    from ..swarm_mission import DRONE_COLORS, TICK_SECONDS, SwarmMission
    from .city_scene import build_city_scene
    from .controller import rotation_xyzw
    from .effects import CityFire, FlowFires, enable_flow
    from .native_airframe import MISSION_VISUAL_SCALE, create_airframe
    from .px4_bridge import PX4SITL

    # Wildland keeps sprites: its 5 Hz render budget has not been measured with Flow.
    if world_name == "city":
        enable_flow()
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    views, mission_scenario, ground_at, px4_limits = CITY_VIEWS, {}, None, None
    if world_name == "wildland":
        from .wildland_live import PX4_LIMITS, WILDLAND_VIEWS, prepare_render, scenario
        from .wildland_scene import build_wildland
        from .wildland_terrain import MISSION_ORIGIN, mission_ground

        prepare_render()
        scene = dict(build_wildland(world.stage, origin=MISSION_ORIGIN), world="wildland")
        views, mission_scenario, ground_at, px4_limits = WILDLAND_VIEWS, scenario(), mission_ground, PX4_LIMITS
    elif Path("/opt/nvidia-tower/Demos/AEC/TowerDemo/CityTowerDemopack").is_dir():
        from .authored_city import build_authored_city

        scene = build_authored_city(world.stage)
    else:
        scene = build_city_scene(world.stage, "/opt/embernet-assets")
    decisions = (hub.output / "decisions.jsonl").open("w")
    policy = PolicyRuntime("/opt/mission.pt") if policy_name == "learned" else None
    swarm = SwarmMission(drones, policy=policy, sink=decisions, **mission_scenario)
    mission = swarm.bridge
    homes = swarm.homes
    ids = swarm.ids
    count = len(ids)
    for index, key in enumerate(ids):
        create_airframe(
            world.stage,
            f"/World/{key}/body",
            homes[key],
            color=DRONE_COLORS[index % len(DRONE_COLORS)],
            visual_scale=MISSION_VISUAL_SCALE,
        )
    bodies = world.scene.add(RigidPrim([f"/World/{key}/body" for key in ids], name="city_fleet"))
    camera = rep.create.camera(position=(225, 15, 145), look_at=(120, 125, 48), focal_length=24)
    render = rep.create.render_product(camera, (960, 540))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(render)
    camera_prim = camera.get_output_prims()["prims"][0]
    camera_op = UsdGeom.Xformable(camera_prim).MakeMatrixXform()
    world.reset()
    for _ in range(8):
        world.render()
    # Replicator may wrap the camera or leave attributes unauthored; the probe checks these values.
    lens = next((p for p in Usd.PrimRange(camera_prim) if p.IsA(UsdGeom.Camera)), None)
    usd_camera = UsdGeom.Camera(lens) if lens else None
    focal = (usd_camera.GetFocalLengthAttr().Get() if usd_camera else None) or 24.0
    aperture = (usd_camera.GetHorizontalApertureAttr().Get() if usd_camera else None) or 20.955
    focal, aperture = float(focal), float(aperture)
    if ground_at and usd_camera:
        usd_camera.GetClippingRangeAttr().Set(Gf.Vec2f(0.3, 12000.0))
    import carb

    settings = carb.settings.get_settings()
    # Partial alpha needs these; without them smoke sprites render as opaque cutouts.
    settings.set_bool("/rtx/translucency/enabled", True)
    settings.set_bool("/rtx/raytracing/fractionalCutoutOpacity", True)
    # Fixed exposure: a nearby fire light must not swing the whole frame to black.
    settings.set_bool("/rtx/post/histogram/enabled", False)
    before = settings.get("/app/runLoops/main/rateLimitEnabled")
    settings.set_bool("/app/runLoops/main/rateLimitEnabled", False)
    settings.set_bool("/app/runLoops/present/rateLimitEnabled", False)
    (hub.output / "world-pacing.json").write_text(
        json.dumps(
            {
                "after_world_reset_before": before,
                "enabled": settings.get("/app/runLoops/main/rateLimitEnabled"),
                "render_hz_target": render_hz,
                "camera_focal": focal,
                "camera_aperture": aperture,
            }
        )
    )
    if list(bodies.prim_paths) != [f"/World/{key}/body" for key in ids]:
        raise RuntimeError("Aircraft identity mismatch")
    pilots = []
    motor_io = ThreadPoolExecutor(max_workers=count, thread_name_prefix="px4-io")
    paused = False
    view = {
        "camera": "mission",
        "drone": "E02",
        "distance": 14.0,
        "yaw": -120.0,
        "pitch": 22.0,
        "interactive": False,
        "pan_x": 0.0,
        "pan_y": 0.0,
    }
    fire_visuals, subject_visuals, accepted, events = {}, {}, [], []
    terrain_clearance = None
    ticks, min_separation, last_frame = 0, 1000.0, 0.0
    last_render_tick = -4
    last_video = 0.0
    framing = None
    probes = {}
    probe_times = {"takeoff": 16.0, "transit": 34.0}
    render_metrics = (hub.output / "render-metrics.jsonl").open("w")
    video_index = (hub.output / "video-index.jsonl").open("w")
    targets = dict(swarm.flight_targets)
    video = imageio.get_writer(
        hub.output / "session.mp4", fps=10, codec="libx264", quality=7, macro_block_size=1
    )
    video_frame = 0
    rendered_frames, dark_frames = 0, 0
    last_camera_input = 0.0
    last_projector = None
    telemetry = (hub.output / "telemetry.jsonl").open("w")
    physics_log = (hub.output / "physics.jsonl").open("w")
    command_log = (hub.output / "commands.jsonl").open("w")

    def survivor(name, position):
        from ..visual_assets import person

        path = "/World/ScenarioSubjects/" + name
        root = UsdGeom.Xform.Define(world.stage, path)
        root.AddTranslateOp().Set(Gf.Vec3d(*position))
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

    flow_fires = FlowFires(world.stage) if world_name == "city" else None

    def sync_world_visuals(now, eye):
        for key, fire in swarm.world.fires.items():
            scale = max(0.8, min(3.0, fire.extent0 / 3.5))
            if flow_fires:
                if key not in flow_fires.fires:
                    # The tower face sits at the report position; burn just outside its proxy.
                    outward = (0.0, -2.0, 0.0) if fire.position[2] > 20 else (0.0, 0.0, 0.0)
                    flow_fires.add(key, fire.position, fire.extent0, outward, scale)
                flow_fires.update(key, fire.active, fire.fraction, now)
                continue
            if key not in fire_visuals:
                fire_visuals[key] = CityFire(
                    world.stage, "/World/ScenarioFires/" + key, fire.position, "/opt/embernet-assets", scale
                )
            fire_visuals[key].update(now, fire.active, max(0.25, fire.fraction**0.5), eye)
        for key, subject in swarm.world.subjects.items():
            if key not in subject_visuals:
                subject_visuals[key] = survivor(key, subject.position)

    try:
        for index in range(count):
            pilot = PX4SITL(index, hub.output / f"vehicle-{index}", limits=px4_limits)
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
                result, action = "applied", value["action"]
                if action == "stop":
                    hub.deadline = min(hub.deadline, time.time() + 2)
                    result = "session ending"
                elif action == "pause":
                    paused = True
                elif action == "resume":
                    paused = False
                elif action == "camera":
                    view.update({key: value[key] for key in view})
                    last_camera_input = time.monotonic()
                elif action == "mesh":
                    swarm.set_connection(value["drone"], value["enabled"], now)
                    result = (
                        f"{value['drone']} reconnected · mesh links restored"
                        if value["enabled"]
                        else f"{value['drone']} isolated · radio links down, local ledger retained"
                    )
                elif action == "incident":
                    # Operator events change the world; aircraft must still observe them.
                    try:
                        # On terrain an operator's height is measured from the local ground.
                        lift = ground_at(value["x"], value["y"]) if ground_at else 0.0
                        position = (value["x"], value["y"], value["z"] + lift)
                        if value["kind"] == "person":
                            result = "world survivor evidence " + swarm.add_subject(position, now).id
                        else:
                            fire = swarm.add_fire(position, value["radius"], value["severity"], now)
                            result = "world fire " + fire.id
                    except ValueError as error:
                        result = f"rejected: {error}"
                elif action == "ignite":
                    # Resolve the normalized picture coordinate using the latest rendered camera.
                    point = (
                        pick_point(
                            last_projector, value["u"], value["v"], ground_at, swarm.obstacles, swarm.c.size
                        )
                        if last_projector
                        else None
                    )
                    try:
                        if point is None:
                            raise ValueError("click on the ground or a building inside the mission area")
                        fire = swarm.add_fire(point, value["radius"], value["severity"], now)
                        result = f"world fire {fire.id} ignited at {point[0]:.0f}, {point[1]:.0f}"
                    except ValueError as error:
                        result = f"rejected: {error}"
                        swarm.log.write(now, "scenario", "OPERATOR", f"Ignite {result}")
                elif action == "resolve":
                    fire = swarm.world.fires.get(value["incident_id"])
                    if fire is None:
                        result = "rejected: unknown world fire"
                    else:
                        swarm.manual_clear(fire.id, now)
                        result = "operator cleared world fire " + fire.id
                entry = dict(value, simulation_time=now, result=result)
                command_log.write(json.dumps(entry) + "\n")
                command_log.flush()
                accepted.append(entry)
                events.append({"time": now, "message": result})
            positions, orientations = bodies.get_world_poses()
            velocities = bodies.get_velocities()
            if (
                not np.isfinite(positions).all()
                or np.any(positions[:, 2] < -0.5)
                or np.max(np.abs(positions)) > 400
            ):
                raise RuntimeError("Measured aircraft left bounded physics world")
            for j in range(count):
                for k in range(j):
                    min_separation = min(min_separation, float(np.linalg.norm(positions[j] - positions[k])))
            if not paused:
                if ticks % int(250 * TICK_SECONDS) == 0:
                    measured = {key: positions[j].astype(float).tolist() for j, key in enumerate(ids)}
                    # Healthy means PX4 reports this aircraft armed and in Offboard.
                    armed = {key: pilots[j].armed and pilots[j].offboard_active for j, key in enumerate(ids)}
                    targets = swarm.tick(now, measured, armed)
                    if ground_at:
                        for row in positions.astype(float):
                            if row[2] > 4:
                                gap = float(row[2]) - ground_at(float(row[0]), float(row[1]))
                                terrain_clearance = min(gap, terrain_clearance or gap)
                    telemetry.write(
                        json.dumps(
                            {
                                "time": now,
                                "aircraft": {key: asdict(mission.states[key]) for key in ids},
                                "targets": targets,
                                "isolated": sorted(mission.mesh.isolated),
                                "deliveries": mission.last_deliveries,
                                "radio": asdict(mission.mesh.stats),
                                "world": swarm.world.records(),
                            }
                        )
                        + "\n"
                    )
                    telemetry.flush()
                forces, torques = [], []
                pending_motors = []
                for j, key in enumerate(ids):
                    target = np.asarray(targets[key], dtype=float)
                    q = orientations[j][[1, 2, 3, 0]]
                    pending_motors.append(
                        motor_io.submit(
                            pilots[j].step,
                            now,
                            positions[j].copy(),
                            velocities[j, :3].copy(),
                            q.copy(),
                            velocities[j, 3:].copy(),
                            target.copy(),
                        )
                    )
                for j, future in enumerate(pending_motors):
                    wrench = future.result()
                    q = orientations[j][[1, 2, 3, 0]]
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
                time.sleep(0.01)
            # A stray drag must not cost the observer the mission view for the whole session.
            if view["interactive"] and time.monotonic() - last_camera_input > CAMERA_RELEASE_SECONDS:
                view["interactive"] = False
            for label, when in probe_times.items():
                if label not in probes and now >= when:
                    probes[label] = visibility_probe(
                        world, world.stage, rgb, camera_op, hub, ids, positions, label, focal, aperture
                    )
            if time.monotonic() - last_frame >= 1 / render_hz and (paused or ticks - last_render_tick >= 4):
                frame_started = time.monotonic()
                j = ids.index(view["drone"])
                focus = positions[j].astype(float)
                up = (0, 0, 1)
                if view["camera"] == "mission":
                    active = [
                        row["position"]
                        for row in swarm.incidents_view()
                        if row["status"] not in ("cleared", "escalated") and row["committed"]
                    ]
                    framing = mission_camera(positions.astype(float), active[:1], framing)
                    eye, focus = framing[:3], framing[3:]
                elif view["camera"] == "bird":
                    eye, focus = map(np.array, views["bird"])
                    up = (0, 1, 0)
                elif view["camera"] in ("overview", "fire"):
                    eye, focus = map(np.array, views[view["camera"]])
                elif view["camera"] == "onboard":
                    q = orientations[j][[1, 2, 3, 0]]
                    rotation = rotation_xyzw(q)
                    eye = focus + rotation @ np.array([0.12 * MISSION_VISUAL_SCALE, 0, -0.03])
                    focus = eye + rotation @ np.array([0.8, 0, -0.12])
                else:
                    yaw, pitch = np.radians([view["yaw"], view["pitch"]])
                    distance = view["distance"]
                    eye = focus + distance * np.array(
                        [np.cos(yaw) * np.cos(pitch), np.sin(yaw) * np.cos(pitch), np.sin(pitch)]
                    )
                    eye[2] = max(0.8, eye[2])
                if view["interactive"]:
                    focus = focus + np.array([view["pan_x"], view["pan_y"], 0.0])
                    yaw, pitch = np.radians([view["yaw"], view["pitch"]])
                    eye = focus + view["distance"] * np.array(
                        [np.cos(yaw) * np.cos(pitch), np.sin(yaw) * np.cos(pitch), np.sin(pitch)]
                    )
                    eye[2] = max(4.0, eye[2])
                camera_op.Set(
                    Gf.Matrix4d()
                    .SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, focus)), Gf.Vec3d(*up))
                    .GetInverse()
                )
                sync_world_visuals(now, eye)
                render_started = time.monotonic()
                world.render()
                render_seconds = time.monotonic() - render_started
                pixels = np.asarray(rgb.get_data())
                jpeg = ir_jpeg = None
                thermal_meta = {"radiometric": False}
                phase = (
                    "Paused"
                    if paused
                    else "Mission complete"
                    if swarm.completed_at is not None
                    else "Swarm mission active"
                    if all(p.armed and p.offboard_active for p in pilots)
                    else "PX4 preflight and takeoff"
                )
                if pixels.size:
                    rendered_frames += 1
                    # A manual orbit can legitimately end up inside geometry.
                    dark_frames += not view["interactive"] and float(pixels[::16, ::16, :3].mean()) < 8
                    projector = last_projector = Projector(eye, focus, up, focal=focal, aperture=aperture)
                    measured = {key: positions[n] for n, key in enumerate(ids)}
                    frame = draw_overlay(
                        pixels[:, :, :3].copy(), projector, swarm, measured, phase=phase, selected=view["drone"]
                    )
                    image = Image.fromarray(frame)
                    buffer = io.BytesIO()
                    image.save(buffer, format="JPEG", quality=82)
                    jpeg = buffer.getvalue()
                    if time.monotonic() - last_video >= 0.1:
                        video.append_data(frame)
                        video_index.write(json.dumps({"frame": video_frame, "simulation_time": now}) + "\n")
                        video_frame += 1
                        last_video = time.monotonic()
                    if hub.frame_id % 25 == 0:
                        image.save(hub.output / "latest.jpg")
                rows = []
                planned = {row["id"]: row for row in swarm.drones_view()}
                for j, key in enumerate(ids):
                    rows.append(
                        dict(
                            asdict(mission.states[key]),
                            **planned[key],
                            position=positions[j].tolist(),
                            armed=pilots[j].armed,
                            offboard=pilots[j].offboard_active,
                            actuator_packets=pilots[j].stats["actuator_packets"],
                        )
                    )
                decision_rows = [r for r in swarm.log.rows if r["kind"] not in ("delivered", "knowledge")][-14:]
                hub.publish(
                    {
                        "phase": phase,
                        "time": now,
                        "paused": paused,
                        "drones": rows,
                        "incidents": swarm.incidents_view(),
                        "world": swarm.world.records(),
                        "decisions": decision_rows,
                        "events": events[-6:],
                        "command_results": [
                            {key: entry[key] for key in ("request_id", "sequence", "action", "result")}
                            for entry in accepted[-16:]
                        ],
                        "mission": {
                            "completed_at": swarm.completed_at,
                            "policy": swarm.policy_name,
                            "sensor": swarm.sensor.sensor,
                        },
                        "radio": asdict(mission.mesh.stats),
                        "mesh": mesh_view(mission),
                        "camera": view,
                        "scene": scene,
                        "thermal": thermal_meta,
                        "stream": {
                            "target_fps": render_hz,
                            "rgb": "960x540",
                            "ir": "640x360",
                            "latest_only": True,
                        },
                    },
                    jpeg,
                    ir_jpeg,
                )
                render_metrics.write(
                    json.dumps(
                        {
                            "simulation_time": now,
                            "wall_time": time.time(),
                            "frame_seconds": time.monotonic() - frame_started,
                            "render_seconds": render_seconds,
                        }
                    )
                    + "\n"
                )
                render_metrics.flush()
                last_frame = frame_started
                last_render_tick = ticks
        summary = dict(
            swarm.summary(),
            physics_minimum_separation_m=min_separation,
            minimum_terrain_clearance_m=terrain_clearance,
            visibility=probes,
            rendered_frames=rendered_frames,
            dark_frames=int(dark_frames),
        )
        (hub.output / "mission-summary.json").write_text(json.dumps(summary, indent=2))
        acceptance = evaluate(swarm.log.rows, summary)
        (hub.output / "mission-acceptance.json").write_text(json.dumps(acceptance, indent=2))
        return {
            "sim_time_seconds": ticks / 250,
            "drones": count,
            "px4": [p.stats for p in pilots],
            "minimum_separation_m": min_separation,
            "commands": accepted,
            "scene": scene,
            "physical_payload_kg": 0,
            "capacity": "scenario units; virtual work only, no physical release",
            "detector": swarm.sensor.sensor,
            "mission_acceptance": acceptance,
            "completed": True,
            "motor_source": "PX4 HIL_ACTUATOR_CONTROLS",
            "policy": swarm.policy_name,
        }
    finally:
        motor_io.shutdown(wait=True)
        for pilot in pilots:
            pilot.close()
        render_metrics.close()
        video.close()
        video_index.close()
        telemetry.close()
        physics_log.close()
        command_log.close()
        decisions.close()


def main():
    import argparse
    import multiprocessing

    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--duration", type=int, default=600)
    parser.add_argument("--drones", type=int, default=6)
    parser.add_argument("--render-hz", type=float, default=15.0)
    parser.add_argument("--policy", choices=("baseline", "learned"), default="baseline")
    parser.add_argument("--world", choices=("city", "wildland"), default="city")
    args = parser.parse_args()
    if (
        not args.run_id.replace("-", "").isalnum()
        or not 30 <= args.duration <= 1200
        or not 2 <= args.drones <= 8
        or not 5 <= args.render_hz <= 30
    ):
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
            str(path.relative_to(source)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in source.rglob("*.py")
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
                "disable_viewport_updates": True,
                "renderer": "RayTracedLighting",
                "width": 960,
                "height": 540,
                "multi_gpu": False,
                "fast_shutdown": True,
            }
        )
        import carb

        settings = carb.settings.get_settings()
        pacing = {"main_limit_before": settings.get("/app/runLoops/main/rateLimitEnabled")}
        settings.set_bool("/app/runLoops/main/rateLimitEnabled", False)
        settings.set_bool("/app/runLoops/present/rateLimitEnabled", False)
        pacing["main_limit_after"] = settings.get("/app/runLoops/main/rateLimitEnabled")
        (output / "pacing.json").write_text(json.dumps(pacing, indent=2))
        report = run_world(application, hub, args.drones, args.render_hz, args.policy, args.world)
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

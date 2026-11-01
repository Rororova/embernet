"""Isaac 6.x PhysX flight with bounded, rotor-allocated forces and measured sensor output."""

import json
import time

import numpy as np

from .controller import GeometricController, rotation_xyzw
from .rotors import RotorAllocator


def run_native_trial(application, output, asset_root):
    import imageio.v2 as imageio
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.prims import RigidPrim
    from PIL import Image
    from pxr import Gf, UsdGeom

    from ..real_perception import FireDetector, annotate
    from .native_airframe import create_airframe
    from .projection import optical_pose_from_usd, project_depth_pixel
    from .scene import build_field_scene

    start = time.monotonic()
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    scene = build_field_scene(world.stage, asset_root)
    create_airframe(world.stage, "/World/Drone/body", (0, 0, 0.35))
    body = world.scene.add(RigidPrim("/World/Drone/body", name="research_quad"))
    camera = rep.create.camera(position=(9, -12, 5), look_at=(2, 0, 1.6), focal_length=32)
    render = rep.create.render_product(camera, (960, 544))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(render)
    follow_camera = UsdGeom.Camera.Define(world.stage, "/World/FollowCamera")
    follow_camera.CreateFocalLengthAttr(35)
    follow_camera.CreateHorizontalApertureAttr(20.955)
    follow_camera.CreateVerticalApertureAttr(20.955 * 544 / 960)
    follow_transform = follow_camera.MakeMatrixXform()
    follow_render = rep.create.render_product(str(follow_camera.GetPath()), (960, 544))
    follow_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    follow_rgb.attach(follow_render)
    sensor = UsdGeom.Camera.Define(world.stage, "/World/Drone/body/NadirCamera")
    sensor.AddTranslateOp().Set((0, 0, -0.2))
    sensor.CreateFocalLengthAttr(18)
    sensor.CreateHorizontalApertureAttr(20.955)
    sensor.CreateVerticalApertureAttr(20.955 * 360 / 640)
    nadir = rep.create.render_product(str(sensor.GetPath()), (640, 360))
    sensor_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    sensor_depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    sensor_rgb.attach(nadir)
    sensor_depth.attach(nadir)
    world.reset()
    world.play()
    controller, allocator = GeometricController(max_speed=3), RotorAllocator()
    records, frames = [], []
    with (output / "telemetry.jsonl").open("w") as stream:
        for index in range(4500):
            t = index / 250
            position, orientation = body.get_world_poses()
            velocity = body.get_velocities()[0]
            p, q = position[0], orientation[0][[1, 2, 3, 0]]  # Core uses wxyz; control uses xyzw.
            rotation = rotation_xyzw(q)
            target = np.array([0, 0, 3] if t < 6 else [5, 0, 3], float)
            thrust, torque = controller.wrench(p, velocity[:3], q, rotation.T @ velocity[3:], target)
            motors, wrench = allocator.allocate(thrust, torque)
            # Sum of four local rotor forces and arm/yaw moments; PhysX integrates the resulting wrench.
            wind = np.array([0.8, 0.25, 0]) if 8 <= t < 12 else np.zeros(3)
            force = np.array([0, 0, wrench[0]]) + rotation.T @ (wind - 0.12 * velocity[:3])
            body.apply_forces_and_torques_at_pos(
                forces=force[None].astype(np.float32),
                torques=wrench[None, 1:].astype(np.float32),
                is_global=False,
            )
            world.step(render=False)
            if index % 8 == 0:
                eye = p + np.array([2.1, -3.1, 1.3])
                follow_transform.Set(
                    Gf.Matrix4d()
                    .SetLookAt(Gf.Vec3d(*map(float, eye)), Gf.Vec3d(*map(float, p)), Gf.Vec3d(0, 0, 1))
                    .GetInverse()
                )
                world.render()
            if not np.isfinite(p).all() or p[2] < -0.5 or np.linalg.norm(p) > 80:
                raise RuntimeError(f"Measured flight left test bounds: {p}")
            if index % 10 == 0:
                row = {
                    "time": t,
                    "position": p.tolist(),
                    "quaternion_xyzw": q.tolist(),
                    "velocity": velocity[:3].tolist(),
                    "target": target.tolist(),
                    "rotors_rad_s": motors.tolist(),
                    "external_force_world_n": wind.tolist(),
                }
                records.append(row)
                stream.write(json.dumps(row) + "\n")
            if index % 24 == 0:
                pixels = np.asarray(follow_rgb.get_data())
                if pixels.size:
                    frames.append(pixels[:, :, :3].copy())
    # Render without advancing physical time so sensor RGB/depth and calibration have the same stamp.
    world.pause()
    for _ in range(8):
        world.render()
    pixels = np.asarray(rgb.get_data())[:, :, :3]
    observed_rgb, depth = np.asarray(sensor_rgb.get_data())[:, :, :3], np.asarray(sensor_depth.get_data())
    Image.fromarray(pixels).save(output / "rgb.png")
    Image.fromarray(np.asarray(follow_rgb.get_data())[:, :, :3]).save(output / "follow.png")
    Image.fromarray(observed_rgb).save(output / "onboard-rgb.png")
    np.save(output / "onboard-depth.npy", depth)
    position, orientation = body.get_world_poses()
    pose = np.eye(4)
    pose[:3, :3] = rotation_xyzw(orientation[0][[1, 2, 3, 0]])
    pose[:3, 3] = position[0] + pose[:3, :3] @ np.array([0, 0, -0.2])
    k = np.array([[640 * 18 / 20.955, 0, 320], [0, 640 * 18 / 20.955, 180], [0, 0, 1]])
    optical = optical_pose_from_usd(pose)
    center_depth = float(depth[180, 320])
    center_ground = project_depth_pixel((320, 180), center_depth, k, optical)
    calibration = {
        "intrinsics": k.tolist(),
        "world_from_optical": optical.tolist(),
        "depth": "distance_to_image_plane, meters",
        "stamp": 18.0,
        "pose_source": "Measured PhysX body state plus camera extrinsics",
        "center_projected_world": center_ground.tolist(),
    }
    (output / "onboard-calibration.json").write_text(json.dumps(calibration, indent=2))
    observations = FireDetector("/opt/fire-smoke.onnx").predict(Image.fromarray(observed_rgb))
    (output / "onboard-perception.json").write_text(json.dumps(observations, indent=2))
    annotate(Image.fromarray(observed_rgb), observations["detections"]).save(
        output / "onboard-detections.png"
    )
    if frames:
        imageio.mimwrite(
            output / "flight.mp4", frames, fps=250 / 24, codec="libx264", quality=8, macro_block_size=1
        )
    hover = [np.linalg.norm(np.array(r["position"]) - r["target"]) for r in records if 4 <= r["time"] < 6]
    waypoint = [np.linalg.norm(np.array(r["position"]) - r["target"]) for r in records if r["time"] >= 15]
    report = {
        "engine": "Isaac Sim 6.2.0 / PhysX",
        "controller": "EMBERNET geometric rotor-wrench controller",
        "pegasus_running": False,
        "px4_running": False,
        "hardware_actuation": False,
        "physics_hz": 250,
        "physics_steps": 4500,
        "measured_sim_time_seconds": float(world.current_time),
        "duration_sim_seconds": 18,
        "elapsed_seconds": time.monotonic() - start,
        "airframe_mass_kg": 1.5,
        "payload_liters": 0,
        "disturbance": "World force [0.8, 0.25, 0] N applied during 8–12 simulated seconds",
        "samples": len(records),
        "frames": len(frames),
        "hover_mean_error_m": float(np.mean(hover)),
        "waypoint_mean_error_m": float(np.mean(waypoint)),
        "final_position": position[0].tolist(),
        "scene": scene,
        "onboard_detector_candidates": len(observations["detections"]),
        "center_depth_m": center_depth,
        "ground_projection_error_m": abs(float(center_ground[2])),
        "flight_pass": bool(np.mean(hover) < 0.5 and np.mean(waypoint) < 0.7 and abs(center_ground[2]) < 0.3),
        "limitation": "Unloaded research quad with estimated inertia; not firefighting hardware or calibrated thermal.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report

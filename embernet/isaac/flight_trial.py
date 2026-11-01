"""Bounded rotor-force flight trial. Called only inside a running Isaac application."""

import json
import sys
import time
from pathlib import Path


def run_flight_trial(application, output, asset_root=None):
    sys.path.insert(0, "/opt/pegasus/extensions/pegasus.simulator")
    import imageio.v2 as imageio
    import numpy as np
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from pegasus.simulator.logic.interface.pegasus_interface import PegasusInterface
    from pegasus.simulator.logic.vehicles.multirotor import Multirotor, MultirotorConfig
    from pegasus.simulator.params import ROBOTS
    from PIL import Image
    from pxr import Usd, UsdGeom

    from .pegasus_backend import RotorWaypointBackend
    from .projection import optical_pose_from_usd
    from .scene import build_field_scene

    start = time.monotonic()
    output = Path(output)
    pg = PegasusInterface()
    pg._world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    world = pg.world
    scene = build_field_scene(world.stage, asset_root)
    backend = RotorWaypointBackend()
    config = MultirotorConfig()
    config.backends = [backend]
    Multirotor("/World/iris", ROBOTS["Iris"], 0, [0, 0, 0.15], [0, 0, 0, 1], config=config)
    # Body-fixed nadir camera: USD cameras look along -Z, which points down in FLU.
    onboard_camera = UsdGeom.Camera.Define(world.stage, "/World/iris/body/OnboardCamera")
    onboard_camera.AddTranslateOp().Set((0, 0, -0.08))
    onboard_camera.CreateFocalLengthAttr(18)
    onboard_camera.CreateHorizontalApertureAttr(20.955)
    onboard_camera.CreateVerticalApertureAttr(20.955 * 360 / 640)
    onboard_render = rep.create.render_product(str(onboard_camera.GetPath()), (640, 360))
    onboard_rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    onboard_depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    onboard_rgb.attach(onboard_render)
    onboard_depth.attach(onboard_render)
    camera = rep.create.camera(position=(11, -15, 7), look_at=(2, 0, 2), focal_length=28)
    render = rep.create.render_product(camera, (960, 540))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    rgb.attach(render)
    depth.attach(render)
    camera_path = camera.get_output_prims()["prims"][0].GetPath()
    world.reset()
    world.play()
    frames, records = [], []
    with (output / "telemetry.jsonl").open("w", encoding="utf-8") as stream:
        # Six seconds settle; six seconds travel; six seconds settle at the waypoint.
        for index in range(4500):
            t = index / 250
            backend.target = np.array([0, 0, 3] if t < 6 else [5, 0, 3], float)
            world.step(render=False)
            if index % 8 == 0:
                world.render()
            state = backend.state
            if state is None:
                continue
            position = np.asarray(state.position)
            if not np.isfinite(position).all() or position[2] < -0.5 or np.linalg.norm(position) > 100:
                raise RuntimeError(f"Flight left test bounds: {position}")
            if index % 10 == 0:
                row = {
                    "time": t,
                    "position": position.tolist(),
                    "quaternion_xyzw": state.attitude.tolist(),
                    "velocity": state.linear_velocity.tolist(),
                    "target": backend.target.tolist(),
                    "rotors_rad_s": backend.rotors.tolist(),
                }
                records.append(row)
                stream.write(json.dumps(row) + "\n")
            if index % 24 == 0:
                pixels = np.asarray(rgb.get_data())
                if pixels.size:
                    frames.append(pixels[:, :, :3].copy())
    for _ in range(8):
        application.update()
    pixels = np.asarray(rgb.get_data())[:, :, :3]
    distance = np.asarray(depth.get_data())
    Image.fromarray(pixels).save(output / "rgb.png")
    np.save(output / "depth.npy", distance)
    sensor_pixels = np.asarray(onboard_rgb.get_data())[:, :, :3]
    sensor_distance = np.asarray(onboard_depth.get_data())
    Image.fromarray(sensor_pixels).save(output / "onboard-rgb.png")
    np.save(output / "onboard-depth.npy", sensor_distance)
    # Query the dynamic body's measured orientation and location for the sensor pose.
    from ..real_perception import FireDetector, annotate
    from .controller import rotation_xyzw

    world_from_onboard = np.eye(4)
    world_from_onboard[:3, :3] = rotation_xyzw(backend.state.attitude)
    world_from_onboard[:3, 3] = backend.state.position + world_from_onboard[:3, :3] @ np.array([0, 0, -0.08])
    sensor_calibration = {
        "intrinsics": [[640 * 18 / 20.955, 0, 320], [0, 640 * 18 / 20.955, 180], [0, 0, 1]],
        "world_from_optical": optical_pose_from_usd(world_from_onboard).tolist(),
        "depth": "distance_to_image_plane in meters",
        "stamp": 18.0,
        "pose_source": "Pegasus measured body state; body-fixed camera extrinsics",
    }
    (output / "onboard-calibration.json").write_text(json.dumps(sensor_calibration, indent=2))
    observed = FireDetector("/opt/fire-smoke.onnx").predict(Image.fromarray(sensor_pixels))
    (output / "onboard-perception.json").write_text(json.dumps(observed, indent=2))
    annotate(Image.fromarray(sensor_pixels), observed["detections"]).save(output / "onboard-detections.png")
    # USD's row-vector matrix is transposed for the project's column-vector optics convention.
    camera_prim = world.stage.GetPrimAtPath(camera_path)
    world_from_usd = np.asarray(
        UsdGeom.Xformable(camera_prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    ).T
    schema = UsdGeom.Camera(camera_prim)
    f = schema.GetFocalLengthAttr().Get()
    aperture = schema.GetHorizontalApertureAttr().Get()
    intrinsics = [[960 * f / aperture, 0, 480], [0, 960 * f / aperture, 270], [0, 0, 1]]
    calibration = {
        "intrinsics": intrinsics,
        "world_from_optical": optical_pose_from_usd(world_from_usd).tolist(),
        "depth": "distance_to_image_plane, meters",
        "rgb": "RTX render, not thermal",
    }
    (output / "calibration.json").write_text(json.dumps(calibration, indent=2))
    if frames:
        imageio.mimwrite(output / "flight.mp4", frames, fps=250 / 24, codec="libx264", quality=8)
    hover = [np.linalg.norm(np.array(r["position"]) - r["target"]) for r in records if 4 <= r["time"] < 6]
    waypoint = [np.linalg.norm(np.array(r["position"]) - r["target"]) for r in records if r["time"] >= 15]
    report = {
        "engine": "Isaac Sim 5.1.0 / PhysX / Pegasus v5.1.0",
        "controller": "EMBERNET geometric rotor controller",
        "px4_running": False,
        "hardware_actuation": False,
        "physics_hz": 250,
        "duration_sim_seconds": 18,
        "elapsed_seconds": time.monotonic() - start,
        "airframe_mass_kg": 1.5,
        "payload_liters": 0,
        "samples": len(records),
        "frames": len(frames),
        "onboard_detector_candidates": len(observed["detections"]),
        "sensor_depth_median_m": float(np.median(sensor_distance[np.isfinite(sensor_distance)])),
        "hover_mean_error_m": float(np.mean(hover)),
        "waypoint_mean_error_m": float(np.mean(waypoint)),
        "final_position": records[-1]["position"],
        "scene": scene,
        "flight_pass": bool(np.mean(hover) < 0.5 and np.mean(waypoint) < 0.7),
        "limitation": "Unloaded Iris; not validation of a firefighting aircraft, PX4 or real fire perception.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report

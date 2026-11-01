"""Isolate Kit native code from the Modal worker so a crash cannot resubmit a trial."""

import argparse
import json
import os
import time
import traceback
from importlib.metadata import version
from pathlib import Path


def boot(application, output):
    import numpy as np
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import DynamicCuboid
    from PIL import Image
    from pxr import UsdLux

    world = World(physics_dt=1 / 120, rendering_dt=1 / 30, stage_units_in_meters=1)
    world.scene.add_default_ground_plane()
    UsdLux.DomeLight.Define(world.stage, "/World/TestLight").CreateIntensityAttr(1000)
    cube = world.scene.add(
        DynamicCuboid(
            prim_path="/World/FallingCube",
            name="falling_cube",
            position=np.array([0.0, 0.0, 2.0]),
            scale=np.ones(3),
            mass=1.0,
            color=np.array([0.8, 0.2, 0.04]),
        )
    )
    camera = rep.create.camera(position=(5, -5, 3), look_at=(0, 0, 1))
    render = rep.create.render_product(camera, (640, 480))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
    rgb.attach(render)
    depth.attach(render)
    world.reset()
    world.play()
    trajectory = []
    for index in range(240):
        world.step(render=False)
        if index % 4 == 0:
            world.render()
        if index % 12 == 0:
            trajectory.append(cube.get_world_pose()[0].tolist())
    world.pause()
    for _ in range(8):
        world.render()
    pixels, distance = np.asarray(rgb.get_data()), np.asarray(depth.get_data())
    final = cube.get_world_pose()[0].tolist()
    Image.fromarray(pixels[:, :, :3]).save(output / "rgb.png")
    np.save(output / "depth.npy", distance)
    return {
        "engine": f"Isaac Sim {version('isaacsim')} / PhysX",
        "final_position": final,
        "trajectory": trajectory,
        "rgb_shape": list(pixels.shape),
        "rgb_std": float(pixels[:, :, :3].std()),
        "finite_depth_pixels": int(np.isfinite(distance).sum()),
        "gravity_collision_pass": bool(0.25 < final[2] < 0.8),
        "render_pass": bool(pixels.size and pixels[:, :, :3].std() > 1),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("boot", "flight", "fleet", "px4"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED") != "YES":
        raise RuntimeError("Explicit NVIDIA license acknowledgement required")
    start = time.monotonic()
    from isaacsim import SimulationApp

    application = SimulationApp(
        {
            "headless": True,
            "renderer": "RayTracedLighting",
            "width": 960,
            "height": 540,
            "multi_gpu": False,
            "fast_shutdown": True,
        }
    )
    try:
        if args.mode == "boot":
            report = boot(application, args.output)
        elif args.mode == "px4":
            from .px4_trial import run_px4_trial

            report = run_px4_trial(application, args.output, "/opt/embernet-assets")
        elif args.mode == "fleet":
            from .fleet_trial import run_fleet_trial

            report = run_fleet_trial(application, args.output, "/opt/embernet-assets")
        else:
            if version("isaacsim").startswith("5.1"):
                from .flight_trial import run_flight_trial

                report = run_flight_trial(application, args.output, "/opt/embernet-assets")
            else:
                from .native_trial import run_native_trial

                report = run_native_trial(application, args.output, "/opt/embernet-assets")
        report["total_elapsed_seconds"] = time.monotonic() - start
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
        print("EMBERNET_RESULT " + json.dumps(report), flush=True)
        passed = (
            report["gravity_collision_pass"] and report["render_pass"]
            if args.mode == "boot"
            else report["fleet_pass"]
            if args.mode == "fleet"
            else report["flight_pass"]
        )
        if not passed:
            raise RuntimeError("Isaac trial did not meet its recorded acceptance thresholds")
    except BaseException:
        failure = traceback.format_exc()
        (args.output / "exception.txt").write_text(failure)
        print(failure, flush=True)
        raise
    finally:
        application.close()


if __name__ == "__main__":
    main()

"""Bounded wildland look-development render: fixed views, timings and logs, no flight or mission."""

import argparse
import json
import os
import subprocess
import time
import traceback
from pathlib import Path

import numpy as np

from .wildland_terrain import (
    IGNITION,
    MEADOW,
    place_trees,
    place_understory,
    road_distance,
    terrain_height,
)


def ground(x, y, above):
    return (float(x), float(y), float(terrain_height(x, y)) + above)


def forest_view():
    """Stand in a clear gap among stems and plants, looking along the nearest dense stand."""
    trees, plants = place_trees(), place_understory()
    x, y = (values.ravel() for values in np.meshgrid(np.arange(590.0, 700.0, 3.0), np.arange(690.0, 800.0, 3.0)))
    near = (np.abs(trees["x"] - 645) < 120) & (np.abs(trees["y"] - 745) < 120)
    stems = np.hypot(x[:, None] - trees["x"][near], y[:, None] - trees["y"][near])
    shrubs = np.hypot(x[:, None] - plants["x"][:, None].T, y[:, None] - plants["y"][:, None].T)
    keep = (stems.min(axis=1) > 9) & (shrubs.min(axis=1) > 3) & (road_distance(x, y) > 14)
    band = (stems > 30) & (stems < 70)
    best = int(np.argmax(np.where(keep, band.sum(axis=1), -1)))
    picked = band[best]
    fx = float(trees["x"][near][picked].mean())
    fy = float(trees["y"][near][picked].mean())
    return ground(x[best], y[best], 1.8), ground(fx, fy, 6)


def views():
    ix, iy = IGNITION
    mx, my, _ = MEADOW
    return {
        "fire": (ground(ix + 42, iy - 62, 30), ground(ix, iy, 8), 24),
        "firefar": (ground(ix - 80, iy - 150, 45), ground(ix, iy, 14), 28),
        "aerial": (ground(120, 80, 330), ground(620, 640, 40), 24),
        "bird": (ground(400, 400, 640), ground(400, 401, 0), 24),
        "ridge": (ground(ix - 260, iy - 300, 130), ground(ix, iy, 30), 28),
        "onboard": (ground(ix - 150, iy - 120, 60), ground(ix, iy, 10), 18),
        "meadow": (ground(mx - 95, my - 110, 1.7), ground(mx + 60, my + 70, 6), 28),
        "forest": (*forest_view(), 22),
        "road": (ground(642, 480, 1.9), ground(690, 560, 4), 26),
    }


def gpu_memory():
    return subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.used,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    ).stdout.strip()


def settle(world, frames=4):
    import omni.usd

    context = omni.usd.get_context()
    started = time.monotonic()
    while time.monotonic() - started < 150:
        world.render()
        loading = context.get_stage_loading_status()[2]
        if not loading:
            break
    for _ in range(frames):
        world.render()
    return time.monotonic() - started


def run(output):
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from PIL import Image
    from pxr import Gf, Usd, UsdGeom

    from .effects import CityFire
    from .wildland_live import prepare_render
    from .wildland_scene import build_wildland

    report = {"stages": {}}
    started = time.monotonic()
    prepare_render()
    import carb

    settings = carb.settings.get_settings()
    settings.set_bool("/rtx/ambientOcclusion/enabled", True)
    settings.set_bool("/rtx/indirectDiffuse/enabled", True)
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    scene = build_wildland(world.stage, "/opt/nvidia-wildland")
    report["scene"] = scene
    fire = CityFire(world.stage, "/World/Fire", ground(*IGNITION, 1.0), "/tmp/embernet-wildland", 3.0)
    report["stages"]["author_seconds"] = time.monotonic() - started
    camera = rep.create.camera(position=(0, 0, 200), look_at=(10, 10, 0), focal_length=24)
    product = rep.create.render_product(camera, (1920, 1080))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(product)
    prim = camera.get_output_prims()["prims"][0]
    transform = UsdGeom.Xformable(prim).MakeMatrixXform()
    # Replicator returns the parent Xform; lens attributes live on the Camera beneath it.
    lens_prim = next(item for item in Usd.PrimRange(prim) if item.IsA(UsdGeom.Camera))
    focal = UsdGeom.Camera(lens_prim).GetFocalLengthAttr()
    UsdGeom.Camera(lens_prim).GetClippingRangeAttr().Set(Gf.Vec2f(0.3, 12000.0))
    world.reset()
    report["stages"]["reset_seconds"] = time.monotonic() - started
    report["stages"]["first_settle_seconds"] = settle(world, 12)
    report["gpu_after_load"] = gpu_memory()
    report["views"] = {}
    for name, (eye, focus, lens) in views().items():
        up = (0, 1, 0) if name == "bird" else (0, 0, 1)
        transform.Set(
            Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*focus), Gf.Vec3d(*up)).GetInverse()
        )
        focal.Set(float(lens))
        fire.update(9.0, eye=eye)
        wait = settle(world, 40)
        pixels = np.asarray(rgb.get_data())
        Image.fromarray(pixels[:, :, :3]).save(output / f"{name}.png")
        frames = []
        for _ in range(24):
            tick = time.monotonic()
            world.render()
            frames.append(time.monotonic() - tick)
        report["views"][name] = {
            "eye": eye,
            "settle_seconds": wait,
            "median_render_ms_1080p": float(np.median(frames) * 1000),
            "mean_luma": float(pixels[:, :, :3].mean()),
            "luma_std": float(pixels[:, :, :3].std()),
        }
    report["gpu_after_views"] = gpu_memory()
    report["elapsed_seconds"] = time.monotonic() - started
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get("EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED") != "YES":
        raise RuntimeError("Explicit NVIDIA license acknowledgement required")
    from isaacsim import SimulationApp

    application = SimulationApp(
        {
            "headless": True,
            "renderer": "RayTracedLighting",
            "width": 1920,
            "height": 1080,
            "multi_gpu": False,
            "fast_shutdown": True,
        }
    )
    try:
        report = run(args.output)
        (args.output / "report.json").write_text(json.dumps(report, indent=2))
        print("EMBERNET_RESULT " + json.dumps(report), flush=True)
    except BaseException:
        (args.output / "exception.txt").write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
        raise
    finally:
        application.close()


if __name__ == "__main__":
    main()

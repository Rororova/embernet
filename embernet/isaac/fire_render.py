"""Bounded city fire look-development: compares Flow tunings on fixed views; no flight or mission."""

import argparse
import copy
import json
import os
import time
import traceback
from pathlib import Path

import numpy as np

from .city_scene import FIRE_POSITION
from .effects import FLOW_GRAVITY_METRES, FLOW_TUNING

SMALL_FIRE = (162.0, 106.0, 1.0)
LARGE_EXTENT = 11.0
SMALL_EXTENT = 2.0
VIEWS = {
    "fire": ((175.0, 92.0, 118.0), FIRE_POSITION, 24),
    "close": ((133.0, 80.0, 116.0), FIRE_POSITION, 24),
    "street": ((96.0, 62.0, 4.0), (150.0, 134.0, 96.0), 20),
    "overview": ((265.0, -35.0, 185.0), (120.0, 132.0, 58.0), 24),
    "bird": ((120.0, 120.0, 235.0), (120.0, 120.0, 0.0), 24),
}


def merged(**changes):
    """Copy the shipped tuning with `{"prim": {"attribute": value}}` overrides, keeping the rest."""
    tuning = copy.deepcopy(FLOW_TUNING)
    for name, values in changes.items():
        tuning.setdefault(name.replace("__", "/"), {}).update(values)
    return tuning


CONFIGS = {
    "base": (FLOW_TUNING, FLOW_GRAVITY_METRES),
    "fine": (merged(flowSimulate={"densityCellSize": 0.22}), FLOW_GRAVITY_METRES),
    "tall": (merged(flowSimulate__advection={"coolingRate": 1.35, "fuelPerBurn": 0.28}), FLOW_GRAVITY_METRES),
}


def run(output, settle_seconds):
    import carb
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from PIL import Image
    from pxr import Usd, UsdGeom

    from .authored_city import build_authored_city
    from .effects import FlowFires, enable_flow

    report = {"configs": {}, "stages": {}}
    started = time.monotonic()
    enable_flow()
    world = World(physics_dt=1 / 250, rendering_dt=1 / 30, stage_units_in_meters=1, device="cpu")
    report["scene"] = build_authored_city(world.stage)
    fires = FlowFires(world.stage)
    fires.add("F01", FIRE_POSITION, LARGE_EXTENT, (0.0, -2.0, 0.0), 3.0)
    fires.add("F02", SMALL_FIRE, SMALL_EXTENT, glow=0.8)
    camera = rep.create.camera(position=(225, 15, 145), look_at=(120, 125, 48), focal_length=24)
    product = rep.create.render_product(camera, (960, 540))
    rgb = rep.AnnotatorRegistry.get_annotator("rgb")
    rgb.attach(product)
    prim = camera.get_output_prims()["prims"][0]
    transform = UsdGeom.Xformable(prim).MakeMatrixXform()
    lens = UsdGeom.Camera(next(p for p in Usd.PrimRange(prim) if p.IsA(UsdGeom.Camera))).GetFocalLengthAttr()
    world.reset()
    settings = carb.settings.get_settings()
    settings.set_bool("/rtx/translucency/enabled", True)
    settings.set_bool("/rtx/post/histogram/enabled", False)
    world.play()
    report["stages"]["ready_seconds"] = time.monotonic() - started
    report["flow_settings"] = {
        key: settings.get(key) for key in ("/rtx/flow/enabled", "/rtx/flow/rayTracedTranslucencyEnabled")
    }

    def frame():
        for _ in range(8):
            world.step(render=False)
        tick = time.monotonic()
        fires.update("F01", True, 1.0, world.current_time)
        fires.update("F02", True, 1.0, world.current_time)
        world.render()
        return time.monotonic() - tick

    for name, (tuning, gravity) in CONFIGS.items():
        fires.tune(tuning, gravity)
        fires.tune({"flowSimulate": {"forceClear": True}})
        frame()
        fires.tune({"flowSimulate": {"forceClear": False}})
        transform.Set(_pose(VIEWS["fire"]))
        lens.Set(24.0)
        timings, wall = [], time.monotonic()
        while time.monotonic() - wall < settle_seconds:
            timings.append(frame())
        report["configs"][name] = {
            "frames": len(timings),
            "median_ms": float(np.median(timings) * 1000),
            "p95_ms": float(np.percentile(timings, 95) * 1000),
            "views": {},
        }
        for label, view in VIEWS.items():
            transform.Set(_pose(view))
            lens.Set(float(view[2]))
            samples = [frame() for _ in range(12)]
            pixels = np.asarray(rgb.get_data())[:, :, :3]
            Image.fromarray(pixels).save(output / f"{name}-{label}.jpg", quality=90)
            report["configs"][name]["views"][label] = {
                "median_ms": float(np.median(samples) * 1000),
                "mean_luma": float(pixels.mean()),
            }
        (output / "report.json").write_text(json.dumps(report, indent=2))
    report["elapsed_seconds"] = time.monotonic() - started
    return report


def _pose(view):
    from pxr import Gf

    eye, focus = view[:2]
    up = (0, 1, 0) if abs(eye[0] - focus[0]) + abs(eye[1] - focus[1]) < 1 else (0, 0, 1)
    return Gf.Matrix4d().SetLookAt(Gf.Vec3d(*eye), Gf.Vec3d(*focus), Gf.Vec3d(*up)).GetInverse()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--settle", type=float, default=14.0)
    args = parser.parse_args()
    if os.environ.get("EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED") != "YES":
        raise RuntimeError("Explicit NVIDIA license acknowledgement required")
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
    try:
        report = run(args.output, args.settle)
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

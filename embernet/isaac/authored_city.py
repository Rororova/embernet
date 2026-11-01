"""NVIDIA architectural assemblies, explicitly converted from centimetres to ENU metres."""

from math import hypot
from pathlib import Path

# Buildings past this range sit behind the visible skyline and are switched off.
CONTEXT_KEEP_METRES = 600.0
CONTEXT_BUILDINGS = "/World/Architecture/City/Model/ce_Context_City_Bldg/Streetnetwork"


def prune_context(stage, center, radius=CONTEXT_KEEP_METRES, parent=CONTEXT_BUILDINGS):
    """Deactivate context buildings outside `radius`; streets and the tower are untouched."""
    from pxr import Usd, UsdGeom

    root = stage.GetPrimAtPath(parent)
    if not root.IsValid():
        raise ValueError(f"Missing context buildings at {parent}")
    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), ["default", "render", "proxy"], useExtentsHint=True)
    kept, removed = 0, 0
    for prim in list(root.GetChildren()):
        bounds = cache.ComputeWorldBound(prim).ComputeAlignedRange()
        if bounds.IsEmpty():
            continue
        middle = bounds.GetMidpoint()
        if hypot(middle[0] - center[0], middle[1] - center[1]) > radius:
            prim.SetActive(False)
            removed += 1
        else:
            kept += 1
    return {"kept": kept, "removed": removed, "radius_m": radius}


def build_authored_city(stage, root="/opt/nvidia-tower"):
    from pxr import Gf, UsdGeom, UsdLux, UsdPhysics

    source = Path(root) / "Demos/AEC/TowerDemo/CityTowerDemopack/Assemblies"
    required = [
        "assembly_BaseBuilding.usd",
        "assembly_Facade02A.usd",
        "assembly_City.usd",
        "assembly_Site.usd",
    ]
    for name in required:
        if not (source / name).is_file():
            raise FileNotFoundError(source / name)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    # Position the authored facade's south face at y=134 and its centre at x=150.
    offset = (132.30857, 140.68655, 0.0)
    for name in required:
        path = "/World/Architecture/" + name.removeprefix("assembly_").removesuffix(".usd")
        placement = UsdGeom.Xform.Define(stage, path)
        placement.AddTranslateOp().Set(Gf.Vec3d(*offset))
        tower = name in required[:2]
        placement.AddScaleOp().Set(Gf.Vec3f(0.01, 0.01, 108 / 7940.224922 if tower else 0.01))
        model = stage.DefinePrim(path + "/Model", "Xform")
        model.GetReferences().AddReference(str(source / name), "/World")
    context = prune_context(stage, (150.0, 134.0))
    # Conservative static proxy; visual CAD geometry never teleports the flight body.
    collision = UsdGeom.Cube.Define(stage, "/World/TowerCollision")
    collision.CreateSizeAttr(1.0)
    collision.AddTranslateOp().Set((150.0, 153.0, 54.0))
    collision.AddScaleOp().Set((44.0, 40.0, 108.0))
    collision.CreateVisibilityAttr("invisible")
    UsdPhysics.CollisionAPI.Apply(collision.GetPrim())
    ground = UsdGeom.Plane.Define(stage, "/World/PhysicsGround")
    ground.CreateAxisAttr("Z")
    ground.CreateWidthAttr(5000.0)
    ground.CreateVisibilityAttr("invisible")
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
    sun = UsdLux.DistantLight.Define(stage, "/World/CitySun")
    sun.CreateIntensityAttr(2600)
    sun.CreateAngleAttr(0.53)
    sun.CreateColorAttr((1.0, 0.94, 0.85))
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set((-42.0, -20.0, -25.0))
    sky = UsdLux.DomeLight.Define(stage, "/World/CitySky")
    sky.CreateIntensityAttr(800)
    sky.CreateColorAttr((0.74, 0.84, 1.0))
    return {
        "scenario": "NVIDIA architectural city / 30th-floor response scenario",
        "authored_source": "NVIDIA City Tower Demo Pack NVD@10011",
        "assemblies": required,
        "units": "Source centimetres explicitly converted to ENU metres",
        "tower_height_m": 108.0,
        "tower_vertical_scale": 108 / 7940.224922,
        "collision": "Conservative 44x40x108 m static tower proxy and flat ground",
        "fire_floor": 30,
        "fire_position": [150.0, 134.0, 104.4],
        "floor_note": "Scenario floor designation; authored tower is scaled to the scenario height",
        "map_size_m": 240,
        "visual_context_extent_m": 1900,
        "context_buildings": context,
    }

"""OpenUSD forest clearing and attributed NVIDIA props. Import after SimulationApp."""

import math
from pathlib import Path

import numpy as np

from ..visual_assets import Mesh, pine


def build_field_scene(stage, asset_root=None, *, offset=(0, 0, 0), clearing=(-14, 19, -20, 12)):
    from pxr import Gf, Usd, UsdGeom, UsdLux, UsdPhysics

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/World/Field")
    root.AddTranslateOp().Set(Gf.Vec3d(*offset))
    rng = np.random.default_rng(41)
    forest = Mesh()
    vegetation = Path(asset_root).parent / "nvidia-vegetation/Black_Oak.usd" if asset_root else None
    detailed = vegetation is not None and vegetation.is_file()
    # A static triangle terrain surface; no default laboratory grid in the forest.
    for x in range(-46, 46, 2):
        for y in range(-46, 46, 2):
            tone = float(rng.uniform(0.91, 1.08))
            color = (*np.clip(np.array([63, 76, 42]) * tone, 0, 255).astype(np.uint8), 255)
            forest.quad((x, y, -0.02), (x + 2, y, -0.02), (x + 2, y + 2, -0.02), (x, y + 2, -0.02), color)
    prototypes = [pine(i) for i in range(3)]
    tree_count = 0
    detailed_trees = 0
    for i in range(180):
        x, y = rng.uniform(-45, 45, 2)
        margin = 10 if detailed else 0
        if (
            clearing[0] - margin < x < clearing[1] + margin
            and clearing[2] - margin < y < clearing[3] + margin
        ):
            continue
        scale, yaw = rng.uniform(0.42, 0.75), rng.uniform(0, 360)
        if detailed:
            tree = UsdGeom.Xform.Define(stage, f"/World/Field/Oak_{i:03}")
            tree.GetPrim().GetReferences().AddReference(vegetation.resolve().as_posix())
            tree.AddTranslateOp().Set((float(x), float(y), 0))
            tree.AddRotateZOp().Set(float(yaw))
            tree.AddScaleOp().Set((scale * 0.01,) * 3)
            tree.GetPrim().SetInstanceable(True)
            trunk = UsdGeom.Cylinder.Define(stage, f"/World/Field/OakTrunkCollider_{i:03}")
            trunk.CreateRadiusAttr(0.3 * scale)
            trunk.CreateHeightAttr(19.74 * scale)
            trunk.AddTranslateOp().Set((float(x), float(y), 9.87 * scale))
            trunk.CreateVisibilityAttr("invisible")
            UsdPhysics.CollisionAPI.Apply(trunk.GetPrim())
            detailed_trees += 1
        else:
            forest.merge(prototypes[i % 3], (x, y, 0), scale, math.radians(yaw))
            tree_count += 1
    # A grounded field station, water tanks and two H pads; geometry has collision.
    forest.box((-8, -14, 1.35), (7, 4, 2.7), (188, 183, 157, 255))
    forest.box((-8, -14, 2.8), (7.6, 4.6, 0.2), (62, 74, 70, 255))
    for x in (-10, -7):
        forest.box((x, -11.98, 1.5), (1.5, 0.03, 0.9), (49, 83, 94, 255))
    for x in (-12.5, -15):
        forest.tube((x, -14, 0), (x, -14, 2.7), 0.8, (151, 173, 175, 255), 24)
    for x in (0, 5):
        # Pads are flush with the ground; aircraft start above the surface once.
        forest.box((x, 0, -0.04), (3.4, 3.4, 0.08), (102, 112, 105, 255))
        for side in (-0.5, 0.5):
            forest.box((x + side, 0, 0.003), (0.16, 1.6, 0.006), (234, 224, 191, 255))
        forest.box((x, 0, 0.003), (1.1, 0.16, 0.006), (234, 224, 191, 255))
    positions, normals, colors = forest.arrays()
    mesh = UsdGeom.Mesh.Define(stage, str(root.GetPath()) + "/ForestAndStation")
    mesh.CreatePointsAttr(positions.tolist())
    mesh.CreateFaceVertexCountsAttr([3] * (len(positions) // 3))
    mesh.CreateFaceVertexIndicesAttr(list(range(len(positions))))
    mesh.CreateNormalsAttr(normals.tolist())
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    srgb = colors[:, :3] / 255
    linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
    mesh.CreateDisplayColorAttr(linear.tolist())
    mesh.GetDisplayColorPrimvar().SetInterpolation(UsdGeom.Tokens.vertex)
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
    sun.CreateIntensityAttr(3000)
    sun.CreateAngleAttr(0.53)
    sun.CreateColorAttr((1.0, 0.88, 0.72))
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set((-28, -35, -20))
    sky = UsdLux.DomeLight.Define(stage, "/World/Sky")
    sky.CreateIntensityAttr(800)
    sky.CreateColorAttr((0.6, 0.73, 0.9))
    included = []
    if asset_root:
        for name, file, placements in (
            (
                "barrier_wall_plastic_orange_a03",
                "sm_barrier_wall_plastic_orange_a03_01.usd",
                [(-4, -6, 0), (0, -6, 0), (4, -6, 0)],
            ),
            ("fireExtinguisher_abc_a03", "sm_fireExtinguisher_abc_a03_01.usd", [(-7, -11.5, 0)]),
        ):
            source = Path(asset_root) / name / "simready_usd" / file
            if not source.is_file():
                raise FileNotFoundError(source)
            for index, position in enumerate(placements):
                transform = UsdGeom.Xform.Define(stage, f"/World/Field/{name}_{index}")
                transform.GetPrim().GetReferences().AddReference(source.resolve().as_posix())
                transform.AddTranslateOp().Set(Gf.Vec3d(*position))
                # Avoid stale nested-prototype paths in the Fabric scene delegate.
                for prim in list(Usd.PrimRange(transform.GetPrim())):
                    if prim.IsInstanceable():
                        prim.SetInstanceable(False)
            included.append(name)
    return {
        "authored_trees": tree_count,
        "nvidia_oak_instances": detailed_trees,
        "nvidia_vegetation_collision": "Trunk proxies; foliage visual only" if detailed else None,
        "static_collision_triangles": len(positions) // 3,
        "nvidia_simready_assets": included,
        "units": "meters, Z up, ENU",
    }

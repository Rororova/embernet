"""Author a small, unloaded research airframe with rigid mass, inertia and collisions."""

from pathlib import Path

import numpy as np

from ..visual_assets import drone

IRIS_MODEL = Path("/opt/embernet-assets/px4-iris/iris.stl")
# Observer legibility only: the shell grows, while mass, inertia and collision stay 1:1.
MISSION_VISUAL_SCALE = 3.0


def stl_mesh(path):
    """Read binary STL without a heavyweight runtime dependency."""
    payload = Path(path).read_bytes()
    if len(payload) < 84:
        raise ValueError("Invalid STL")
    count = int.from_bytes(payload[80:84], "little")
    if len(payload) != 84 + count * 50 or count < 1:
        raise ValueError("Invalid binary STL size")
    dtype = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attr", "<u2")])
    records = np.frombuffer(payload, dtype=dtype, count=count, offset=84)
    points = records["vertices"].reshape(-1, 3).astype(np.float32)
    normals = np.repeat(records["normal"], 3, axis=0).astype(np.float32)
    if not np.isfinite(points).all() or not np.isfinite(normals).all():
        raise ValueError("Nonfinite STL geometry")
    return points, normals


def create_airframe(stage, path, position, model_path=IRIS_MODEL, color="#ff7a2f", visual_scale=1.0):
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics, UsdShade

    root = UsdGeom.Xform.Define(stage, path)
    root.AddTranslateOp().Set(Gf.Vec3d(*position))
    root.AddOrientOp().Set(Gf.Quatf(1, 0, 0, 0))
    UsdPhysics.RigidBodyAPI.Apply(root.GetPrim())
    mass = UsdPhysics.MassAPI.Apply(root.GetPrim())
    mass.CreateMassAttr(1.5)
    mass.CreateCenterOfMassAttr((0, 0, 0))
    mass.CreateDiagonalInertiaAttr((0.029125, 0.029125, 0.055225))
    mass.CreatePrincipalAxesAttr(Gf.Quatf(1, 0, 0, 0))
    collision = UsdGeom.Cube.Define(stage, path + "/BodyCollision")
    collision.CreateSizeAttr(1)
    collision.AddScaleOp().Set((0.35, 0.35, 0.20))
    collision.CreateVisibilityAttr("invisible")
    UsdPhysics.CollisionAPI.Apply(collision.GetPrim())

    def material(name, color, roughness, metallic=0.0, opacity=1.0):
        target = UsdShade.Material.Define(stage, path + "/" + name)
        shader = UsdShade.Shader.Define(stage, path + "/" + name + "/Shader")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
        shader.CreateInput("opacity", Sdf.ValueTypeNames.Float).Set(opacity)
        target.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
        return target

    # A saturated matte shell gives contrast against the dark, dense city behind it.
    tint = tuple((int(color[i : i + 2], 16) / 255) ** 2.2 for i in (1, 3, 5))
    body_material = material("BodyMaterial", tint, 0.45, 0.05)
    accent_material = material("AccentMaterial", (0.95, 0.95, 0.92), 0.4, 0.0)
    rotor_material = material("RotorMaterial", (0.025, 0.03, 0.035), 0.2, 0.5, 0.28)
    shell = path + "/Shell"
    UsdGeom.Xform.Define(stage, shell).AddScaleOp().Set((float(visual_scale),) * 3)
    if Path(model_path).is_file():
        points, normals = stl_mesh(model_path)
        center = (points.min(axis=0) + points.max(axis=0)) / 2
        points[:, :2] -= center[:2]
        mesh = UsdGeom.Mesh.Define(stage, shell + "/IrisVisual")
        mesh.CreatePointsAttr(points.tolist())
        mesh.CreateNormalsAttr(normals.tolist())
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateFaceVertexCountsAttr([3] * (len(points) // 3))
        mesh.CreateFaceVertexIndicesAttr(np.arange(len(points)).tolist())
        mesh.CreateSubdivisionSchemeAttr("none")
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(body_material)
    else:
        positions, normals, colors = drone().arrays()
        mesh = UsdGeom.Mesh.Define(stage, shell + "/Visual")
        mesh.CreatePointsAttr((positions * 0.14).tolist())
        mesh.CreateNormalsAttr(normals.tolist())
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        mesh.CreateFaceVertexCountsAttr([3] * (len(positions) // 3))
        mesh.CreateFaceVertexIndicesAttr(np.arange(len(positions)).tolist())
        mesh.CreateSubdivisionSchemeAttr("none")
        srgb = colors[:, :3] / 255
        linear = np.where(srgb <= 0.04045, srgb / 12.92, ((srgb + 0.055) / 1.055) ** 2.4)
        mesh.CreateDisplayColorAttr(linear.tolist())
        mesh.GetDisplayColorPrimvar().SetInterpolation(UsdGeom.Tokens.vertex)
    top = UsdGeom.Cube.Define(stage, shell + "/TopAccent")
    top.CreateSizeAttr(1)
    top.AddScaleOp().Set((0.09, 0.13, 0.025))
    top.AddTranslateOp().Set((0, 0, 0.057))
    UsdShade.MaterialBindingAPI.Apply(top.GetPrim()).Bind(accent_material)
    for index, (x, y) in enumerate(((0.13, 0.18), (-0.13, 0.18), (0.13, -0.18), (-0.13, -0.18))):
        motor = UsdGeom.Cylinder.Define(stage, shell + f"/Motor{index}")
        motor.CreateRadiusAttr(0.026)
        motor.CreateHeightAttr(0.045)
        motor.AddTranslateOp().Set((x, y, 0.035))
        UsdShade.MaterialBindingAPI.Apply(motor.GetPrim()).Bind(body_material)
        rotor = UsdGeom.Cylinder.Define(stage, shell + f"/Rotor{index}")
        rotor.CreateRadiusAttr(0.12)
        rotor.CreateHeightAttr(0.004)
        rotor.AddTranslateOp().Set((x, y, 0.063))
        UsdShade.MaterialBindingAPI.Apply(rotor.GetPrim()).Bind(rotor_material)
    gimbal = UsdGeom.Sphere.Define(stage, shell + "/Gimbal")
    gimbal.CreateRadiusAttr(0.035)
    gimbal.AddTranslateOp().Set((0.09, 0, -0.065))
    UsdShade.MaterialBindingAPI.Apply(gimbal.GetPrim()).Bind(body_material)
    lens = UsdGeom.Cylinder.Define(stage, shell + "/CameraLens")
    lens.CreateRadiusAttr(0.018)
    lens.CreateHeightAttr(0.018)
    lens.AddTranslateOp().Set((0.12, 0, -0.065))
    lens.AddRotateYOp().Set(90)
    UsdShade.MaterialBindingAPI.Apply(lens.GetPrim()).Bind(material("LensMaterial", (0.015, 0.09, 0.13), 0.08, 0.7))
    return root

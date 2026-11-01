"""A metre-scale city with PBR surfaces and a 30th-floor incident. Import after Kit."""

from pathlib import Path

import numpy as np

CITY_SIZE = 240
FIRE_FLOOR = 30
FLOOR_HEIGHT = 3.6
FIRE_POSITION = (150.0, 134.0, 104.4)
CITY_MATERIALS = ("asphalt_02", "concrete_wall_006", "brick_wall_001")


def _facade_textures(asset_root):
    from PIL import Image, ImageDraw

    output = Path(asset_root) / "city-generated"
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(41)
    for source, floors in (("concrete_wall_006", 12), ("brick_wall_001", 12), ("concrete_wall_006", 30)):
        target = output / f"{source}-facade-{floors}.jpg"
        if target.exists():
            continue
        with Image.open(Path(asset_root) / "city-materials" / source / "diffuse.jpg") as image:
            image = image.convert("RGB").resize((512, 1024))
        image = Image.blend(image, Image.new("RGB", image.size, "#52616a"), 0.28)
        draw = ImageDraw.Draw(image)
        columns, rows = 8, floors
        cell_x, cell_y = 512 / columns, 1024 / rows
        for row in range(rows):
            for column in range(columns):
                x0, y0 = int(column * cell_x + 8), int(row * cell_y + 5)
                x1, y1 = int((column + 1) * cell_x - 8), int((row + 1) * cell_y - 5)
                lit = rng.random() < 0.18
                color = (190, 177, 127) if lit else tuple(rng.integers(24, 66, 3))
                draw.rectangle((x0, y0, x1, y1), fill=color, outline=(112, 128, 134), width=2)
                draw.line(((x0 + x1) // 2, y0, (x0 + x1) // 2, y1), fill=(75, 89, 96), width=1)
        image.save(target, quality=90)
    return output


def _material(stage, path, color, roughness=0.6, metallic=0.0, texture=None):
    from pxr import Sdf, UsdShade

    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/Shader")
    shader.CreateIdAttr("UsdPreviewSurface")
    shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(color)
    shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(roughness)
    shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(metallic)
    if texture:
        texture = Path(texture)
        reader = UsdShade.Shader.Define(stage, path + "/UV")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.String).Set("st")
        diffuse = UsdShade.Shader.Define(stage, path + "/Diffuse")
        diffuse.CreateIdAttr("UsdUVTexture")
        diffuse.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(texture / "diffuse.jpg" if texture.is_dir() else texture))
        diffuse.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.String).Set("sRGB")
        diffuse.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
        shader.GetInput("diffuseColor").ConnectToSource(diffuse.ConnectableAPI(), "rgb")
        if texture.is_dir():
            for name, input_name, value_type, channel in (
                ("roughness", "roughness", Sdf.ValueTypeNames.Float, "r"),
                ("normal", "normal", Sdf.ValueTypeNames.Normal3f, "rgb"),
            ):
                source = texture / f"{name}.jpg"
                if not source.exists():
                    continue
                node = UsdShade.Shader.Define(stage, path + "/" + name.title())
                node.CreateIdAttr("UsdUVTexture")
                node.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(str(source))
                node.CreateInput("sourceColorSpace", Sdf.ValueTypeNames.String).Set("raw")
                node.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.ConnectableAPI(), "result")
                shader.CreateInput(input_name, value_type).ConnectToSource(node.ConnectableAPI(), channel)
    material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(), "surface")
    return material


def _mesh(stage, path, faces, material, collision=False):
    from pxr import Sdf, UsdGeom, UsdPhysics, UsdShade

    positions, normals, uvs, indices, counts = [], [], [], [], []
    for corners, normal, scale in faces:
        base = len(positions)
        positions.extend(corners)
        normals.extend([normal] * 4)
        u, v = scale
        uvs.extend([(0, 0), (u, 0), (u, v), (0, v)])
        indices.extend(range(base, base + 4))
        counts.append(4)
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(positions)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateNormalsAttr(normals)
    mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    primvars = UsdGeom.PrimvarsAPI(mesh)
    primvars.CreatePrimvar("st", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.faceVarying).Set(uvs)
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    if collision:
        UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    return mesh


def _box(stage, path, center, size, material, collision=True, uv_world=(24, 40.8)):
    x, y, z = center
    w, d, h = (value / 2 for value in size)
    x0, x1, y0, y1, z0, z1 = x - w, x + w, y - d, y + d, z - h, z + h
    faces = [
        ([(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0)], (0, 0, -1), (size[0] / 12, size[1] / 12)),
        ([(x0, y1, z1), (x1, y1, z1), (x1, y0, z1), (x0, y0, z1)], (0, 0, 1), (size[0] / 12, size[1] / 12)),
        ([(x0, y0, z1), (x1, y0, z1), (x1, y0, z0), (x0, y0, z0)], (0, -1, 0), (size[0] / uv_world[0], size[2] / uv_world[1])),
        ([(x1, y1, z1), (x0, y1, z1), (x0, y1, z0), (x1, y1, z0)], (0, 1, 0), (size[0] / uv_world[0], size[2] / uv_world[1])),
        ([(x1, y0, z1), (x1, y1, z1), (x1, y1, z0), (x1, y0, z0)], (1, 0, 0), (size[1] / uv_world[0], size[2] / uv_world[1])),
        ([(x0, y1, z1), (x0, y0, z1), (x0, y0, z0), (x0, y1, z0)], (-1, 0, 0), (size[1] / uv_world[0], size[2] / uv_world[1])),
    ]
    return _mesh(stage, path, faces, material, collision)


def _plane(stage, path, center, size, material, uv=(20, 20)):
    x, y, z = center
    w, d = size[0] / 2, size[1] / 2
    return _mesh(
        stage,
        path,
        [([(x - w, y - d, z), (x + w, y - d, z), (x + w, y + d, z), (x - w, y + d, z)], (0, 0, 1), uv)],
        material,
    )


def build_city_scene(stage, asset_root):
    from pxr import UsdGeom, UsdLux, UsdPhysics, UsdShade

    asset_root = Path(asset_root)
    generated = _facade_textures(asset_root)
    materials = asset_root / "city-materials"
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    asphalt = _material(stage, "/World/Materials/Asphalt", (0.15, 0.17, 0.19), texture=materials / "asphalt_02")
    concrete = _material(stage, "/World/Materials/Concrete", (0.5, 0.52, 0.5), texture=materials / "concrete_wall_006")
    glass = _material(stage, "/World/Materials/Glass", (0.08, 0.16, 0.2), 0.18, 0.55)
    metal = _material(stage, "/World/Materials/Metal", (0.12, 0.14, 0.16), 0.28, 0.8)
    white = _material(stage, "/World/Materials/RoadPaint", (0.72, 0.74, 0.68), 0.82)
    yellow = _material(stage, "/World/Materials/LanePaint", (0.8, 0.55, 0.12), 0.8)
    _plane(stage, "/World/City/Asphalt", (120, 120, -0.04), (240, 240), asphalt)
    rng = np.random.default_rng(41)
    building_count = 0
    for x in (30, 90, 150, 210):
        for y in (30, 90, 150, 210):
            if (x <= 90 and y <= 30) or (x == 150 and y == 150):
                continue
            _box(stage, f"/World/City/Block{x}_{y}", (x, y, 0.18), (44, 44, 0.36), concrete, False)
            corridor = x == 150 and y == 90
            height = float(rng.uniform(10, 16) if corridor else rng.uniform(20, 68))
            width, depth = float(rng.uniform(25, 34)), float(rng.uniform(25, 34))
            source = "brick_wall_001" if (x + y) % 120 else "concrete_wall_006"
            facade = _material(
                stage,
                f"/World/Materials/Facade{x}_{y}",
                (0.4, 0.45, 0.48),
                texture=generated / f"{source}-facade-12.jpg",
            )
            _box(stage, f"/World/City/Building{x}_{y}", (x, y, height / 2 + 0.36), (width, depth, height), facade)
            _box(stage, f"/World/City/Roof{x}_{y}", (x, y, height + 0.7), (width + 0.5, depth + 0.5, 0.7), metal, False)
            for unit in range(2):
                _box(stage, f"/World/City/HVAC{x}_{y}_{unit}", (x - 5 + unit * 10, y, height + 1.7), (4, 6, 1.4), metal, False)
            building_count += 1
    highrise_mat = _material(
        stage, "/World/Materials/Highrise", (0.35, 0.42, 0.46), texture=generated / "concrete_wall_006-facade-30.jpg"
    )
    _box(stage, "/World/City/Highrise30", (150, 150, 54.36), (32, 28, 108), highrise_mat, uv_world=(32, 108))
    _box(stage, "/World/City/HighriseCrown", (150, 150, 109.2), (34, 30, 1.7), metal, False)
    _box(stage, "/World/City/HighriseAntenna", (150, 150, 116), (0.6, 0.6, 12), metal, False)
    building_count += 1
    _box(stage, "/World/City/LaunchBlock", (60, 30, 0.12), (76, 44, 0.24), concrete, False)
    _box(stage, "/World/City/FireBlock", (150, 150, 0.18), (44, 44, 0.36), concrete, False)
    for coordinate in (0, 60, 120, 180, 240):
        for offset in range(10, 240, 20):
            _plane(stage, f"/World/City/LaneX{coordinate}_{offset}", (coordinate, offset, 0.012), (0.18, 7), yellow, (1, 1))
            _plane(stage, f"/World/City/LaneY{coordinate}_{offset}", (offset, coordinate, 0.013), (7, 0.18), yellow, (1, 1))
    for x in range(42, 82, 13):
        pad = _material(stage, f"/World/Materials/Pad{x}", (0.14, 0.18, 0.2), 0.5)
        _plane(stage, f"/World/City/Pad{x}", (x, 30, 0.25), (8, 8), pad, (1, 1))
        _box(stage, f"/World/City/PadMark{x}A", (x - 1.5, 30, 0.28), (0.5, 5, 0.04), white, False)
        _box(stage, f"/World/City/PadMark{x}B", (x + 1.5, 30, 0.28), (0.5, 5, 0.04), white, False)
        _box(stage, f"/World/City/PadMark{x}H", (x, 30, 0.28), (3, 0.5, 0.04), white, False)
    car_colors = [(0.35, 0.04, 0.025), (0.035, 0.12, 0.22), (0.55, 0.57, 0.58), (0.03, 0.09, 0.06)]
    for index in range(16):
        x = float(rng.choice([54, 66, 114, 126, 174, 186]))
        y = float(rng.uniform(15, 225))
        paint = _material(stage, f"/World/Materials/Car{index}", car_colors[index % 4], 0.24, 0.65)
        _box(stage, f"/World/City/Car{index}", (x, y, 0.75), (2.1, 4.4, 1.1), paint, False)
        _box(stage, f"/World/City/CarGlass{index}", (x, y - 0.2, 1.45), (1.75, 2.2, 0.65), glass, False)
    for index, (x, y) in enumerate([(55, 45), (65, 105), (115, 65), (125, 165), (175, 125), (185, 205)] * 2):
        pole = UsdGeom.Cylinder.Define(stage, f"/World/City/Streetlight{index}")
        pole.CreateRadiusAttr(0.11)
        pole.CreateHeightAttr(7)
        pole.AddTranslateOp().Set((x, y, 3.5))
        UsdShade.MaterialBindingAPI.Apply(pole.GetPrim()).Bind(metal)
        lamp = UsdGeom.Sphere.Define(stage, f"/World/City/Lamp{index}")
        lamp.CreateRadiusAttr(0.35)
        lamp.AddTranslateOp().Set((x, y, 7))
        UsdShade.MaterialBindingAPI.Apply(lamp.GetPrim()).Bind(white)
    sun = UsdLux.DistantLight.Define(stage, "/World/CitySun")
    sun.CreateIntensityAttr(2600)
    sun.CreateAngleAttr(0.35)
    sun.CreateColorAttr((1.0, 0.86, 0.69))
    UsdGeom.Xformable(sun).AddRotateXYZOp().Set((-32, -28, -25))
    sky = UsdLux.DomeLight.Define(stage, "/World/CitySky")
    sky.CreateIntensityAttr(650)
    sky.CreateColorAttr((0.55, 0.7, 0.9))
    ground = UsdGeom.Plane.Define(stage, "/World/City/PhysicsGround")
    ground.CreateAxisAttr("Z")
    ground.CreateWidthAttr(500)
    ground.CreateVisibilityAttr("invisible")
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim())
    return {
        "scenario": "Metro 30 · 30th-floor high-rise fire",
        "map_size_m": CITY_SIZE,
        "building_count": building_count,
        "fire_floor": FIRE_FLOOR,
        "fire_position": FIRE_POSITION,
        "pbr_materials": list(CITY_MATERIALS),
        "surface_detail": "CC0 PBR asphalt/concrete/brick, procedural facade windows, road markings, vehicles and rooftop equipment",
        "units": "meters, Z up, ENU",
    }

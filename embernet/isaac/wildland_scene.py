"""NVIDIA vegetation on a generated wildland; ground layers blend in one MDL. Import after SimulationApp."""

import shutil
from pathlib import Path

import numpy as np

from .wildland_terrain import (
    HOME,
    IGNITION,
    WILDLAND_SIZE,
    grid_axis,
    ground_masks,
    place_grass,
    place_trees,
    place_understory,
    terrain_height,
)

# Path, authored height (m) and intended height (m). Several source plants are saplings.
TREES = (
    ("Trees/Douglas_Fir.usd", 6.03, 25.0),
    ("Trees/Yellow_Pine.usd", 26.99, 27.0),
    ("Trees/White_Pine.usd", 2.0, 5.5),
    ("Trees/Colorado_Spruce.usd", 3.87, 19.0),
    ("Trees/Douglas_Fir.usd", 6.03, 19.0),
    ("Trees/Black_Oak.usd", 19.74, 16.0),
    ("Trees/Largetooth_Aspen.usd", 7.89, 15.0),
)
UNDERSTORY = (
    ("Shrub/Barberry.usd", 1.14, 1.3),
    ("Shrub/Switchgrass.usd", 1.37, 1.2),
    ("Shrub/Barberry.usd", 1.14, 1.2),
    ("Shrub/Barberry.usd", 1.14, 1.7),
    ("Plant_Tropical/Japanese_Painted_Fern.usd", 0.25, 0.7),
    ("Debris/fallcluster1.usd", 0.04, 0.05),
    ("Debris/fallcluster2.usd", 0.04, 0.05),
) + tuple((f"Rocks/rock_small_{i:02}.usda", 0.14, 0.7) for i in (2, 5, 8, 11, 14))
GRASS = (
    ("Shrub/Grass_Short_A.usd", 0.14, 0.34, 1.0),
    ("Shrub/Grass_Short_B.usd", 0.15, 0.38, 1.1),
    ("Shrub/Switchgrass.usd", 1.37, 0.95),
    ("Shrub/Prairie_Dropseed.usd", 1.5, 0.75),
    ("Shrub/Lupin.usd", 1.14, 0.8),
)
FLATTENED = {
    "Trees/Douglas_Fir.usd",
    "Trees/Yellow_Pine.usd",
    "Trees/White_Pine.usd",
    "Trees/Black_Oak.usd",
    "Shrub/Barberry.usd",
}
NATURAL = ("Dirt", "Grass_Countryside", "Leaves", "Mulch_Brown", "Soil_Rocky")

GROUND_MDL = """mdl 1.6;
import ::anno::*;
import ::df::*;
import ::math::*;
import ::state::*;
import ::tex::*;

float3 sample(uniform texture_2d image, float2 uv) {
    return tex::lookup_float3(image, uv, tex::wrap_repeat, tex::wrap_repeat);
}

// One surface sampled at two rotated scales so a 1 km ground shows no visible tile.
float3 twice(uniform texture_2d image, float2 metres, float size) {
    float2 turned = float2(0.8 * metres.x - 0.6 * metres.y, 0.6 * metres.x + 0.8 * metres.y);
    return math::lerp(sample(image, metres / size), sample(image, turned / (size * 3.37)), 0.42);
}

// Height-aware blend: a soft mask edge breaks up along the layer's own bright detail.
float edge(float weight, float detail) {
    return math::saturate((weight - (1.0 - math::saturate(detail)) * (1.0 - weight)) * 2.2);
}

export material wildland_ground(
    uniform texture_2d mask = texture_2d("./ground-mask.png", ::tex::gamma_linear),
    uniform texture_2d grass_c = texture_2d("./Grass_Countryside/Grass_Countryside_BaseColor.png", ::tex::gamma_srgb),
    uniform texture_2d grass_n = texture_2d("./Grass_Countryside/Grass_Countryside_Normal.png", ::tex::gamma_linear),
    uniform texture_2d grass_o = texture_2d("./Grass_Countryside/Grass_Countryside_ORM.png", ::tex::gamma_linear),
    uniform texture_2d litter_c = texture_2d("./Leaves/Leaves_BaseColor.png", ::tex::gamma_srgb),
    uniform texture_2d litter_n = texture_2d("./Leaves/Leaves_N.png", ::tex::gamma_linear),
    uniform texture_2d litter_o = texture_2d("./Leaves/Leaves_ORM.png", ::tex::gamma_linear),
    uniform texture_2d mulch_c = texture_2d("./Mulch_Brown/Mulch_Brown_baseColor.png", ::tex::gamma_srgb),
    uniform texture_2d mulch_n = texture_2d("./Mulch_Brown/Mulch_Brown_N.png", ::tex::gamma_linear),
    uniform texture_2d mulch_o = texture_2d("./Mulch_Brown/Mulch_Brown_ORM.png", ::tex::gamma_linear),
    uniform texture_2d soil_c = texture_2d("./Soil_Rocky/Soil_Rocky_BaseColor.png", ::tex::gamma_srgb),
    uniform texture_2d soil_n = texture_2d("./Soil_Rocky/Soil_Rocky_N.png", ::tex::gamma_linear),
    uniform texture_2d soil_o = texture_2d("./Soil_Rocky/Soil_Rocky_ORM.png", ::tex::gamma_linear),
    uniform texture_2d dirt_c = texture_2d("./Dirt/Dirt_BaseColor.png", ::tex::gamma_srgb),
    uniform texture_2d dirt_n = texture_2d("./Dirt/Dirt_Normal.png", ::tex::gamma_linear),
    uniform texture_2d dirt_o = texture_2d("./Dirt/Dirt_ORM.png", ::tex::gamma_linear)
) [[ anno::display_name("EMBERNET wildland ground") ]]
= let {
    float2 metres = float2(state::texture_coordinate(0).x, state::texture_coordinate(0).y);
    float4 weights = tex::lookup_float4(
        mask, metres / 800.0, tex::wrap_clip, tex::wrap_clip);

    float macro = sample(soil_c, metres / 211.0).y;
    float duff = math::smoothstep(0.3, 0.62, macro);
    float3 floor_c = math::lerp(twice(mulch_c, metres, 2.6), twice(litter_c, metres, 3.1), duff)
        * float3(0.34, 0.27, 0.19);
    float3 floor_n = math::lerp(twice(mulch_n, metres, 2.6), twice(litter_n, metres, 3.1), duff);
    float3 floor_o = math::lerp(twice(mulch_o, metres, 2.6), twice(litter_o, metres, 3.1), duff);

    float3 grass = twice(grass_c, metres, 4.3) * float3(0.86, 0.72, 0.42);
    float grass_w = edge(weights.x, grass.y * 1.5);
    float3 a_c = math::lerp(floor_c, grass, grass_w);
    float3 a_n = math::lerp(floor_n, twice(grass_n, metres, 4.3), grass_w);
    float3 a_o = math::lerp(floor_o, twice(grass_o, metres, 4.3), grass_w);

    float3 soil = twice(soil_c, metres, 5.7) * float3(0.56, 0.5, 0.43);
    float soil_w = edge(weights.y, soil.y * 1.4);
    float3 b_c = math::lerp(a_c, soil, soil_w);
    float3 b_n = math::lerp(a_n, twice(soil_n, metres, 5.7), soil_w);
    float3 b_o = math::lerp(a_o, twice(soil_o, metres, 5.7), soil_w);

    float3 dirt = twice(dirt_c, metres, 3.9);
    float dirt_w = edge(weights.z, dirt.y * 1.4);
    float3 c_c = math::lerp(b_c, dirt, dirt_w);
    float3 tangent = math::lerp(b_n, twice(dirt_n, metres, 3.9), dirt_w);
    float3 orm = math::lerp(b_o, twice(dirt_o, metres, 3.9), dirt_w);

    // Char and pale ash are derived from the soil detail; there is no separate burn scan.
    float3 cinder = soil * float3(0.055, 0.052, 0.05) + float3(math::pow(soil.y, 4.0) * 0.24);
    float char_w = edge(weights.w, 0.5 + 0.5 * soil.x);
    float3 near_c = math::lerp(c_c, cinder, char_w);
    float2 beyond = math::abs(metres - float2(400.0)) - float2(400.0);
    float far = math::smoothstep(0.0, 600.0, math::max(beyond.x, beyond.y));
    float3 albedo = math::lerp(near_c, float3(0.018, 0.03, 0.014) + near_c * 0.06, far);
    // Dry ground: scanned roughness never drops low enough to read as wet.
    float roughness = math::max(math::lerp(orm.y, 0.95, char_w), 0.72);

    float3 n = (tangent - float3(0.5)) * float3(2.0, 2.0, 2.0);
    float3 shading = math::normalize(
        state::texture_tangent_u(0) * n.x + state::texture_tangent_v(0) * n.y
        + state::normal() * math::max(n.z, 0.25));
    float occlusion = math::lerp(1.0, orm.x, 0.8);
    bsdf matte = df::diffuse_reflection_bsdf(tint: color(albedo * occlusion));
} in material(
    surface: material_surface(
        scattering: df::fresnel_layer(
            ior: 1.45,
            weight: 0.22,
            layer: df::microfacet_ggx_smith_bsdf(
                roughness_u: math::max(roughness * roughness, 0.08)),
            base: matte)),
    geometry: material_geometry(normal: shading));
"""


def _bake_ground(output, asset_root, size=2048):
    from PIL import Image

    natural = Path(asset_root) / "Isaac/6.2/NVIDIA/Materials/Base/Natural"
    ground = Path(output) / "wildland-ground"
    ground.mkdir(parents=True, exist_ok=True)
    for name in NATURAL:
        shutil.copytree(natural / name, ground / name, dirs_exist_ok=True)
    masks = np.clip(ground_masks(size) * 255, 0, 255).astype(np.uint8)
    # Image rows run north to south; MDL v runs south to north.
    Image.fromarray(masks[::-1], "RGBA").save(ground / "ground-mask.png")
    (ground / "wildland_ground.mdl").write_text(GROUND_MDL, encoding="utf-8")
    return ground


def _ground_material(stage, ground):
    from pxr import Sdf, UsdShade

    material = UsdShade.Material.Define(stage, "/World/Wildland/Looks/Ground")
    shader = UsdShade.Shader.Define(stage, "/World/Wildland/Looks/Ground/Shader")
    shader.SetSourceAsset(Sdf.AssetPath((ground / "wildland_ground.mdl").as_posix()), "mdl")
    shader.SetSourceAssetSubIdentifier("wildland_ground", "mdl")
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    material.CreateVolumeOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    material.CreateDisplacementOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    return material


def _terrain_mesh(stage, path, axis_x, axis_y, material=None):
    from pxr import UsdGeom, UsdShade, Vt

    x, y = np.meshgrid(axis_x, axis_y)
    z = np.zeros_like(x)
    for row in range(0, x.shape[0], 128):
        z[row : row + 128] = terrain_height(x[row : row + 128], y[row : row + 128])
    dz_dy, dz_dx = np.gradient(z, axis_y, axis_x)
    normals = np.stack([-dz_dx, -dz_dy, np.ones_like(z)], axis=-1)
    normals /= np.linalg.norm(normals, axis=-1, keepdims=True)
    rows, cols = x.shape
    index = np.arange(rows * cols).reshape(rows, cols)
    quads = np.stack(
        [index[:-1, :-1], index[:-1, 1:], index[1:, 1:], index[1:, :-1]], axis=-1
    ).ravel()
    mesh = UsdGeom.Mesh.Define(stage, path)
    points = np.stack([x, y, z], axis=-1).reshape(-1, 3).astype(np.float32)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
    mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(quads.size // 4, 4, dtype=np.int32)))
    mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(quads.astype(np.int32)))
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreateExtentAttr([tuple(map(float, points.min(0))), tuple(map(float, points.max(0)))])
    if material is not None:
        mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(normals.reshape(-1, 3).astype(np.float32)))
        mesh.SetNormalsInterpolation(UsdGeom.Tokens.vertex)
        st = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
            "st", _texcoord_type(), UsdGeom.Tokens.vertex
        )
        st.Set(Vt.Vec2fArray.FromNumpy(points[:, :2]))
        UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)
    return mesh, int(quads.size // 4)


def _texcoord_type():
    from pxr import Sdf

    return Sdf.ValueTypeNames.TexCoord2fArray


def _flatten_plant(stage, plant, source):
    """Merge nested branch instancers into one mesh per material; RTX pays per instance, not triangle."""
    from pxr import Usd, UsdGeom, UsdShade, Vt

    asset = Usd.Stage.Open(str(source))
    placed = []
    prototype_roots = set()
    for prim in asset.Traverse():
        if not prim.IsA(UsdGeom.PointInstancer):
            continue
        instancer = UsdGeom.PointInstancer(prim)
        roots = instancer.GetPrototypesRel().GetTargets()
        prototype_roots.update(roots)
        parent = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(0)
        indices = instancer.GetProtoIndicesAttr().Get()
        matrices = instancer.ComputeInstanceTransformsAtTime(0, 0)
        for root_index, root_path in enumerate(roots):
            root = asset.GetPrimAtPath(root_path)
            base = UsdGeom.Xformable(root.GetParent()).ComputeLocalToWorldTransform(0).GetInverse()
            for item in Usd.PrimRange(root):
                if item.IsA(UsdGeom.Mesh):
                    local = UsdGeom.Xformable(item).ComputeLocalToWorldTransform(0) * base
                    placed.extend(
                        (item, local * matrix * parent)
                        for matrix, index in zip(matrices, indices)
                        if index == root_index
                    )
    for item in asset.Traverse():
        if item.IsA(UsdGeom.Mesh) and not any(item.GetPath().HasPrefix(r) for r in prototype_roots):
            placed.append((item, UsdGeom.Xformable(item).ComputeLocalToWorldTransform(0)))

    groups, cached = {}, {}
    for item, matrix in placed:
        key = str(item.GetPath())
        if key not in cached:
            mesh = UsdGeom.Mesh(item)
            counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get() or [], dtype=np.int32)
            if not counts.size:
                cached[key] = None
                continue
            indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int32)
            normals = np.asarray(mesh.GetNormalsAttr().Get(), dtype=np.float32)
            if mesh.GetNormalsInterpolation() != UsdGeom.Tokens.faceVarying:
                normals = normals[indices]
            primvar = UsdGeom.PrimvarsAPI(mesh).GetPrimvar("st")
            st = np.asarray(primvar.ComputeFlattened(), dtype=np.float32)
            if primvar.GetInterpolation() != UsdGeom.Tokens.faceVarying:
                st = st[indices]
            bound = UsdShade.MaterialBindingAPI(item).ComputeBoundMaterial()[0].GetPath()
            points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float32)
            cached[key] = (points, counts, indices, normals, st, str(bound))
        if cached[key] is None:
            continue
        points, counts, indices, normals, st, bound = cached[key]
        rows = np.array(matrix, dtype=np.float64)
        spin = rows[:3, :3] / np.cbrt(abs(np.linalg.det(rows[:3, :3])))
        groups.setdefault(bound, []).append(
            (points @ rows[:3, :3] + rows[3, :3], counts, indices, normals @ spin, st)
        )

    for child in stage.GetPrimAtPath(plant).GetChildren():
        if child.GetName() != "Looks":
            child.SetActive(False)
    default = str(asset.GetDefaultPrim().GetPath())
    for number, (bound, parts) in enumerate(groups.items()):
        offsets = np.cumsum([0] + [len(part[0]) for part in parts[:-1]])
        merged = UsdGeom.Mesh.Define(stage, f"{plant}/Merged{number}")
        points = np.concatenate([part[0] for part in parts]).astype(np.float32)
        merged.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
        merged.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.concatenate([p[1] for p in parts])))
        merged.CreateFaceVertexIndicesAttr(
            Vt.IntArray.FromNumpy(np.concatenate([p[2] + o for p, o in zip(parts, offsets)]))
        )
        merged.CreateNormalsAttr(
            Vt.Vec3fArray.FromNumpy(np.concatenate([p[3] for p in parts]).astype(np.float32))
        )
        merged.SetNormalsInterpolation(UsdGeom.Tokens.faceVarying)
        UsdGeom.PrimvarsAPI(merged).CreatePrimvar(
            "st", _texcoord_type(), UsdGeom.Tokens.faceVarying
        ).Set(Vt.Vec2fArray.FromNumpy(np.concatenate([p[4] for p in parts])))
        merged.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        merged.CreateExtentAttr([tuple(map(float, points.min(0))), tuple(map(float, points.max(0)))])
        if bound:
            look = UsdShade.Material(stage.GetPrimAtPath(plant + bound[len(default):]))
            UsdShade.MaterialBindingAPI.Apply(merged.GetPrim()).Bind(look)


def _orientations(data):
    """Yaw about Z, then tilt onto the ground normal when a placement carries one."""
    half = np.radians(data["yaw"]) / 2
    spin = np.stack([np.cos(half), 0 * half, 0 * half, np.sin(half)], axis=-1)
    if "normal" not in data:
        return spin
    n = data["normal"]
    tilt = np.stack([1 + n[:, 2], -n[:, 1], n[:, 0], 0 * n[:, 0]], axis=-1)
    tilt /= np.linalg.norm(tilt, axis=-1, keepdims=True)
    a, b = tilt, spin
    return np.stack(
        [
            a[:, 0] * b[:, 0] - a[:, 3] * b[:, 3],
            a[:, 1] * b[:, 0] + a[:, 2] * b[:, 3],
            a[:, 2] * b[:, 0] - a[:, 1] * b[:, 3],
            a[:, 0] * b[:, 3] + a[:, 3] * b[:, 0],
        ],
        axis=-1,
    )


def _instancer(stage, path, asset_root, table, picks, data):
    """One PointInstancer over referenced NVIDIA plants; source centimetres are converted once."""
    from pxr import Gf, Sdf, UsdGeom, Vt

    instancer = UsdGeom.PointInstancer.Define(stage, path)
    prototypes = instancer.CreatePrototypesRel()
    for index, (asset, source_height, height, *width) in enumerate(table):
        source = Path(asset_root) / "Vegetation" / asset
        if not source.is_file():
            raise FileNotFoundError(source)
        # A wrapper keeps the unit scale apart from transforms some assets author on their root.
        prototype = UsdGeom.Xform.Define(stage, f"{path}/Prototypes/P{index:02}")
        upright = float(height / source_height) * 0.01
        across = float(width[0]) * 0.01 if width else upright
        prototype.AddScaleOp().Set(Gf.Vec3f(across, across, upright))
        plant = UsdGeom.Xform.Define(stage, f"{prototype.GetPath()}/Plant")
        plant.GetPrim().GetReferences().AddReference(source.resolve().as_posix())
        if asset in FLATTENED:
            _flatten_plant(stage, str(plant.GetPath()), source)
        prototypes.AddTarget(Sdf.Path(str(prototype.GetPath())))
    points = np.stack([data["x"], data["y"], data["z"]], axis=-1).astype(np.float32)
    instancer.CreatePositionsAttr(Vt.Vec3fArray.FromNumpy(points))
    instancer.CreateProtoIndicesAttr(Vt.IntArray.FromNumpy(picks.astype(np.int32)))
    instancer.CreateOrientationsAttr(
        Vt.QuathArray([Gf.Quath(float(w), float(x), float(y), float(z)) for w, x, y, z in _orientations(data)])
    )
    uniform = data["scale"].astype(np.float32)
    instancer.CreateScalesAttr(Vt.Vec3fArray.FromNumpy(np.stack([uniform] * 3, axis=-1)))
    reach = 40.0
    instancer.CreateExtentAttr(
        [tuple(map(float, points.min(0) - reach)), tuple(map(float, points.max(0) + reach))]
    )
    return int(points.shape[0])


def _pick_understory(rows):
    roll, forest = rows["roll"], rows["forest"]
    shrubs = np.select(
        [roll < 0.28, roll < 0.46, roll < 0.6, roll < 0.68, roll < 0.82, roll < 0.91],
        [0, 1, 2, 3, 4, 5],
        default=6,
    )
    rocks = 7 + (roll * 1000).astype(int) % 5
    # Boulders favour open ground; litter and ferns stay under the canopy.
    open_rock = (forest < 0.25) & (roll % 0.1 < 0.045)
    return np.where(open_rock, rocks, shrubs)


def _pick_grass(rows):
    roll = rows["roll"]
    return np.select([roll < 0.5, roll < 0.74, roll < 0.9, roll < 0.975], [0, 1, 2, 3], default=4)


def build_wildland(stage, asset_root="/opt/nvidia-wildland", output="/tmp/embernet-wildland", origin=None):
    from pxr import Gf, UsdGeom, UsdLux, UsdPhysics

    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/World/Wildland")
    if origin is not None:
        # The whole map moves; mission, PX4 and safety keep their own coordinates.
        root.AddTranslateOp().Set(Gf.Vec3d(-origin[0], -origin[1], -float(terrain_height(*HOME))))
    ground = _bake_ground(output, asset_root)
    material = _ground_material(stage, ground)
    axis = grid_axis()
    _, quads = _terrain_mesh(stage, "/World/Wildland/Terrain", axis, axis, material)

    # Physics uses its own 10 m static surface; every plant remains visual only.
    coarse = np.linspace(-80.0, WILDLAND_SIZE + 80.0, 137)
    collision, collision_quads = _terrain_mesh(stage, "/World/Wildland/TerrainCollision", coarse, coarse)
    collision.CreateVisibilityAttr("invisible")
    UsdPhysics.CollisionAPI.Apply(collision.GetPrim())
    UsdPhysics.MeshCollisionAPI.Apply(collision.GetPrim()).CreateApproximationAttr("none")

    trees = place_trees()
    understory = place_understory()
    grass = place_grass()
    tree_count = _instancer(stage, "/World/Wildland/Trees", asset_root, TREES, trees["species"], trees)
    understory_count = _instancer(
        stage, "/World/Wildland/Understory", asset_root, UNDERSTORY, _pick_understory(understory), understory
    )
    grass_count = _instancer(stage, "/World/Wildland/Grass", asset_root, GRASS, _pick_grass(grass), grass)

    sun = UsdLux.DistantLight.Define(stage, "/World/Sun")
    sun.CreateIntensityAttr(3000)
    sun.CreateAngleAttr(0.53)
    sun.CreateColorAttr((1.0, 0.86, 0.68))
    UsdGeom.Xformable(sun).AddRotateZYXOp().Set(Gf.Vec3f(0.0, 52.0, 118.0))
    sky = UsdLux.DomeLight.Define(stage, "/World/Sky")
    sky.CreateIntensityAttr(2000)
    sky.CreateTextureFileAttr(
        (Path(asset_root) / "Skies/Cloudy/kloofendal_48d_partly_cloudy_4k.hdr").resolve().as_posix()
    )
    sky.CreateTextureFormatAttr(UsdLux.Tokens.latlong)
    UsdGeom.Xformable(sky).AddRotateXYZOp().Set(Gf.Vec3f(90.0, 0.0, 200.0))

    home = (*HOME, float(terrain_height(*HOME)))
    ignition = (*IGNITION, float(terrain_height(*IGNITION)))
    return {
        "scenario": "NVIDIA vegetation wildland / ridge-line wildfire response scenario",
        "authored_source": "NVIDIA Omniverse Assets/Vegetation, Base/Natural materials and Skies",
        "map_size_m": WILDLAND_SIZE,
        "visual_context_extent_m": float(axis[-1] - axis[0]),
        "terrain_quads": quads,
        "collision_quads": collision_quads,
        "trees": tree_count,
        "understory": understory_count,
        "grass_clumps": grass_count,
        "species": [row[0] for row in TREES + UNDERSTORY + GRASS],
        "home": home,
        "ignition": ignition,
        "units": "Source centimetres explicitly converted to ENU metres",
        "collision": "10 m static terrain mesh; trees, shrubs and rocks have no collision",
    }

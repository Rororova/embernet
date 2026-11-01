"""Fire/smoke visuals: NVIDIA Flow volumes or soft sprites; scenario visuals, never world truth."""

from pathlib import Path

import numpy as np

# Flow's preset is authored in centimetres; these are the metre-scale values that replace it.
FLOW_TUNING = {
    "flowEmitterSphere": {"temperature": 0.55, "coupleRateTemperature": 3.0, "coupleRateFuel": 1.5},
    "flowSimulate": {"densityCellSize": 0.3, "enableVariableTimeStep": True, "forceSimulate": True},
    "flowSimulate/advection": {
        "buoyancyPerTemp": 3.0,
        "buoyancyPerSmoke": 0.3,
        "coolingRate": 1.7,
        "fuelPerBurn": 0.35,
        "gravity": (0.15, 0.04, -1.0),
        "smokePerBurn": 4.0,
        "tempPerBurn": 2.8,
    },
    "flowSimulate/advection/smoke": {"fade": 0.4},
    "flowSimulate/summaryAllocate": {"smokeThreshold": 0.05},
    "flowSimulate/vorticity": {"forceScale": 7.0},
    "flowOffscreen/colormap": {
        "colorScale": 1.2,
        # Temperature ramp: soft grey smoke, deep red, orange, a small yellow core; never white.
        "rgbaPoints": [
            (0.05, 0.05, 0.052, 0.005),
            (0.075, 0.072, 0.07, 0.5),
            (0.06, 0.05, 0.045, 0.55),
            (1.0, 0.12, 0.01, 0.8),
            (7.0, 1.5, 0.06, 0.8),
            (20.0, 8.0, 1.0, 0.7),
        ],
    },
    "flowOffscreen/shadow": {"attenuation": 0.1, "lightDirection": (0.45, -0.55, 0.7)},
    "flowRender/rayMarch": {"attenuation": 0.2},
}
FLOW_GRAVITY_METRES = 28.0


def _effect_textures(asset_root):
    from PIL import Image, ImageFilter

    output = Path(asset_root) / "city-generated"
    output.mkdir(parents=True, exist_ok=True)
    flame_path, smoke_path = output / "flame.png", output / "smoke.png"
    if not flame_path.exists():
        width, height = 160, 320
        x = np.linspace(-1, 1, width)[None, :]
        y = np.linspace(0, 1, height)[:, None]
        center = 0.08 * np.sin(y * 17) + 0.05 * np.sin(y * 41)
        spread = 0.07 + 0.72 * y**0.65
        alpha = np.clip(1 - np.abs(x - center) / spread, 0, 1) ** 1.5
        alpha *= np.clip(y * 8, 0, 1) * (0.8 + 0.2 * np.sin(y * 37 + x * 9))
        core = np.exp(-((x - center) ** 2 / 0.08 + (y - 0.82) ** 2 / 0.12))
        rgb = np.zeros((height, width, 3), dtype=np.float32)
        rgb[:, :, 0] = 1
        rgb[:, :, 1] = np.clip(0.22 + 0.68 * (1 - y) + 0.45 * core, 0, 1)
        rgb[:, :, 2] = 0.04 + 0.5 * core
        rgba = np.dstack([rgb, alpha]).astype(np.float32)
        Image.fromarray((rgba * 255).astype(np.uint8)).save(flame_path)
    if not smoke_path.exists():
        size = 256
        x, y = np.meshgrid(np.linspace(-1, 1, size), np.linspace(-1, 1, size))
        rng = np.random.default_rng(43)
        noise = Image.fromarray((rng.random((size, size)) * 255).astype(np.uint8))
        noise = noise.filter(ImageFilter.GaussianBlur(12)).resize((size, size))
        detail = np.asarray(noise, dtype=np.float32) / 255
        alpha = np.clip(1 - np.sqrt(x * x + y * y), 0, 1) ** 1.4
        alpha *= 0.35 + detail * 0.65
        gray = 0.12 + detail * 0.28
        rgba = np.dstack([gray, gray, gray * 1.04, alpha * 0.75])
        Image.fromarray((rgba * 255).astype(np.uint8)).save(smoke_path)
    return flame_path, smoke_path


SOFT_SPRITES_MDL = """mdl 1.6;
import ::df::*;
import ::math::*;
import ::state::*;
import ::tex::*;

float4 texel(uniform texture_2d image) {
    float3 uv = state::texture_coordinate(0);
    return tex::lookup_float4(image, float2(uv.x, uv.y), tex::wrap_clamp, tex::wrap_clamp);
}

export material soft_flame(
    uniform texture_2d image = texture_2d("./flame.png", ::tex::gamma_srgb),
    uniform float glow = 1500.0
) = let {
    float4 c = texel(image);
} in material(
    thin_walled: true,
    surface: material_surface(
        emission: material_emission(emission: df::diffuse_edf(), intensity: color(c.x, c.y, c.z) * glow)),
    geometry: material_geometry(cutout_opacity: math::saturate(c.w * 1.4)));

export material soft_smoke(
    uniform texture_2d image = texture_2d("./smoke.png", ::tex::gamma_srgb),
    uniform float density = 0.72
) = let {
    float4 c = texel(image);
} in material(
    thin_walled: true,
    surface: material_surface(scattering: df::diffuse_reflection_bsdf(tint: color(c.x, c.y, c.z))),
    geometry: material_geometry(cutout_opacity: c.w * density));
"""


def _soft_material(stage, path, folder, name):
    """RTX only blends MDL cutout opacity; UsdPreviewSurface opacity renders as a hard slab."""
    from pxr import Sdf, UsdShade

    module = Path(folder) / "soft_sprites.mdl"
    module.write_text(SOFT_SPRITES_MDL, encoding="utf-8")
    material = UsdShade.Material.Define(stage, path)
    shader = UsdShade.Shader.Define(stage, path + "/Shader")
    shader.SetSourceAsset(Sdf.AssetPath(module.as_posix()), "mdl")
    shader.SetSourceAssetSubIdentifier(name, "mdl")
    for output in (material.CreateSurfaceOutput("mdl"), material.CreateVolumeOutput("mdl")):
        output.ConnectToSource(shader.ConnectableAPI(), "out")
    material.CreateDisplacementOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    return material


def _quad(stage, path, width, height, material):
    from .city_scene import _mesh

    w, h = width / 2, height / 2
    faces = [([(-w, 0, -h), (w, 0, -h), (w, 0, h), (-w, 0, h)], (0, -1, 0), (1, 1))]
    return _mesh(stage, path, faces, material, False)


def billboard(position, eye, scale=(1.0, 1.0, 1.0)):
    """Row-major USD matrix turning an XZ quad's -Y face toward `eye`, including from straight above."""
    position = np.asarray(position, float)
    toward = np.asarray(eye, float) - position
    toward = toward / max(np.linalg.norm(toward), 1e-6)
    right = np.cross((0.0, 0.0, 1.0), toward)
    if np.linalg.norm(right) < 1e-3:
        right = np.array((1.0, 0.0, 0.0))
    right = right / np.linalg.norm(right)
    up = np.cross(right, -toward)
    matrix = np.eye(4)
    matrix[0, :3], matrix[1, :3], matrix[2, :3] = right * scale[0], -toward, up * scale[2]
    matrix[3, :3] = position
    return matrix


class CityFire:
    def __init__(self, stage, path, position, asset_root, scale=1.0):
        from pxr import Gf, UsdGeom, UsdLux

        flame_texture, smoke_texture = _effect_textures(asset_root)
        flame_material = _soft_material(stage, path + "/FlameMaterial", flame_texture.parent, "soft_flame")
        smoke_material = _soft_material(stage, path + "/SmokeMaterial", smoke_texture.parent, "soft_smoke")
        self.position = np.asarray(position, float)
        self.root = UsdGeom.Xform.Define(stage, path)
        self.root.AddTranslateOp().Set(Gf.Vec3d(*position))
        self.scale_op = self.root.AddScaleOp()
        self.scale_op.Set((1.0, 1.0, 1.0))
        self.flames, self.smoke = [], []
        rng = np.random.default_rng(217)
        for index in range(9):
            transform = UsdGeom.Xform.Define(stage, path + f"/Flame{index}")
            base = (float(rng.uniform(-2.4, 2.4) * scale), float(rng.uniform(-1.2, 1.2) * scale), float(rng.uniform(0, 2) * scale))
            width, height = float(rng.uniform(1.2, 2.7) * scale), float(rng.uniform(3, 6) * scale)
            _quad(stage, path + f"/Flame{index}/Sprite", width, height, flame_material)
            self.flames.append((transform.MakeMatrixXform(), base, index))
        for index in range(18):
            transform = UsdGeom.Xform.Define(stage, path + f"/Smoke{index}")
            size = float(rng.uniform(6, 11) * min(scale, 1.4))
            _quad(stage, path + f"/Smoke{index}/Sprite", size, size, smoke_material)
            self.smoke.append((transform.MakeMatrixXform(), index))
        light = UsdLux.SphereLight.Define(stage, path + "/Glow")
        light.CreateIntensityAttr(4500 * scale)
        light.CreateRadiusAttr(3 * scale)
        light.CreateColorAttr((1.0, 0.19, 0.025))
        light.AddTranslateOp().Set((0, -2, 2))

    def update(self, now, visible=True, intensity=1.0, eye=(0.0, -1e4, 0.0)):
        """Fire size follows scenario state; `intensity` comes from virtual work, not time."""
        from pxr import Gf

        self.root.MakeVisible() if visible else self.root.MakeInvisible()
        if not visible:
            return
        self.scale_op.Set((float(intensity),) * 3)
        local_eye = (np.asarray(eye, float) - self.position) / max(float(intensity), 1e-3)
        for op, base, index in self.flames:
            flicker = 0.82 + 0.22 * np.sin(now * (7.1 + index * 0.17) + index * 2.3)
            sway = (base[0] + 0.18 * np.sin(now * 3 + index), base[1], base[2])
            scale = (1.0 + 0.1 * np.sin(now * 5 + index), 1.0, flicker)
            op.Set(Gf.Matrix4d(billboard(sway, local_eye, scale).tolist()))
        for op, index in self.smoke:
            phase = (now * 0.055 + index / len(self.smoke)) % 1.0
            drift = np.sin(index * 2.4 + phase * 2) * phase * 5
            # Shrinking at both ends hides the wrap from plume top back to the source.
            scale = (0.65 + phase * 1.5) * np.sin(np.pi * phase) ** 0.5
            place = (drift + phase * 8, phase * 3, 3 + phase * 43)
            op.Set(Gf.Matrix4d(billboard(place, local_eye, (scale, scale, scale)).tolist()))


def flow_spheres(position, extent, outward=(0.0, 0.0, 0.0)):
    """Spread a fire's burning width over several emitters so it never reads as one ball."""
    width = float(np.clip(extent, 1.5, 14.0))
    count = int(np.clip(round(width / 2.5), 1, 5))
    radius = float(np.clip(width / (count + 0.5), 0.8, 2.4))
    centre = np.asarray(position, float) + np.asarray(outward, float)
    reach = max(width / 2 - radius, 0.0)
    offsets = np.linspace(-reach, reach, count) if count > 1 else [0.0]
    return [tuple(float(v) for v in centre + (offset, 0.0, 0.0)) for offset in offsets], radius


def flow_fuel(fraction):
    """Emitter fuel from remaining fire; a contained fire burns low before it is out."""
    return float(0.2 + 0.5 * np.clip(fraction, 0.0, 1.0))


def enable_flow():
    """Flow ships with Isaac but is off by default; run this before authoring Flow prims."""
    import carb
    from isaacsim.core.utils.extensions import enable_extension

    enable_extension("omni.flowusd")
    settings = carb.settings.get_settings()
    settings.set_bool("/rtx/flow/enabled", True)
    settings.set_bool("/rtx/flow/rayTracedReflectionsEnabled", True)
    settings.set_bool("/rtx/flow/rayTracedTranslucencyEnabled", True)


class FlowFires:
    """One sparse Flow volume with emitters per scenario fire; combustion is visual, not world truth."""

    def __init__(self, stage, path="/World/FlowFires", tuning=None, gravity=FLOW_GRAVITY_METRES):
        import omni.kit.app

        manager = omni.kit.app.get_app().get_extension_manager()
        preset = Path(manager.get_extension_path_by_module("omni.flowusd")) / "data/presets/Fire/Fire.usda"
        self.stage, self.path = stage, path
        stage.DefinePrim(path, "Xform").GetReferences().AddReference(str(preset))
        self.template = stage.GetPrimAtPath(path + "/flowEmitterSphere")
        self.template.GetAttribute("enabled").Set(False)
        self.tune(tuning or FLOW_TUNING, gravity)
        self.fires = {}

    def tune(self, tuning, gravity=FLOW_GRAVITY_METRES):
        from pxr import Gf, Vt

        for name, values in tuning.items():
            prim = self.stage.GetPrimAtPath(f"{self.path}/{name}")
            if not prim.IsValid():
                raise ValueError(f"Flow preset has no {name}")
            for key, value in values.items():
                attribute = prim.GetAttribute(key)
                if not attribute.IsValid():
                    raise ValueError(f"Flow prim {name} has no {key}")
                if key == "gravity":
                    value = tuple(float(v) * gravity for v in value)
                if isinstance(value, list):
                    value = Vt.Vec4fArray([Gf.Vec4f(*point) for point in value])
                attribute.Set(Gf.Vec3f(*value) if isinstance(value, tuple) else value)

    def add(self, key, position, extent, outward=(0.0, 0.0, 0.0), glow=1.0):
        from pxr import Gf, UsdGeom, UsdLux

        spheres, radius = flow_spheres(position, extent, outward)
        emitters = []
        for index, centre in enumerate(spheres):
            prim = self.stage.DefinePrim(f"{self.path}/{key}_{index}", "FlowEmitterSphere")
            prim.GetReferences().AddInternalReference(self.template.GetPath())
            prim.GetAttribute("position").Set(Gf.Vec3f(*centre))
            prim.GetAttribute("radius").Set(radius)
            prim.GetAttribute("enabled").Set(True)
            emitters.append(prim)
        light = UsdLux.SphereLight.Define(self.stage, f"{self.path}/{key}_glow")
        light.CreateIntensityAttr(1800 * glow)
        light.CreateRadiusAttr(3 * glow)
        light.CreateColorAttr((1.0, 0.27, 0.05))
        UsdGeom.Xformable(light).AddTranslateOp().Set(Gf.Vec3d(*spheres[0]))
        self.fires[key] = {"emitters": emitters, "light": light, "base": 1800 * glow, "state": None}

    def update(self, key, active, fraction, now=0.0):
        fire = self.fires[key]
        state = (bool(active), round(flow_fuel(fraction), 2))
        if state != fire["state"]:
            fire["state"] = state
            for prim in fire["emitters"]:
                prim.GetAttribute("enabled").Set(state[0])
                prim.GetAttribute("fuel").Set(state[1])
        flicker = 0.85 + 0.15 * np.sin(now * 9.0) * np.sin(now * 4.3)
        fire["light"].GetIntensityAttr().Set(float(fire["base"] * fraction * flicker) if active else 0.0)

"""Synthetic IR visualization from the live RGB render; no radiometric claim."""

import numpy as np

_LUT = np.array(
    [
        [0, 0, 4],
        [20, 11, 52],
        [66, 10, 104],
        [106, 23, 110],
        [147, 38, 103],
        [188, 55, 84],
        [221, 81, 58],
        [243, 120, 25],
        [252, 176, 54],
        [252, 235, 163],
    ],
    dtype=np.float32,
)


def thermal_frame(rgb, seed=0):
    """Return a 640x360 sensor-style view and explicitly uncalibrated heat stats."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont

    array = np.asarray(rgb, dtype=np.float32)[:, :, :3] / 255.0
    if array.ndim != 3 or min(array.shape[:2]) < 2:
        raise ValueError("RGB frame is required")
    red, green, blue = array[:, :, 0], array[:, :, 1], array[:, :, 2]
    luminance = 0.299 * red + 0.587 * green + 0.114 * blue
    sky = (blue > red * 1.04) & (blue > 0.42)
    ambient = 30 + 58 * luminance
    ambient[sky] = 5 + 5 * luminance[sky]
    hot_color = np.clip((red - 1.25 * blue - 0.12) * 2.2, 0, 1)
    hot_color *= np.clip((red - 0.72 * green) * 3, 0, 1)
    estimated = ambient + 760 * hot_color
    estimated = np.asarray(
        Image.fromarray(estimated.astype(np.float32), mode="F").resize((640, 360), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    rng = np.random.default_rng(seed)
    estimated = estimated + rng.normal(0, 1.4, estimated.shape)
    normalized = np.clip((estimated - 10) / 190, 0, 1) ** 0.55
    positions = np.linspace(0, 1, len(_LUT))
    colored = np.stack([np.interp(normalized, positions, _LUT[:, channel]) for channel in range(3)], axis=-1)
    image = Image.fromarray(colored.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.45))
    draw = ImageDraw.Draw(image, "RGBA")
    font = ImageFont.load_default(size=13)
    draw.rectangle((8, 8, 202, 31), fill=(0, 0, 0, 145))
    draw.text((14, 12), "IR SIM · UNCALIBRATED", font=font, fill=(245, 245, 245, 255))
    draw.line((320, 168, 320, 192), fill=(255, 255, 255, 130), width=1)
    draw.line((308, 180, 332, 180), fill=(255, 255, 255, 130), width=1)
    return image, {
        "mode": "synthetic thermal-style RGB conversion",
        "radiometric": False,
        "estimated_hot_color_max_c": float(estimated.max()),
    }

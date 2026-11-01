"""Paired synthetic camera renderer, dual-encoder network, and image-only inference."""

from dataclasses import dataclass
from math import pi, sqrt

import numpy as np
from PIL import Image, ImageDraw

from .contracts import Detection

IMAGE_SIZE = 64


@dataclass
class CameraObject:
    kind: str
    x: float
    y: float
    radius: float
    severity: float = 0.5


def render_camera(objects, center=(0.0, 0.0), span=102.0, seed=0):
    """Synthetic nadir RGB/IR. Labels are used for supervised training only."""
    rng = np.random.default_rng(seed)
    n = IMAGE_SIZE
    ground = np.zeros((n, n, 3), dtype=np.float32)
    ground[:] = rng.uniform([26, 40, 29], [48, 66, 48])
    ground += rng.normal(0, 5, ground.shape)
    rgb = Image.fromarray(np.clip(ground, 0, 255).astype(np.uint8))
    ir = Image.fromarray(np.clip(rng.normal(33, 5, (n, n)), 0, 255).astype(np.uint8))
    labels = [Image.new("L", (n, n)) for _ in range(3)]
    heat_label = Image.new("L", (n, n))
    draw, thermal = ImageDraw.Draw(rgb), ImageDraw.Draw(ir)
    for _ in range(16):
        x, y, r = rng.integers(0, n), rng.integers(0, n), rng.uniform(1, 5)
        draw.ellipse(
            (x - r, y - r, x + r, y + r), fill=tuple(int(v) for v in rng.uniform([17, 37, 24], [37, 78, 47]))
        )
    for obj in objects:
        x = (obj.x - center[0]) / span * n + n / 2
        y = (obj.y - center[1]) / span * n + n / 2
        r = max(1.2, obj.radius / span * n)
        if obj.kind == "fire":
            box = (x - r, y - r * 0.8, x + r, y + r * 0.8)
            draw.ellipse(box, fill=(210, int(55 + obj.severity * 90), 22))
            thermal.ellipse(box, fill=int(155 + obj.severity * 95))
            ImageDraw.Draw(labels[0]).ellipse(box, fill=255)
            ImageDraw.Draw(heat_label).ellipse(box, fill=int(obj.severity * 255))
            for dx in (-0.55, 0, 0.55):
                flame = [
                    (x + r * dx - r * 0.4, y + r * 0.4),
                    (x + r * dx, y - r * 1.25),
                    (x + r * dx + r * 0.4, y + r * 0.4),
                ]
                draw.polygon(flame, fill=(255, int(130 + obj.severity * 95), 60))
                thermal.polygon(flame, fill=int(165 + obj.severity * 85))
                ImageDraw.Draw(labels[0]).polygon(flame, fill=255)
                ImageDraw.Draw(heat_label).polygon(flame, fill=int(obj.severity * 255))
        elif obj.kind == "person":
            draw.rectangle((x - r * 0.6, y - r * 0.2, x + r * 0.6, y + r), fill=(70, 157, 204))
            draw.ellipse((x - r * 0.6, y - r, x + r * 0.6, y), fill=(223, 179, 141))
            for canvas in (thermal, ImageDraw.Draw(labels[1])):
                canvas.rectangle((x - r * 0.6, y - r * 0.2, x + r * 0.6, y + r), fill=235)
                canvas.ellipse((x - r * 0.6, y - r, x + r * 0.6, y), fill=255)
        elif obj.kind == "animal":
            box = (x - r, y - r * 0.5, x + r, y + r * 0.5)
            draw.ellipse(box, fill=(175, 142, 93))
            draw.rectangle((x - r * 0.8, y, x - r * 0.5, y + r), fill=(145, 110, 75))
            draw.rectangle((x + r * 0.5, y, x + r * 0.8, y + r), fill=(145, 110, 75))
            thermal.ellipse(box, fill=210)
            ImageDraw.Draw(labels[2]).ellipse(box, fill=255)
        else:
            # Hot rock: thermal evidence alone must not imply a fire.
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(107, 96, 82))
            thermal.ellipse((x - r, y - r, x + r, y + r), fill=180)
    rgb_array = np.asarray(rgb).astype(np.float32) / 255
    thermal_array = np.asarray(ir).astype(np.float32) / 255
    x = np.concatenate([rgb_array.transpose(2, 0, 1), thermal_array[None]], axis=0)
    masks = np.stack([np.asarray(label).astype(np.float32) / 255 for label in labels])
    severity = np.asarray(heat_label).astype(np.float32)[None] / 255
    return x, masks, severity


def synthetic_example(seed):
    rng = np.random.default_rng(seed)
    objects = []
    for _ in range(int(rng.integers(0, 5))):
        kind = rng.choice(["fire", "person", "animal", "rock"], p=[0.4, 0.23, 0.23, 0.14])
        radius = rng.uniform(1.5, 12) if kind == "fire" else rng.uniform(2.5, 5)
        objects.append(
            CameraObject(kind, rng.uniform(-42, 42), rng.uniform(-42, 42), radius, rng.uniform(0.1, 1))
        )
    return render_camera(objects, seed=seed)


def build_network():
    import torch
    from torch import nn
    from torch.nn import functional as F

    class FusionVision(nn.Module):
        def __init__(self):
            super().__init__()

            def encoder(channels):
                return nn.Sequential(
                    nn.Conv2d(channels, 16, 3, padding=1),
                    nn.SiLU(),
                    nn.Conv2d(16, 24, 3, stride=2, padding=1),
                    nn.SiLU(),
                    nn.Conv2d(24, 32, 3, stride=2, padding=1),
                    nn.SiLU(),
                )

            self.rgb, self.thermal = encoder(3), encoder(1)
            self.fusion = nn.Sequential(
                nn.Conv2d(64, 48, 3, padding=1), nn.SiLU(), nn.Conv2d(48, 32, 3, padding=1), nn.SiLU()
            )
            self.detail = nn.Sequential(nn.Conv2d(36, 24, 3, padding=1), nn.SiLU(), nn.Conv2d(24, 4, 1))

        def forward(self, images):
            encoded = self.fusion(torch.cat([self.rgb(images[:, :3]), self.thermal(images[:, 3:])], dim=1))
            encoded = F.interpolate(encoded, size=images.shape[-2:], mode="bilinear", align_corners=False)
            logits = self.detail(torch.cat([encoded, images], dim=1))
            return logits[:, :3], logits[:, 3:].sigmoid()

    return FusionVision()


def components(mask):
    """Small 4-neighbour connected components; no scipy runtime dependency."""
    seen = np.zeros(mask.shape, dtype=bool)
    for y, x in zip(*np.where(mask)):
        if seen[y, x]:
            continue
        stack, points = [(int(y), int(x))], []
        seen[y, x] = True
        while stack:
            yy, xx = stack.pop()
            points.append((yy, xx))
            for ny, nx in ((yy - 1, xx), (yy + 1, xx), (yy, xx - 1), (yy, xx + 1)):
                if 0 <= ny < mask.shape[0] and 0 <= nx < mask.shape[1] and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
        if len(points) >= 3:
            yield np.asarray(points)


class VisionRuntime:
    def __init__(self, path):
        import torch

        torch.set_num_threads(2)
        saved = torch.load(path, map_location="cpu", weights_only=True)
        self.model = build_network().eval()
        self.model.load_state_dict(saved["model"])
        self.metadata = saved.get("metadata", {})

    def detect_batch(self, images, centers, span, now, sources):
        import torch

        with torch.inference_mode():
            logits, severity = self.model(torch.from_numpy(np.stack(images)))
            probs, severity = logits.sigmoid().numpy(), severity.numpy()
        result = []
        for index, center in enumerate(centers):
            footprint = span[index] if isinstance(span, (list, tuple)) else span
            detections = []
            for channel, kind in enumerate(("fire", "person", "animal")):
                for points in components(probs[index, channel] > 0.55):
                    yy, xx = points[:, 0], points[:, 1]
                    px, py = float(xx.mean()), float(yy.mean())
                    position = (
                        center[0] + (px / IMAGE_SIZE - 0.5) * footprint,
                        center[1] + (py / IMAGE_SIZE - 0.5) * footprint,
                        0.0,
                    )
                    extent = sqrt(len(points) / pi) / IMAGE_SIZE * footprint
                    detections.append(
                        Detection(
                            kind,
                            position,
                            extent,
                            float(severity[index, 0, yy, xx].mean()),
                            float(probs[index, channel, yy, xx].mean()),
                            now,
                            sources[index],
                        )
                    )
            result.append(detections)
        return result

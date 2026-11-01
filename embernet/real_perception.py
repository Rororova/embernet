"""Real RGB detection and radiometric evidence, separate from synthetic sensors."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

PRETRAINED_MODEL = Path("artifacts/embernet/pretrained/fire-smoke-yolov8n/model.onnx")
CANDIDATE_MODEL = Path("artifacts/embernet/real-perception-v1-20261101-e1/model.onnx")
DEFAULT_MODEL = CANDIDATE_MODEL if CANDIDATE_MODEL.is_file() else PRETRAINED_MODEL


def nms(boxes, scores, classes, threshold=0.45):
    """Class-aware IoU suppression on XYXY image coordinates."""
    keep = []
    order = np.argsort(-scores, kind="stable")[:2000]
    while len(order) and len(keep) < 300:
        index = int(order[0])
        keep.append(index)
        rest = order[1:]
        low = np.maximum(boxes[index, :2], boxes[rest, :2])
        high = np.minimum(boxes[index, 2:], boxes[rest, 2:])
        intersection = np.prod(np.maximum(0, high - low), axis=1)
        area = np.prod(np.maximum(0, boxes[rest, 2:] - boxes[rest, :2]), axis=1)
        own = np.prod(np.maximum(0, boxes[index, 2:] - boxes[index, :2]))
        overlap = intersection / np.maximum(own + area - intersection, 1e-8)
        order = rest[(classes[rest] != classes[index]) | (overlap <= threshold)]
    return keep


class FireDetector:
    def __init__(self, model=DEFAULT_MODEL, confidence=0.25):
        import onnxruntime as ort

        self.model = Path(model)
        if not self.model.is_file():
            raise FileNotFoundError(f"Pretrained ONNX checkpoint missing: {self.model}")
        if not 0 < confidence < 1:
            raise ValueError("Confidence must be between zero and one")
        self.confidence = confidence
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self.session = ort.InferenceSession(
            str(self.model), sess_options=options, providers=["CPUExecutionProvider"]
        )
        if self.session.get_inputs()[0].shape != [1, 3, 640, 640]:
            raise ValueError("Unsupported detector input shape")

    def predict(self, image):
        start = time.perf_counter()
        image = ImageOps.exif_transpose(image).convert("RGB")
        width, height = image.size
        ratio = min(640 / width, 640 / height)
        nw, nh = round(width * ratio), round(height * ratio)
        left, top = (640 - nw) // 2, (640 - nh) // 2
        canvas = Image.new("RGB", (640, 640), (114, 114, 114))
        canvas.paste(image.resize((nw, nh), Image.Resampling.BILINEAR), (left, top))
        tensor = np.asarray(canvas, dtype=np.float32).transpose(2, 0, 1)[None] / 255
        raw = self.session.run(None, {"images": tensor})[0]
        if raw.shape != (1, 6, 8400):
            raise ValueError(f"Unsupported output shape {raw.shape}")
        prediction = raw[0].T
        classes = prediction[:, 4:].argmax(1)
        scores = prediction[:, 4:].max(1)
        select = np.flatnonzero((scores >= self.confidence) & np.isfinite(prediction).all(1))
        prediction, classes, scores = prediction[select], classes[select], scores[select]
        boxes = np.column_stack(
            (prediction[:, :2] - prediction[:, 2:4] / 2, prediction[:, :2] + prediction[:, 2:4] / 2)
        )
        boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / (nw / width)
        boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / (nh / height)
        boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, width)
        boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, height)
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes, classes, scores = boxes[valid], classes[valid], scores[valid]
        detections = [
            {
                "kind": ("smoke", "fire")[int(classes[k])],
                "confidence": round(float(scores[k]), 5),
                "box": np.round(boxes[k], 2).tolist(),
            }
            for k in nms(boxes, scores, classes)
        ]
        return {
            "detections": detections,
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "width": width,
            "height": height,
        }


def thermal_evidence(path, preview=None, threshold=100.0):
    """Read Celsius TIFF supplied by FLAME 3; threshold is an uncalibrated baseline."""
    values = np.asarray(Image.open(path), dtype=np.float32)
    if values.ndim != 2:
        raise ValueError("Radiometric TIFF must contain one temperature plane")
    valid = np.isfinite(values)
    if valid.mean() < 0.99:
        raise ValueError("Too many nonfinite radiometric pixels")
    pixels = values[valid]
    hot = float(np.mean(pixels >= threshold))
    if preview:
        scale = np.clip((np.nan_to_num(values, nan=10) - 10) / 140, 0, 1)
        stops = np.array([[15, 28, 42], [43, 67, 91], [117, 65, 77], [225, 119, 61], [255, 227, 157]], float)
        lo = np.minimum((scale * 4).astype(int), 3)
        blend = (scale * 4 - lo)[..., None]
        rgb = (stops[lo] * (1 - blend) + stops[lo + 1] * blend).astype(np.uint8)
        Image.fromarray(rgb).save(preview)
    return {
        "units": "Celsius (publisher radiometric TIFF)",
        "min": round(float(pixels.min()), 2),
        "max": round(float(pixels.max()), 2),
        "p95": round(float(np.quantile(pixels, 0.95)), 2),
        "hot_fraction": round(hot, 6),
        "threshold_c": threshold,
        "hot_candidate": bool(hot >= 0.0005),
        "display_range_c": [10, 150],
        "registration_uncertainty_pixels": 20,
    }


def annotate(image, detections):
    image = ImageOps.exif_transpose(image).convert("RGB").copy()
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=max(13, round(image.width / 45)))
    for detection in detections:
        x0, y0, x1, y1 = detection["box"]
        color = "#ffb45c" if detection["kind"] == "fire" else "#b5d9ed"
        draw.rectangle((x0, y0, x1, y1), outline=color, width=3)
        text = f"{detection['kind']} {detection['confidence']:.0%}"
        bounds = draw.textbbox((x0, y0), text, font=font)
        h = bounds[3] - bounds[1] + 8
        y = max(0, y0 - h)
        draw.rectangle((x0, y, min(image.width, x0 + bounds[2] - bounds[0] + 10), y + h), fill="#10232c")
        draw.text((x0 + 4, y + 2), text, font=font, fill=color)
    return image


def run_images(source, output, model=DEFAULT_MODEL, confidence=0.25):
    """Inspect independent images; never infer trajectories from filename order."""
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(source.iterdir()) if source.is_dir() else [source]
    files = [p for p in files if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if not files:
        raise ValueError("Source contains no supported RGB images")
    detector = FireDetector(model, confidence)
    records = []
    for index, path in enumerate(files):
        with Image.open(path) as image:
            result = detector.predict(image)
            name = f"frame-{index:05d}.jpg"
            annotate(image, result["detections"]).save(output / name, quality=92)
        records.append(
            {
                "id": path.name,
                "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "overlay": name,
                **result,
            }
        )
    report = {
        "model_sha256": hashlib.sha256(Path(model).read_bytes()).hexdigest(),
        "confidence": confidence,
        "frames": records,
        "scope": "Independent RGB image inspection. No geolocation, tracking, severity or actuation.",
    }
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

"""Zero-shot inspection on source-labeled FLAME 3 frames, without fitting or tuning."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from embernet.real_perception import DEFAULT_MODEL, FireDetector, annotate, thermal_evidence

parser = argparse.ArgumentParser()
parser.add_argument("--data", type=Path, default=Path("artifacts/embernet/real-perception"))
parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
parser.add_argument("--output", type=Path)
parser.add_argument(
    "--training-description",
    default="Zero-shot pretrained model; no local training or threshold tuning.",
)
args = parser.parse_args()
DATA = args.data
OUT = args.output or DATA
MODEL = args.model
manifest = json.loads((DATA / "sample-manifest.json").read_text())
(OUT / "review").mkdir(parents=True, exist_ok=True)
detector = FireDetector(MODEL)
# Warm up; reported per-frame times exclude loading and this call.
detector.predict(Image.new("RGB", (640, 512)))
frames = []
for sample in manifest["samples"]:
    with Image.open(DATA / sample["rgb"]) as image:
        result = detector.predict(image)
        captured = image.getexif().get(36867) or image.getexif().get(306)
        overlay = f"review/{sample['id']}-rgb.jpg"
        annotate(image, result["detections"]).save(OUT / overlay, quality=94)
    preview = f"review/{sample['id']}-thermal.png"
    thermal = thermal_evidence(DATA / sample["thermal"], OUT / preview)
    fire_score = max((d["confidence"] for d in result["detections"] if d["kind"] == "fire"), default=0)
    smoke_score = max((d["confidence"] for d in result["detections"] if d["kind"] == "smoke"), default=0)
    frames.append(
        {
            **sample,
            **result,
            "captured_at_raw": str(captured) if captured else None,
            "timestamp_warning": "Camera timestamp differs from the publisher's 2023 burn year; clock unverified."
            if captured and not str(captured).startswith("2023")
            else None,
            "overlay": overlay,
            "thermal_preview": preview,
            "thermal_stats": thermal,
            "fire_score": fire_score,
            "predicted_fire": bool(fire_score >= detector.confidence),
            "smoke_score": smoke_score,
            "predicted_warning": bool(result["detections"]),
        }
    )


def score(predicate):
    tp = sum(f["source_label"] == "Fire" and predicate(f) for f in frames)
    fp = sum(f["source_label"] == "No Fire" and predicate(f) for f in frames)
    fn = sum(f["source_label"] == "Fire" and not predicate(f) for f in frames)
    tn = sum(f["source_label"] == "No Fire" and not predicate(f) for f in frames)
    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "precision": round(tp / max(tp + fp, 1), 4),
        "recall": round(tp / max(tp + fn, 1), 4),
        "specificity": round(tn / max(tn + fp, 1), 4),
    }


report = {
    "title": "FLAME 3 · Sycan Marsh inspection",
    "created_unix": time.time(),
    "model": json.loads(MODEL.with_name("manifest.json").read_text()),
    "model_sha256": hashlib.sha256(MODEL.read_bytes()).hexdigest(),
    "dataset": manifest["dataset"],
    "dataset_version": 1,
    "confidence": detector.confidence,
    "iou": 0.45,
    "sample_counts": {
        "fire": sum(sample["source_label"] == "Fire" for sample in manifest["samples"]),
        "no_fire": sum(sample["source_label"] == "No Fire" for sample in manifest["samples"]),
    },
    "frames": frames,
    "rgb_image_level": score(lambda f: f["predicted_warning"]),
    "rgb_flame_only": score(lambda f: f["predicted_fire"]),
    "thermal_source_label_agreement": score(lambda f: f["thermal_stats"]["hot_candidate"]),
    "latency_ms": {
        "median": round(float(np.median([f["latency_ms"] for f in frames])), 2),
        "p95": round(float(np.quantile([f["latency_ms"] for f in frames], 0.95)), 2),
        "provider": "ONNX Runtime CPU, 4 threads; preprocess + inference + NMS",
    },
    "scope": [
        f"48 balanced, evenly spaced sample IDs from one prescribed burn. {args.training_description}",
        "Image-level source-folder labels only; no independent box/mask labels, no cross-burn claim.",
        "RGB warning means fire OR smoke, requiring verification; flame-only results reported separately.",
        "Thermal agreement is descriptive: source labels may themselves depend on thermal measurements.",
        "RGB model is not a thermal detector; temperature TIFF is processed independently.",
        "Frames are independent observations; filename order is not a verified flight timeline.",
        "No camera-to-ground calibration, severity, survivor assessment, water-demand inference or physical actuation.",
    ],
    "provenance": {
        "sample_manifest_sha256": hashlib.sha256((DATA / "sample-manifest.json").read_bytes()).hexdigest(),
        "inference_source_sha256": hashlib.sha256(
            Path("embernet/real_perception.py").read_bytes()
        ).hexdigest(),
    },
}
(OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(
    json.dumps(
        {k: report[k] for k in ("rgb_image_level", "thermal_source_label_agreement", "latency_ms")}, indent=2
    )
)

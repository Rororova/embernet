"""Pin, inspect and export a community checkpoint; runtime uses ONNX only."""

import hashlib
import importlib
import json
import os
from pathlib import Path
from urllib.request import urlopen

import numpy as np
import onnx
import onnxruntime as ort
import torch

ROOT = Path("artifacts/embernet/pretrained/fire-smoke-yolov8n")
ROOT.mkdir(parents=True, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = str(ROOT / "settings")
REVISION = "13017fe8af477c25f5298d168e2dfede4b000753"
REPO = "rabahdev/fire-smoke-yolov8n"
for filename in ("best.pt", "README.md"):
    path = ROOT / filename
    if not path.exists():
        with urlopen(f"https://huggingface.co/{REPO}/resolve/{REVISION}/{filename}", timeout=60) as response:
            path.write_bytes(response.read())
if (
    hashlib.sha256((ROOT / "best.pt").read_bytes()).hexdigest()
    != "b91633799ceb052c814b4f8b77a37efc9a40f002d528df97d74463585fa4f28f"
):
    raise ValueError("Pinned checkpoint SHA-256 mismatch")

# Allow named, installed neural-network classes only. Never deserialize arbitrary
# Python functions from the downloaded pickle or enable weights_only=False.
classes = {
    "ultralytics.nn.tasks.DetectionModel",
    "ultralytics.nn.modules.conv.Conv",
    "ultralytics.nn.modules.conv.Concat",
    "ultralytics.nn.modules.block.C2f",
    "ultralytics.nn.modules.block.Bottleneck",
    "ultralytics.nn.modules.block.DFL",
    "ultralytics.nn.modules.block.SPPF",
    "ultralytics.nn.modules.head.Detect",
    "torch.nn.modules.batchnorm.BatchNorm2d",
    "torch.nn.modules.upsampling.Upsample",
    "torch.nn.modules.activation.SiLU",
    "torch.nn.modules.container.Sequential",
    "torch.nn.modules.pooling.MaxPool2d",
    "torch.nn.modules.conv.Conv2d",
    "torch.nn.modules.container.ModuleList",
    "torch.nn.modules.linear.Identity",
    "builtins.set",
}
unsafe = torch.serialization.get_unsafe_globals_in_checkpoint(ROOT / "best.pt")
unexpected = set(unsafe) - classes
if unexpected:
    raise RuntimeError(f"Checkpoint contains unapproved global names: {sorted(unexpected)}")
allowed = []
for name in unsafe:
    module, attr = name.rsplit(".", 1)
    allowed.append(getattr(importlib.import_module(module), attr))
with torch.serialization.safe_globals(allowed):
    checkpoint = torch.load(ROOT / "best.pt", map_location="cpu", weights_only=True)
model = checkpoint["model"].float().eval()
if model.names != {0: "smoke", 1: "fire"}:
    raise RuntimeError(f"Unexpected class mapping: {model.names}")
for module in model.modules():
    if type(module).__name__ == "Detect":
        module.export, module.format, module.dynamic = True, "onnx", False
torch.set_num_threads(4)
dummy = torch.rand(1, 3, 640, 640)
with torch.inference_mode():
    expected = model(dummy).numpy()
torch.onnx.export(
    model,
    dummy,
    ROOT / "model.onnx",
    input_names=["images"],
    output_names=["detections"],
    opset_version=17,
    dynamo=False,
)
onnx.checker.check_model(str(ROOT / "model.onnx"))
session = ort.InferenceSession(str(ROOT / "model.onnx"), providers=["CPUExecutionProvider"])
actual = session.run(None, {"images": dummy.numpy()})[0]
np.testing.assert_allclose(actual, expected, rtol=2e-3, atol=2e-3)
manifest = {
    "repo": REPO,
    "revision": REVISION,
    "license": "AGPL-3.0",
    "classes": model.names,
    "parameters": sum(p.numel() for p in model.parameters()),
    "input": [1, 3, 640, 640],
    "output": list(actual.shape),
    "export_opset": 17,
    "parity_max_abs_error": float(np.max(np.abs(actual - expected))),
    "training_data_claim": "D-Fire, according to publisher model card; not independently audited",
    "files": {
        p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        for p in ROOT.iterdir()
        if p.name in ("best.pt", "model.onnx", "README.md")
    },
}
(ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps(manifest, indent=2))

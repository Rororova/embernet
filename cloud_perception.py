"""One bounded real-data detector fine-tune on an explicitly authorized Modal profile."""

from pathlib import Path

import modal

app = modal.App("embernet-real-perception-training")
ROOT = Path(__file__).resolve().parent
BASE = ROOT / "artifacts/embernet/pretrained/fire-smoke-yolov8n/best.pt"
BASE_CARD = ROOT / "artifacts/embernet/pretrained/fire-smoke-yolov8n/README.md"
BASE_LICENSE = ROOT / "artifacts/embernet/pretrained/fire-smoke-yolov8n/LICENSE"
BASE_SHA256 = "b91633799ceb052c814b4f8b77a37efc9a40f002d528df97d74463585fa4f28f"
volume = modal.Volume.from_name("embernet-experiments", create_if_missing=True)
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libgl1", "libglib2.0-0")
    .pip_install(
        "torch==2.15.0",
        "torchvision==0.29.2",
        "numpy==2.5.4",
        "pillow==12.3.0",
        "pyarrow==21.0.0",
        "ultralytics==8.4.194",
        "onnx==1.23.2",
        "onnxruntime==1.31.1",
    )
    .env({"YOLO_CONFIG_DIR": "/tmp/embernet-yolo", "PYTHONUTF8": "1", "PYTHONUNBUFFERED": "1"})
    .add_local_python_source("embernet")
    .add_local_file(str(BASE), "/opt/embernet/base.pt")
    .add_local_file(str(BASE_CARD), "/opt/embernet/base-model-card.md")
    .add_local_file(str(BASE_LICENSE), "/opt/embernet/AGPL-3.0.txt")
)


@app.function(
    image=image,
    gpu=["L4", "A10", "T4"],
    cpu=4,
    memory=16384,
    timeout=1800,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume},
)
def fine_tune(run_id: str, epochs: int = 4):
    import json
    import shutil
    import time

    import numpy as np
    import onnx
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    from embernet.perception_training import prepare_dataset, sha256_file

    if not run_id or any(
        character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
        for character in run_id
    ):
        raise ValueError("Use a simple unique run ID")
    if not 1 <= epochs <= 6:
        raise ValueError("Real-perception fine-tuning is capped at six epochs")
    output = Path("/runs") / run_id
    if output.exists():
        raise ValueError("Run already exists; use a new run ID")
    output.mkdir(parents=True)
    started = time.monotonic()
    if sha256_file("/opt/embernet/base.pt") != BASE_SHA256:
        raise RuntimeError("Pinned base checkpoint SHA-256 mismatch")
    print(f"Preparing pinned real-image subset for {run_id}", flush=True)
    dataset = prepare_dataset(Path("/tmp") / f"embernet-{run_id}", seed=217)
    dataset_root = Path("/tmp") / f"embernet-{run_id}"
    for name in ("dataset-manifest.json", "dataset-card.md", "annotation-contact-sheet.jpg", "data.yaml"):
        shutil.copy2(dataset_root / name, output / name)
    volume.commit()

    print(f"Starting {epochs}-epoch fine-tune; FLAME 3 is not present", flush=True)
    model = YOLO("/opt/embernet/base.pt")

    def persist_epoch(_trainer):
        volume.commit()

    model.add_callback("on_fit_epoch_end", persist_epoch)
    results = model.train(
        data=str(output / "data.yaml"),
        epochs=epochs,
        imgsz=640,
        batch=16,
        device=0,
        workers=4,
        project=str(output / "trainer"),
        name="run",
        exist_ok=False,
        seed=217,
        deterministic=True,
        optimizer="AdamW",
        lr0=0.0005,
        lrf=0.1,
        weight_decay=0.0005,
        warmup_epochs=0.5,
        patience=3,
        close_mosaic=1,
        mosaic=0.5,
        mixup=0.0,
        cache=False,
        save=True,
        save_period=1,
        val=True,
        plots=True,
        pretrained=True,
        verbose=True,
    )
    trainer_dir = output / "trainer" / "run"
    best = trainer_dir / "weights" / "best.pt"
    last = trainer_dir / "weights" / "last.pt"
    if not best.is_file() or not last.is_file():
        raise RuntimeError("Training finished without best/last checkpoints")

    exported = YOLO(str(best)).export(
        format="onnx",
        imgsz=640,
        opset=17,
        simplify=False,
        dynamic=False,
        half=False,
        device="cpu",
    )
    exported = Path(exported)
    onnx.checker.check_model(str(exported))
    session = ort.InferenceSession(str(exported), providers=["CPUExecutionProvider"])
    dummy = np.random.default_rng(217).random((1, 3, 640, 640), dtype=np.float32)
    actual = session.run(None, {"images": dummy})[0]
    if actual.shape != (1, 6, 8400) or not np.isfinite(actual).all():
        raise RuntimeError(f"Unexpected ONNX output: {actual.shape}")

    raw_model = YOLO(str(best)).model.float().eval()
    for module in raw_model.modules():
        if type(module).__name__ == "Detect":
            module.export, module.format, module.dynamic = True, "onnx", False
    with torch.inference_mode():
        expected = raw_model(torch.from_numpy(dummy)).numpy()
    np.testing.assert_allclose(actual, expected, rtol=2e-3, atol=2e-3)
    parity = float(np.max(np.abs(actual - expected)))
    parameters = sum(parameter.numel() for parameter in raw_model.parameters())

    shutil.copy2(best, output / "best.pt")
    shutil.copy2(last, output / "last.pt")
    shutil.copy2(exported, output / "model.onnx")
    for name in ("results.csv", "results.png", "args.yaml", "confusion_matrix.png", "confusion_matrix_normalized.png"):
        source = trainer_dir / name
        if source.is_file():
            shutil.copy2(source, output / name)
    shutil.copy2("/opt/embernet/base-model-card.md", output / "base-model-card.md")
    shutil.copy2("/opt/embernet/AGPL-3.0.txt", output / "AGPL-3.0.txt")

    metrics = {
        str(key): float(value)
        for key, value in getattr(results, "results_dict", {}).items()
        if isinstance(value, (int, float))
    }
    summary = {
        "run_id": run_id,
        "status": "completed",
        "base_model": "rabahdev/fire-smoke-yolov8n",
        "base_revision": "13017fe8af477c25f5298d168e2dfede4b000753",
        "base_sha256": BASE_SHA256,
        "dataset": dataset["dataset"],
        "dataset_revision": dataset["revision"],
        "dataset_counts": dataset["counts"],
        "category_counts": dataset["category_counts"],
        "epochs_requested": epochs,
        "seed": 217,
        "image_size": 640,
        "batch": 16,
        "optimizer": "AdamW",
        "lr0": 0.0005,
        "lrf": 0.1,
        "selection_metrics": metrics,
        "onnx_parity_max_abs_error": parity,
        "device": torch.cuda.get_device_name(0),
        "seconds": round(time.monotonic() - started, 2),
        "limitations": [
            "The base checkpoint was already trained on D-Fire; this is a small mixed-source fine-tune.",
            "FlamEye validation metrics select checkpoints but are not independent scene-generalization evidence.",
            "No FLAME 3 image was used for training, checkpoint selection or threshold tuning.",
            "Fire and smoke detection does not establish severity, location, survivorship or suppression demand.",
        ],
    }
    inference_manifest = {
        "kind": "fine-tuned fire/smoke YOLOv8n",
        "run_id": run_id,
        "license": "AGPL-3.0",
        "classes": {0: "smoke", 1: "fire"},
        "parameters": parameters,
        "input": [1, 3, 640, 640],
        "output": list(actual.shape),
        "export_opset": 17,
        "parity_max_abs_error": parity,
        "base_model": summary["base_model"],
        "base_revision": summary["base_revision"],
        "training_data": {
            "dataset": dataset["dataset"],
            "revision": dataset["revision"],
            "counts": dataset["counts"],
            "categories": dataset["category_counts"],
        },
    }
    (output / "training-summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output / "manifest.json").write_text(json.dumps(inference_manifest, indent=2), encoding="utf-8")
    files = {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "output-manifest.json"
    }
    (output / "output-manifest.json").write_text(json.dumps({"files": files}, indent=2), encoding="utf-8")
    volume.commit()
    print(json.dumps(summary, indent=2), flush=True)
    return summary

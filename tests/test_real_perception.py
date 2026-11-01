from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from embernet.real_perception import (
    CANDIDATE_MODEL,
    DEFAULT_MODEL,
    FireDetector,
    nms,
    thermal_evidence,
)


def test_nms_preserves_different_classes_and_nonoverlapping_regions():
    boxes = np.array([[0, 0, 10, 10], [1, 1, 9, 9], [1, 1, 9, 9], [30, 30, 40, 40]], float)
    assert nms(boxes, np.array([0.9, 0.8, 0.7, 0.6]), np.array([0, 0, 1, 0])) == [0, 2, 3]


def test_letterbox_predictions_return_original_image_coordinates():
    detector = FireDetector.__new__(FireDetector)
    detector.confidence = 0.25
    output = np.zeros((1, 6, 8400), np.float32)
    output[0, :, 0] = [320, 320, 80, 80, 0.1, 0.9]
    detector.session = SimpleNamespace(run=lambda *_: [output])
    result = detector.predict(Image.new("RGB", (800, 400)))
    assert result["detections"][0]["kind"] == "fire"
    assert result["detections"][0]["box"] == [350, 150, 450, 250]


def test_radiometric_values_survive_display_clipping(tmp_path):
    data = np.full((20, 20), 25, dtype=np.float32)
    data[:2, :2] = 620
    source = tmp_path / "temperatures.tiff"
    preview = tmp_path / "preview.png"
    Image.fromarray(data).save(source)
    stats = thermal_evidence(source, preview)
    assert stats["max"] == 620 and stats["hot_fraction"] == 0.01 and stats["hot_candidate"]
    assert np.array_equal(np.asarray(Image.open(source)), data)
    assert Image.open(preview).mode == "RGB"


@pytest.mark.skipif(not DEFAULT_MODEL.exists(), reason="Downloaded checkpoint not installed")
def test_real_onnx_runtime_has_valid_finite_outputs():
    detector = FireDetector()
    result = detector.predict(Image.new("RGB", (640, 512)))
    assert result["latency_ms"] > 0 and result["width"] == 640
    assert all(0.25 <= d["confidence"] <= 1 and np.isfinite(d["box"]).all() for d in result["detections"])


@pytest.mark.skipif(
    not (CANDIDATE_MODEL.parent / "flame3" / "report.json").exists(),
    reason="Fine-tuned candidate review is not installed",
)
def test_candidate_review_serves_candidate_assets_and_preserves_baseline(tmp_path):
    from fastapi.testclient import TestClient

    from embernet.server import create_app

    with TestClient(create_app(run_dir=str(tmp_path))) as client:
        response = client.get("/api/perception")
        assert response.status_code == 200
        report = response.json()
        assert report["model"]["run_id"] == "real-perception-v1-20261101-e1"
        frame = report["frames"][0]
        assert frame["overlay"].startswith("candidate/review/")
        assert client.get(f"/evidence/{frame['overlay']}").status_code == 200
        assert client.get(f"/evidence/{frame['rgb']}").status_code == 200
        baseline = client.get("/evidence/report.json").json()
        assert baseline["model"]["repo"] == "rabahdev/fire-smoke-yolov8n"

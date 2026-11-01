import io

import pytest
from PIL import Image

import embernet.perception_training as training
from embernet.perception_training import row_category, select_rows, yolo_label


def _row(index, source, *, fire=False, smoke=False, empty=False):
    annotations = []
    if not empty:
        if fire:
            annotations.append(
                {"class_name": "fire", "x_center": 0.5, "y_center": 0.5, "width": 0.2, "height": 0.3}
            )
        if smoke:
            annotations.append(
                {"class_name": "smoke", "x_center": 0.4, "y_center": 0.4, "width": 0.3, "height": 0.2}
            )
    return {
        "row_idx": index,
        "row": {
            "image_id": f"{source}-{index}",
            "source": source,
            "has_fire": fire,
            "has_smoke": smoke,
            "annotations": annotations,
        },
    }


def test_selection_is_deterministic_and_preserves_category_quotas():
    rows = []
    for index in range(12):
        rows.extend(
            [
                _row(index * 4, "dfire", fire=True, smoke=index % 2 == 0),
                _row(index * 4 + 1, "pyro", smoke=True),
                _row(index * 4 + 2, "dfire", smoke=True),
                _row(index * 4 + 3, "pyro", empty=True),
            ]
        )
    quotas = {"fire": 5, "new_smoke": 4, "dfire_smoke": 3, "negative": 2}
    selected = select_rows(rows, quotas, seed=217)
    assert select_rows(rows, quotas, seed=217) == selected
    assert len(selected) == 14
    assert {category: sum(row_category(item["row"]) == category for item in selected) for category in quotas} == quotas


def test_yolo_label_remaps_classes_and_retains_empty_negatives():
    labelled = _row(0, "dfire", fire=True, smoke=True)
    assert yolo_label(labelled["row"]).splitlines() == [
        "1 0.50000000 0.50000000 0.20000000 0.30000000",
        "0 0.40000000 0.40000000 0.30000000 0.20000000",
    ]
    assert yolo_label(_row(1, "pyro", empty=True)["row"]) == ""


def test_yolo_label_rejects_invalid_or_unknown_annotations():
    row = _row(0, "dfire", fire=True)["row"]
    row["annotations"][0]["x_center"] = 1.2
    with pytest.raises(ValueError, match="Invalid normalized box"):
        yolo_label(row)
    row = _row(0, "dfire", fire=True)["row"]
    row["annotations"][0]["class_name"] = "person"
    with pytest.raises(ValueError, match="Unexpected class"):
        yolo_label(row)


def test_yolo_label_clips_only_small_boundary_rounding_errors():
    row = _row(0, "dfire", fire=True)["row"]
    row["annotations"][0].update(x_center=0.99, y_center=0.5, width=0.04, height=0.2)
    values = yolo_label(row).split()
    assert values[0] == "1"
    assert float(values[1]) + float(values[3]) / 2 == 1
    row["annotations"][0].update(x_center=1.0, width=0.1)
    with pytest.raises(ValueError, match="Box leaves image bounds"):
        yolo_label(row)


def test_selection_fails_instead_of_silently_shrinking_a_quota():
    with pytest.raises(ValueError, match="Need 2 fire rows, found 1"):
        select_rows([_row(0, "dfire", fire=True)], {"fire": 2}, seed=217)


def test_parquet_metadata_and_embedded_images_form_a_yolo_split(tmp_path, monkeypatch):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    payload = io.BytesIO()
    Image.new("RGB", (64, 48), "green").save(payload, format="JPEG")
    source_rows = [
        _row(0, "dfire", fire=True)["row"],
        _row(1, "pyro", smoke=True)["row"],
        _row(2, "dfire", smoke=True)["row"],
        _row(3, "pyro", empty=True)["row"],
    ]
    images = [{"bytes": payload.getvalue(), "path": None} for _ in source_rows]
    shard = tmp_path / "tiny.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [
                {key: value for key, value in row.items() if key != "image_id"}
                | {"image_id": row["image_id"], "image": image}
                for row, image in zip(source_rows, images, strict=True)
            ]
        ),
        shard,
    )
    monkeypatch.setattr(training, "SOURCE_SHARDS", {"train": [{"path": "tiny.parquet"}]})
    shards = {"tiny.parquet": shard}
    rows = training._metadata_rows("train", shards)
    quotas = {"fire": 1, "new_smoke": 1, "dfire_smoke": 1, "negative": 1}
    records = training._write_split("train", rows, quotas, 217, tmp_path / "out", shards)
    assert len(records) == 4
    assert {record["category"] for record in records} == set(quotas)
    for record in records:
        assert (tmp_path / "out" / record["image"]).is_file()
        assert (tmp_path / "out" / record["label"]).is_file()

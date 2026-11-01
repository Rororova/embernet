"""Bounded, reproducible real-image dataset preparation for detector fine-tuning."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

DATASET_REPO = "Hajorda/flameye-wildfire-detection"
DATASET_REVISION = "361a3dea8b877482af9f4ed80eff77ffd39926ef"
DEFAULT_TRAIN_QUOTAS = {"fire": 200, "new_smoke": 400, "dfire_smoke": 100, "negative": 200}
DEFAULT_VALIDATION_QUOTAS = {"fire": 50, "new_smoke": 120, "dfire_smoke": 30, "negative": 60}
MAX_IMAGE_BYTES = 25 * 1024 * 1024
# Exact publisher Parquet shards: D-Fire/other sources plus a separate Pyro shard.
SOURCE_SHARDS = {
    "train": [
        {
            "path": "data/train-00000-of-00013.parquet",
            "bytes": 472353509,
            "sha256": "cfba584a38290e68d9d6ad30aee3b8f48cdfede704773fabcebdd4c523966838",
        },
        {
            "path": "data/train-00001-of-00013.parquet",
            "bytes": 284378756,
            "sha256": "cb9ccaf86280e7312db9f6ed8d989fa4fe9be918fdefc8dc6309e1a3f255e631",
        },
        {
            "path": "data/train-00002-of-00013.parquet",
            "bytes": 482326279,
            "sha256": "bbd9b7d560ea5026a969efa0e2511f697ec2a38e757091995be4659aa3c1255c",
        },
        {
            "path": "data/train-00010-of-00013.parquet",
            "bytes": 726426340,
            "sha256": "e4dce3ad2668396e4813955efc2d34c82a618f1d2a966b6207b7a01ce5fb7995",
        },
    ],
    "validation": [
        {
            "path": "data/validation-00000-of-00004.parquet",
            "bytes": 358190645,
            "sha256": "2b22673bc391769ffdcad797d1b306931e8062c4c25bbdf580592ba426cdca48",
        },
        {
            "path": "data/validation-00003-of-00004.parquet",
            "bytes": 672780187,
            "sha256": "857324321edafd19d7e01d85dd414ea775b2fcac9ae7f2dce442c650cb6856eb",
        },
    ],
}


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_category(row):
    """Separate base-model D-Fire examples from newly introduced smoke sources."""
    source = row.get("source")
    if source == "dfire" and row.get("has_fire"):
        return "fire"
    if source in ("pyro", "aiformankind") and row.get("has_smoke"):
        return "new_smoke"
    if source == "dfire" and row.get("has_smoke"):
        return "dfire_smoke"
    if not row.get("annotations"):
        return "negative"
    return "other"


def select_rows(rows, quotas, seed):
    """Select exact category quotas using stable hashes, never FLAME 3 data."""
    groups = {category: [] for category in quotas}
    for item in rows:
        category = row_category(item["row"])
        if category in groups:
            groups[category].append(item)
    selected = []
    for category, quota in quotas.items():
        if not isinstance(quota, int) or quota < 1:
            raise ValueError(f"Invalid {category} quota: {quota}")
        candidates = groups[category]
        if len(candidates) < quota:
            raise ValueError(f"Need {quota} {category} rows, found {len(candidates)}")
        ordered = sorted(
            candidates,
            key=lambda item: hashlib.sha256(
                f"{seed}:{category}:{item['row_idx']}:{item['row']['image_id']}".encode()
            ).hexdigest(),
        )
        selected.extend(ordered[:quota])
    identities = [(item["row_idx"], item["row"]["image_id"]) for item in selected]
    if len(identities) != len(set(identities)):
        raise ValueError("Dataset selection contains duplicate rows")
    return sorted(selected, key=lambda item: item["row_idx"])


def yolo_label(row):
    """Validate source boxes and remap FlamEye fire=0/smoke=1 to smoke=0/fire=1."""
    lines = []
    for annotation in row.get("annotations", []):
        kind = annotation.get("class_name")
        if kind not in ("smoke", "fire"):
            raise ValueError(f"Unexpected class in {row.get('image_id')}: {kind}")
        values = [float(annotation[key]) for key in ("x_center", "y_center", "width", "height")]
        if not all(math.isfinite(value) for value in values):
            raise ValueError(f"Nonfinite box in {row.get('image_id')}")
        x, y, width, height = values
        if not all(0 <= value <= 1 for value in values) or width <= 0 or height <= 0:
            raise ValueError(f"Invalid normalized box in {row.get('image_id')}: {values}")
        x0, y0, x1, y1 = x - width / 2, y - height / 2, x + width / 2, y + height / 2
        if min(x0, y0) < -0.01 or max(x1, y1) > 1.01:
            raise ValueError(f"Box leaves image bounds in {row.get('image_id')}: {values}")
        x0, y0, x1, y1 = max(0, x0), max(0, y0), min(1, x1), min(1, y1)
        clipped = [(x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0]
        if min(clipped[2:]) <= 0:
            raise ValueError(f"Empty clipped box in {row.get('image_id')}: {values}")
        class_id = 0 if kind == "smoke" else 1
        lines.append(f"{class_id} " + " ".join(f"{value:.8f}" for value in clipped))
    return "\n".join(lines) + ("\n" if lines else "")


def _request(url, timeout=60, attempts=5):
    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=timeout) as response:
                return response.read()
        except HTTPError as error:
            if attempt + 1 == attempts:
                detail = error.read().decode("utf-8", errors="replace")[:1000]
                raise RuntimeError(f"HTTP {error.code} from dataset source: {detail}") from error
            retry_after = error.headers.get("Retry-After")
            delay = float(retry_after) if retry_after and retry_after.isdigit() else 2 * (attempt + 1)
            time.sleep(min(delay, 30))
        except Exception:
            if attempt + 1 == attempts:
                raise
            time.sleep(2 * (attempt + 1))
    raise AssertionError("unreachable")


def _download_shard(spec, target):
    url = f"https://huggingface.co/datasets/{DATASET_REPO}/resolve/{DATASET_REVISION}/{spec['path']}"
    temporary = target.with_suffix(".download")
    for attempt in range(3):
        digest = hashlib.sha256()
        size = 0
        try:
            with urlopen(url, timeout=120) as response, temporary.open("wb") as stream:
                while chunk := response.read(4 * 1024 * 1024):
                    stream.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
                    if size > spec["bytes"]:
                        raise RuntimeError(f"Source shard exceeds expected bytes: {spec['path']}")
            if size != spec["bytes"] or digest.hexdigest() != spec["sha256"]:
                raise RuntimeError(
                    f"Source shard failed byte/hash verification: {spec['path']}; "
                    f"actual size={size}, sha256={digest.hexdigest()}"
                )
            temporary.replace(target)
            print(f"Verified source shard {spec['path']} ({size} bytes)", flush=True)
            return
        except Exception:
            temporary.unlink(missing_ok=True)
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))


def _metadata_rows(split, shards):
    import pyarrow.parquet as pq

    columns = ["image_id", "source", "annotations", "has_fire", "has_smoke"]
    rows = []
    for spec in SOURCE_SHARDS[split]:
        table = pq.ParquetFile(shards[spec["path"]]).read(columns=columns)
        for local_index, row in enumerate(table.to_pylist()):
            rows.append(
                {
                    "row_idx": len(rows),
                    "row": row,
                    "_shard": spec["path"],
                    "_local_idx": local_index,
                }
            )
    return rows


def _safe_name(item):
    stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", item["row"]["image_id"]).strip("-.")
    if not stem:
        raise ValueError("Empty dataset image ID")
    return f"{item['row_idx']:05d}-{stem[:100]}.jpg"


def _write_one(item, payload, split, output, category):
    name = _safe_name(item)
    relative = Path(split) / "images" / name
    target = output / relative
    if len(payload) > MAX_IMAGE_BYTES:
        raise ValueError(f"Image exceeds byte bound: {name}")
    from PIL import Image

    with Image.open(io.BytesIO(payload)) as image:
        width, height = image.size
        image.verify()
    if min(width, height) < 32:
        raise ValueError(f"Image is too small: {name} ({width}x{height})")
    target.write_bytes(payload)
    (output / split / "labels" / f"{Path(name).stem}.txt").write_text(
        yolo_label(item["row"]), encoding="utf-8"
    )
    row = item["row"]
    return {
        "row_idx": item["row_idx"],
        "image_id": row["image_id"],
        "source": row["source"],
        "category": category,
        "source_shard": item["_shard"],
        "source_shard_row": item["_local_idx"],
        "image": relative.as_posix(),
        "label": (Path(split) / "labels" / f"{Path(name).stem}.txt").as_posix(),
        "width": width,
        "height": height,
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "annotations": row["annotations"],
    }


def _write_split(split, rows, quotas, seed, output, shards):
    import pyarrow.parquet as pq

    selected = select_rows(rows, quotas, seed)
    for kind in ("images", "labels"):
        (output / split / kind).mkdir(parents=True, exist_ok=True)
    by_shard = {}
    for item in selected:
        by_shard.setdefault(item["_shard"], {})[item["_local_idx"]] = item
    records = []
    for shard, wanted in by_shard.items():
        parquet = pq.ParquetFile(shards[shard])
        local_index = 0
        for batch in parquet.iter_batches(batch_size=64, columns=["image"]):
            for image in batch.column(0).to_pylist():
                item = wanted.get(local_index)
                if item is not None:
                    payload = image.get("bytes")
                    if payload is None:
                        raise ValueError(f"Parquet image has no embedded bytes: {item['row']['image_id']}")
                    records.append(_write_one(item, payload, split, output, row_category(item["row"])))
                    if len(records) % 100 == 0:
                        print(f"Extracted {len(records)}/{len(selected)} {split} images", flush=True)
                local_index += 1
    if len(records) != len(selected):
        raise RuntimeError(f"Expected {len(selected)} {split} images, extracted {len(records)}")
    records.sort(key=lambda record: record["row_idx"])
    print(f"Extracted {len(records)}/{len(selected)} {split} images", flush=True)
    return records


def _contact_sheet(records, output, path):
    from PIL import Image, ImageDraw, ImageFont, ImageOps

    chosen = []
    for category in DEFAULT_TRAIN_QUOTAS:
        candidates = [record for record in records if record["category"] == category]
        sources = sorted({record["source"] for record in candidates})
        per_source = max(1, 6 // max(len(sources), 1))
        category_chosen = [
            record
            for source in sources
            for record in [item for item in candidates if item["source"] == source][:per_source]
        ]
        selected_ids = {record["row_idx"] for record in category_chosen}
        category_chosen.extend(
            record for record in candidates if record["row_idx"] not in selected_ids
        )
        chosen.extend(category_chosen[:6])
    columns, tile_width, tile_height, image_height = 4, 320, 260, 220
    rows = math.ceil(len(chosen) / columns)
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), "#101820")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=13)
    for index, record in enumerate(chosen):
        x, y = (index % columns) * tile_width, (index // columns) * tile_height
        with Image.open(output / record["image"]) as source:
            source = ImageOps.exif_transpose(source).convert("RGB")
            source.thumbnail((tile_width, image_height), Image.Resampling.LANCZOS)
            overlay = ImageDraw.Draw(source)
            for annotation in record["annotations"]:
                cx, cy = annotation["x_center"], annotation["y_center"]
                width, height = annotation["width"], annotation["height"]
                box = [
                    (cx - width / 2) * source.width,
                    (cy - height / 2) * source.height,
                    (cx + width / 2) * source.width,
                    (cy + height / 2) * source.height,
                ]
                color = "#ffb45c" if annotation["class_name"] == "fire" else "#b5d9ed"
                overlay.rectangle(box, outline=color, width=2)
            sheet.paste(source, (x, y + 40))
        label = f"{record['category']} · {record['source']} · {record['row_idx']}"
        draw.text((x + 5, y + 5), label, font=font, fill="#f2f5f7")
        draw.text((x + 5, y + 22), record["image_id"][:42], font=font, fill="#a8b6bf")
    sheet.save(path, quality=92)


def prepare_dataset(output, seed=217):
    """Download 3.00 GB of pinned shards and extract only the bounded selected subset."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    cache = output.parent / f"{output.name}-shards"
    cache.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    shard_paths = {}
    for split_specs in SOURCE_SHARDS.values():
        for spec in split_specs:
            target = cache / Path(spec["path"]).name
            _download_shard(spec, target)
            shard_paths[spec["path"]] = target
    all_records = {}
    quotas_by_split = {"train": DEFAULT_TRAIN_QUOTAS, "validation": DEFAULT_VALIDATION_QUOTAS}
    for split, quotas in quotas_by_split.items():
        rows = _metadata_rows(split, shard_paths)
        all_records[split] = _write_split(split, rows, quotas, seed, output, shard_paths)
    root = output.resolve().as_posix()
    (output / "data.yaml").write_text(
        f"path: {root}\ntrain: train/images\nval: validation/images\n"
        "names:\n  0: smoke\n  1: fire\n",
        encoding="utf-8",
    )
    card_url = f"https://huggingface.co/datasets/{DATASET_REPO}/raw/{DATASET_REVISION}/README.md"
    (output / "dataset-card.md").write_bytes(_request(card_url))
    _contact_sheet(all_records["train"], output, output / "annotation-contact-sheet.jpg")
    manifest = {
        "dataset": DATASET_REPO,
        "revision": DATASET_REVISION,
        "license_reported_by_publisher": "CC-BY-4.0; original source notices remain applicable",
        "seed": seed,
        "selection": "Exact pinned Parquet shards, then stable per-category row hashes; no FLAME 3 rows",
        "class_mapping": {"smoke": 0, "fire": 1},
        "source_shards": SOURCE_SHARDS,
        "quotas": quotas_by_split,
        "counts": {split: len(records) for split, records in all_records.items()},
        "category_counts": {
            split: {
                category: sum(record["category"] == category for record in records)
                for category in quotas
            }
            for split, records in all_records.items()
        },
        "bytes": sum(record["bytes"] for records in all_records.values() for record in records),
        "seconds": round(time.monotonic() - started, 2),
        "limitations": [
            "D-Fire was used to train the base checkpoint; new sources are Pyro-SDIS and AI for Mankind.",
            "Only the recorded source shards are sampled; this is not the complete FlamEye dataset.",
            "Publisher annotations are validated structurally; boundary overflows up to 1% are clipped.",
            "An annotation contact sheet is retained for visual review; boxes are not independently relabelled.",
            "FlamEye validation is for checkpoint selection only; adjacent frames may share scenes.",
            "FLAME 3 remains a separate image-level evaluation set with no boxes or training use.",
        ],
        "records": all_records,
    }
    (output / "dataset-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    shutil.rmtree(cache)
    return manifest

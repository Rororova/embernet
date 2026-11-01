"""Download an evenly spaced, balanced inspection sample from the audited v1 inventory."""

import hashlib
import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import requests

OUT = Path("artifacts/embernet/real-perception")
inventory = json.loads((OUT / "sources/inventory.json").read_text())
by_name = {item["name"]: item for item in inventory}
samples = []
for label in ("Fire", "No Fire"):
    rgb = sorted(item["name"] for item in inventory if f"/{label}/RGB/Corrected FOV/" in item["name"])
    for index in np.linspace(0, len(rgb) - 1, 24, dtype=int):
        name = rgb[index]
        stem = Path(name).stem
        thermal = name.replace("/RGB/Corrected FOV/", "/Thermal/Celsius TIFF/").replace(".JPG", ".TIFF")
        if thermal not in by_name:
            raise RuntimeError("Missing radiometric pair")
        key = ("fire" if label == "Fire" else "clear") + "-" + stem
        samples.append(
            {
                "id": key,
                "source_label": label,
                "rgb_name": name,
                "thermal_name": thermal,
                "rgb": f"originals/{key}.jpg",
                "thermal": f"originals/{key}.tiff",
            }
        )
(OUT / "originals").mkdir(parents=True, exist_ok=True)


def fetch(task):
    source, target = task
    path = OUT / target
    # Current public endpoint, verified against Kaggle's generated SDK.
    url = "https://api.kaggle.com/v1/datasets.DatasetApiService/DownloadDataset"
    request = {
        "ownerSlug": "brycehopkins",
        "datasetSlug": "flame-3-computer-vision-subset-sycan-marsh",
        "datasetVersionNumber": 1,
        "fileName": source,
        "raw": True,
    }
    if not path.exists():
        for attempt in range(3):
            try:
                with requests.post(
                    url, json=request, headers={"User-Agent": "EMBERNET/0.1"}, timeout=60, stream=True
                ) as response:
                    response.raise_for_status()
                    if int(response.headers.get("Content-Length", 0)) > 12_000_000:
                        raise ValueError("Response exceeds single-file limit")
                    pieces = []
                    size = 0
                    for piece in response.iter_content(65536):
                        size += len(piece)
                        if size > 12_000_000:
                            raise ValueError("Response exceeds single-file limit")
                        pieces.append(piece)
                    payload = b"".join(pieces)
                if len(payload) > 12_000_000:
                    raise ValueError("Response exceeds single-file limit")
                if zipfile.is_zipfile(io.BytesIO(payload)):
                    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                        entries = [
                            x
                            for x in archive.infolist()
                            if not x.is_dir() and Path(x.filename).name == Path(source).name
                        ]
                        if len(entries) != 1 or entries[0].file_size > 10_000_000:
                            raise ValueError("Unexpected single-file archive")
                        payload = archive.read(entries[0])
                if len(payload) != by_name[source]["bytes"]:
                    raise ValueError("Downloaded size differs from publisher inventory")
                path.write_bytes(payload)
                break
            except requests.RequestException as error:
                if isinstance(error, requests.HTTPError) and error.response.status_code not in (
                    429,
                    500,
                    502,
                    503,
                ):
                    raise
                if attempt == 2:
                    raise
                time.sleep(3 * (attempt + 1))
    return {
        "local": target,
        "source_name": source,
        "source_url": url,
        "bytes": path.stat().st_size,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


tasks = [(sample[f"{kind}_name"], sample[kind]) for sample in samples for kind in ("rgb", "thermal")]
# Probe one exact inventory entry before scheduling the rest.
results = [fetch(tasks[0])]
with ThreadPoolExecutor(max_workers=3) as pool:
    results.extend(pool.map(fetch, tasks[1:]))
manifest = {
    "dataset": "brycehopkins/flame-3-computer-vision-subset-sycan-marsh",
    "version": 1,
    "license_reported_by_publisher": "MIT",
    "burn": "Sycan Marsh, Oregon, 2023-10-25 through 2023-10-27",
    "inventory_counts": {"fire_pairs": 622, "no_fire_pairs": 116, "files": 2952},
    "selection": "24 evenly spaced file IDs per source folder; inspection only, no training or threshold tuning",
    "scope": "Single prescribed burn. Folder-level source labels; no independent box/mask annotation. Sample order is not a verified video trajectory.",
    "samples": samples,
    "files": results,
}
(OUT / "sample-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Downloaded {len(samples)} RGB/radiometric pairs, {sum(x['bytes'] for x in results):,} bytes")

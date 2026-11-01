"""Fetch two NVIDIA CC-BY-4.0 props, checking every non-preview file against its BOM."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import Request, urlopen

REVISION = "653d91e182011f357cf1644013cc94ddf194d349"
ASSETS = ("barrier_wall_plastic_orange_a03", "fireExtinguisher_abc_a03")
ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "artifacts/embernet/isaac/sources"
TARGET = ROOT / "artifacts/embernet/isaac/assets"


def fetch(asset):
    package_bytes = (SOURCES / f"{asset}-package.json").read_bytes()
    bom_bytes = (SOURCES / f"{asset}-bom.json").read_bytes()
    package, bom = json.loads(package_bytes), json.loads(bom_bytes)
    assert package["license"] == "CC-BY-4.0"
    assert hashlib.sha256(bom_bytes).hexdigest() == package["metadata"][0]["hash"]["sha256"]
    items = [item for item in bom["items"] if ".thumbs" not in PurePosixPath(item["relative_path"]).parts]
    assert sum(item["size"] for item in items) < 60_000_000
    destination = TARGET / asset
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "com.nvidia.simready.packaging.json").write_bytes(package_bytes)
    (destination / ".metadata").mkdir(exist_ok=True)
    (destination / ".metadata/com.nvidia.simready.packaging.bom.json").write_bytes(bom_bytes)

    def download(item):
        relative = PurePosixPath(item["relative_path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ValueError("Unsafe asset path")
        path = destination.joinpath(*relative.parts)
        digest = item["hash"]["sha256"]
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            url = f"https://huggingface.co/datasets/nvidia/simready-assets/resolve/{REVISION}/{asset}/{quote(str(relative))}"
            with urlopen(Request(url, headers={"User-Agent": "EMBERNET/0.1"}), timeout=90) as response:
                content = response.read(item["size"] + 1)
            if len(content) != item["size"] or hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"Asset integrity mismatch: {relative}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return {"path": str(relative), "bytes": item["size"], "sha256": digest}

    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(download, items))
    manifest = {
        "creator": "NVIDIA",
        "asset": asset,
        "license": "CC-BY-4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "source": f"https://huggingface.co/datasets/nvidia/simready-assets/tree/{REVISION}/{asset}",
        "revision": REVISION,
        "modifications": "None; referenced from an authored field scene.",
        "files": verified,
        "omitted": "Preview thumbnails only",
    }
    (destination / "EMBERNET-provenance.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(asset, len(verified), "verified files", sum(x["bytes"] for x in verified), "bytes", flush=True)


if __name__ == "__main__":
    for name in ASSETS:
        fetch(name)

"""Fetch audited NVIDIA sample content for an already authorized Isaac setup."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "config/isaac/vegetation.json").read_text(encoding="utf-8"))
    assert sum(p["bytes"] for p in manifest["files"]) < 50_000_000
    target = ROOT / "artifacts/embernet/isaac/nvidia-vegetation"

    def fetch(item):
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ValueError("Unsafe content path")
        path = target.joinpath(*relative.parts)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
            return
        with urlopen(manifest["source_root"] + str(relative), timeout=90) as response:
            data = response.read(item["bytes"] + 1)
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"NVIDIA content changed: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(fetch, manifest["files"]))
    print(f"Verified {len(manifest['files'])} NVIDIA oak/texture files; source units are centimeters.")


if __name__ == "__main__":
    main()

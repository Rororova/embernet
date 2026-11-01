"""Fetch the pinned NVIDIA wildland content; every file is size and SHA-256 checked."""

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    consent = ROOT / "artifacts/embernet/isaac/license-consent.json"
    if not consent.is_file() or not json.loads(consent.read_text(encoding="utf-8")).get("accepted"):
        raise RuntimeError("NVIDIA license consent is required; read context/ISAAC_SIM.md")
    manifest = json.loads((ROOT / "config/isaac/wildland.json").read_text(encoding="utf-8"))
    target = ROOT / "artifacts/embernet/isaac/nvidia-wildland"

    def fetch(item):
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
            raise ValueError("Unsafe content path")
        path = target.joinpath(*relative.parts)
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]:
            return
        for attempt in range(6):
            try:
                with urlopen(manifest["source_root"] + quote(str(relative)), timeout=180) as response:
                    data = response.read(item["bytes"] + 1)
                break
            except OSError:
                if attempt == 5:
                    raise
                time.sleep(5 * (attempt + 1))
        if len(data) != item["bytes"] or hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError(f"NVIDIA content changed: {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(fetch, manifest["files"]))
    total = sum(item["bytes"] for item in manifest["files"])
    print(f"Verified {len(manifest['files'])} NVIDIA wildland files, {total:,} bytes.")


if __name__ == "__main__":
    main()

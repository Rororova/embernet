"""Reproduce the pinned NVIDIA architectural asset pack; resumable, hashed, safe extraction."""

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

URL = "https://d4i3qtqj3r0z5.cloudfront.net/AECO_CityTowerDemoPack_NVD%4010011.zip"
SIZE = 2797027818
SHA = "03cfb5c643934b26b6876c36112036cd3584c09c3736ef7c237508ef242cf35f"
ROOT = Path(__file__).resolve().parents[1]


def main():
    consent = ROOT / "artifacts/embernet/isaac/license-consent.json"
    if not consent.is_file() or not json.loads(consent.read_text(encoding="utf-8")).get("accepted"):
        raise RuntimeError("NVIDIA license consent is required; read context/ISAAC_SIM.md")
    target = ROOT / "artifacts/embernet/isaac/nvidia-tower"
    target.mkdir(parents=True, exist_ok=True)
    archive = target / "tower.zip"
    start = archive.stat().st_size if archive.exists() else 0
    if start > SIZE:
        raise RuntimeError("Unexpected local archive size; inspect before replacing it")
    if start < SIZE:
        request = urllib.request.Request(URL, headers={"Range": f"bytes={start}-"} if start else {})
        with urllib.request.urlopen(request, timeout=60) as response:
            if start and (
                response.status != 206
                or not response.headers.get("Content-Range", "").startswith(f"bytes {start}-")
            ):
                raise RuntimeError("Server did not honor the download resume offset")
            with archive.open("ab" if start else "wb") as stream:
                while data := response.read(4 * 1024 * 1024):
                    stream.write(data)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive.stat().st_size != SIZE or digest != SHA:
        raise RuntimeError("NVIDIA archive hash/size mismatch")
    pack = (target / "pack").resolve()
    with zipfile.ZipFile(archive) as source:
        for entry in source.infolist():
            if not (pack / entry.filename).resolve().is_relative_to(pack):
                raise RuntimeError("Unsafe archive path")
        source.extractall(pack)
    (target / "source.json").write_text(
        json.dumps({"url": URL, "bytes": SIZE, "sha256": digest}, indent=2), encoding="utf-8"
    )
    print(f"Verified NVIDIA City Tower pack: {SIZE:,} archive bytes")


if __name__ == "__main__":
    main()

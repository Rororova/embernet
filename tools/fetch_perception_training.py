"""Download and hash-verify a persisted real-perception training run."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

from embernet.perception_training import sha256_file

parser = argparse.ArgumentParser()
parser.add_argument("run_id")
args = parser.parse_args()
if not args.run_id or any(
    character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    for character in args.run_id
):
    parser.error("Use a simple run ID")
volume = modal.Volume.from_name("embernet-experiments")
output = Path("artifacts/embernet") / args.run_id
output.mkdir(parents=True, exist_ok=True)


def download(name):
    if Path(name).name != name or name.startswith("."):
        raise ValueError(f"Unsafe artifact name: {name}")
    temporary = output / f"{name}.download"
    with temporary.open("wb") as stream:
        for chunk in volume.read_file(f"{args.run_id}/{name}"):
            stream.write(chunk)
    temporary.replace(output / name)


download("output-manifest.json")
expected = json.loads((output / "output-manifest.json").read_text(encoding="utf-8"))["files"]
for name, metadata in expected.items():
    download(name)
    path = output / name
    if path.stat().st_size != metadata["bytes"] or sha256_file(path) != metadata["sha256"]:
        raise RuntimeError(f"Downloaded artifact failed verification: {name}")
    print(f"Verified {name}", flush=True)
manifest = {
    "run_id": args.run_id,
    "files": {
        path.name: {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in sorted(output.iterdir())
        if path.is_file() and path.suffix != ".download"
    },
}
(output / "download-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(json.dumps({"output": str(output.resolve()), "files": len(expected)}, indent=2), flush=True)

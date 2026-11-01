"""Recover persisted artifacts even if the local training client was interrupted."""

import argparse
from pathlib import Path

import modal

parser = argparse.ArgumentParser()
parser.add_argument("run_id")
parser.add_argument("--vision-only", action="store_true")
args = parser.parse_args()
if not args.run_id or any(
    c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in args.run_id
):
    parser.error("Use a simple run ID")
volume = modal.Volume.from_name("embernet-experiments")
output = Path("artifacts/embernet") / args.run_id
output.mkdir(parents=True, exist_ok=True)
names = ["vision.pt", "vision-report.json"]
if not args.vision_only:
    names += ["mission.pt", "mission-bc.pt", "mission-report.json", "summary.json"]
for name in names:
    temporary = output / (name + ".download")
    with temporary.open("wb") as stream:
        for chunk in volume.read_file(f"{args.run_id}/{name}"):
            stream.write(chunk)
    temporary.replace(output / name)
    print(f"Downloaded {name}", flush=True)

"""Check free-credit headroom, then dispatch exactly one bounded detector fine-tune."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import modal

from cloud_perception import app, fine_tune

parser = argparse.ArgumentParser()
parser.add_argument("run_id")
parser.add_argument("--epochs", type=int, default=4)
args = parser.parse_args()
if not args.run_id or any(
    character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    for character in args.run_id
):
    parser.error("Use a simple unique run ID")
if not 1 <= args.epochs <= 6:
    parser.error("Epochs must be between one and six")
profile = os.environ.get("MODAL_PROFILE", "nikhilthakuraan")
if profile not in ("nikhilthakuraan", "ieirodov14"):
    parser.error("Set MODAL_PROFILE to an authorized Modal profile")
output = ROOT / "artifacts" / "embernet" / args.run_id


def billing():
    result = subprocess.run(
        [sys.executable, "-m", "modal", "billing", "summary", "--profile", profile, "--json"],
        capture_output=True,
        text=True,
        check=True,
        timeout=45,
    )
    return json.loads(result.stdout)


before = billing()
if float(before["billed_cost"]) > 0 or abs(float(before["adjustments"]["credits"])) > 28.0:
    raise RuntimeError("Insufficient verified free-credit headroom; no GPU job dispatched")
output.mkdir(parents=True, exist_ok=False)
(output / "billing-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
print(f"Dispatching {args.run_id} on {profile}; 1800 s hard timeout, no retries", flush=True)
try:
    with modal.enable_output(), app.run():
        call = fine_tune.spawn(args.run_id, args.epochs)
        launch = {
            "run_id": args.run_id,
            "profile": profile,
            "call_id": call.object_id,
            "epochs": args.epochs,
            "timeout_seconds": 1800,
            "retries": 0,
            "gpu_fallback": ["L4", "A10", "T4"],
        }
        (output / "launch.json").write_text(json.dumps(launch, indent=2), encoding="utf-8")
        print(f"Modal call: {call.object_id}", flush=True)
        result = call.get()
    (output / "training-response.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
finally:
    after = billing()
    (output / "billing-after.json").write_text(json.dumps(after, indent=2), encoding="utf-8")
print(json.dumps(result, indent=2), flush=True)

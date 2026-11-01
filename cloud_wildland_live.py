"""One bounded headless wildland mission with real PX4; never touches the shared session."""

import hashlib
import json
import os
import secrets
import subprocess
import sys
import uuid

import modal

from cloud_live import live_image
from embernet.cloud_resources import credit_reserve, rendering_resources, require_free_credits

app = modal.App("embernet-wildland-live")


@app.local_entrypoint()
def main(duration: int = 900, gpu: str = "RTX-PRO-6000", render_hz: float = 5.0):
    profile = os.environ.get("MODAL_PROFILE", "nikhilthakuraan")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Select one of the user-authorized Modal profiles")
    summary = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--json", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        ).stdout
    )
    require_free_credits(summary, credit_reserve(gpu, duration))
    resources = rendering_resources(gpu)
    run_id = "wild-" + uuid.uuid4().hex[:12]
    sandbox = modal.Sandbox.create(
        "python",
        "-m",
        "embernet.isaac.city_live",
        "--run-id",
        run_id,
        "--duration",
        str(duration),
        "--world",
        "wildland",
        "--render-hz",
        str(render_hz),
        app=app,
        image=live_image,
        gpu=resources["gpu"],
        cpu=resources["cpu"],
        memory=resources["memory"],
        timeout=duration + 60,
        volumes={
            "/runs": modal.Volume.from_name("embernet-live-logs"),
            "/opt/nvidia-wildland": modal.Volume.from_name("embernet-wildland-assets"),
        },
        # No viewer joins this run, so the control code is discarded unused.
        env={"EMBERNET_CONTROL_HASH": hashlib.sha256(secrets.token_bytes(32)).hexdigest()},
    )
    print(json.dumps({"run_id": run_id, "sandbox_id": sandbox.object_id}), flush=True)

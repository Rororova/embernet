"""Free-credit-guarded RTX look-development of the city fire on the deployed live image."""

import json
import os
import sys
from pathlib import Path

import modal

app = modal.App("embernet-fire")
volume = modal.Volume.from_name("embernet-isaac", create_if_missing=True)
if modal.is_local():
    deployed = json.loads(Path("artifacts/embernet/cloud/deployment.json").read_text(encoding="utf-8"))["image_id"]
    # Only the Python changes between looks, so the NVIDIA packs are never rebuilt or re-uploaded.
    image = modal.Image.from_id(deployed).add_local_dir("embernet", "/root/embernet", copy=True)
else:
    image = modal.Image.debian_slim()


@app.function(
    image=image,
    gpu="RTX-PRO-6000",
    cpu=12,
    memory=65536,
    timeout=600,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume},
)
def render(run_id):
    import shutil
    import subprocess
    import time

    if not run_id.replace("-", "").isalnum():
        raise ValueError("Invalid run ID")
    os.makedirs("/tmp/embernet-xdg", mode=0o700, exist_ok=True)
    out = Path("/runs") / run_id
    out.mkdir(exist_ok=False)
    started = time.monotonic()
    with (out / "kit-console.log").open("w") as console:
        try:
            run = subprocess.run(
                [sys.executable, "-m", "embernet.isaac.fire_render", "--output", str(out)],
                stdout=console,
                stderr=subprocess.STDOUT,
                timeout=520,
                check=False,
            )
            status = {"return_code": run.returncode}
        except subprocess.TimeoutExpired:
            status = {"return_code": -1, "timeout": True}
    status["elapsed_seconds"] = time.monotonic() - started
    status["success"] = (out / "report.json").is_file() and not (out / "exception.txt").is_file()
    (out / "process.json").write_text(json.dumps(status, indent=2))
    logs = Path(f"/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/isaacsim/kit/logs/Kit")
    for log in logs.rglob("*.log"):
        shutil.copy2(log, out / log.name)
    volume.commit()
    return status


@app.local_entrypoint()
def main(run_id: str):
    import subprocess

    from embernet.cloud_resources import credit_reserve, require_free_credits

    profile = os.environ.get("MODAL_PROFILE")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Set MODAL_PROFILE to the account whose free credit should be checked")
    billing = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--json", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        ).stdout
    )
    require_free_credits(billing, credit_reserve("RTX-PRO-6000", 540))
    target = Path("artifacts/embernet/isaac") / run_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "billing-before.json").write_text(json.dumps(billing, indent=2))
    print(json.dumps(render.remote(run_id)), flush=True)

"""Free-credit-guarded RTX look-development render of the NVIDIA wildland scene."""

import json
import os
from pathlib import Path

import modal

app = modal.App("embernet-wildland")
volume = modal.Volume.from_name("embernet-isaac", create_if_missing=True)
assets = modal.Volume.from_name("embernet-wildland-assets", create_if_missing=True)
if modal.is_local():
    from cloud_isaac_runtime import runtime_base_image

    image = runtime_base_image.env({"ACCEPT_EULA": "Y", "PRIVACY_CONSENT": "N"}).add_local_python_source(
        "embernet"
    )
else:
    # Containers bind their built image by function, so the local-only definition is never needed.
    image = modal.Image.debian_slim()


@app.function(
    image=modal.Image.debian_slim(python_version="3.12"),
    cpu=2,
    memory=4096,
    timeout=1200,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/assets": assets},
)
def fetch_assets(manifest):
    """Pull pinned NVIDIA files directly into the volume; a slow home uplink is never involved."""
    import hashlib
    import time
    from concurrent.futures import ThreadPoolExecutor
    from pathlib import PurePosixPath
    from urllib.parse import quote
    from urllib.request import urlopen

    def fetch(item):
        relative = PurePosixPath(item["path"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe content path")
        path = Path("/assets").joinpath(*relative.parts)
        if path.is_file() and path.stat().st_size == item["bytes"]:
            return 0
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
        return len(data)

    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = sum(pool.map(fetch, manifest["files"]))
    assets.commit()
    return {"files": len(manifest["files"]), "fetched_bytes": fetched}


@app.function(
    image=image,
    gpu="RTX-PRO-6000",
    cpu=12,
    memory=65536,
    timeout=900,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume, "/opt/nvidia-wildland": assets},
)
def render(run_id):
    import shutil
    import subprocess
    import sys
    import time

    if not run_id.replace("-", "").isalnum():
        raise ValueError("Invalid run ID")
    os.makedirs("/tmp/embernet-xdg", mode=0o700, exist_ok=True)
    out = Path("/runs") / run_id
    out.mkdir(exist_ok=False)
    started = time.monotonic()
    env = dict(os.environ, EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED="YES", PYTHONUNBUFFERED="1")
    with (out / "kit-console.log").open("w") as console:
        try:
            run = subprocess.run(
                [sys.executable, "-m", "embernet.isaac.wildland_render", "--output", str(out)],
                stdout=console,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=780,
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
    return {"process": status, "files": [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()]}


@app.function(
    image=modal.Image.debian_slim(python_version="3.12"),
    cpu=0.25,
    memory=512,
    timeout=2400,
    retries=0,
    max_containers=1,
    scaledown_window=2,
)
def pipeline(run_id, manifest):
    """Runs wholly in the cloud, so a dropped local connection cannot strand the job."""
    print(fetch_assets.remote(manifest), flush=True)
    return render.remote(run_id)


@app.local_entrypoint()
def main(run_id: str = "wildland-look-v1"):
    import subprocess
    import sys

    from embernet.cloud_resources import credit_reserve, require_free_credits

    profile = os.environ.get("MODAL_PROFILE", "nikhilthakuraan")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Select one of the user-authorized Modal profiles")
    billing = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--json", "--profile", profile],
            capture_output=True,
            text=True,
            timeout=45,
            check=True,
        ).stdout
    )
    require_free_credits(billing, credit_reserve("RTX-PRO-6000", 600))
    target = Path("artifacts/embernet/isaac") / run_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "billing-before.json").write_text(json.dumps(billing, indent=2))
    manifest = json.loads(Path("config/isaac/wildland.json").read_text(encoding="utf-8"))
    call = pipeline.spawn(run_id, manifest)
    print(f"Started {call.object_id}; collect with: modal volume get embernet-isaac {run_id}", flush=True)

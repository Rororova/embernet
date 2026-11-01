"""Pinned PX4 SITL build, isolated from the user's local Python and hardware."""

from pathlib import Path

import modal

from cloud_isaac_runtime import runtime_base_image

app = modal.App("embernet-px4")
px4_base_image = (
    runtime_base_image.apt_install(
        "cmake", "ninja-build", "pkg-config", "libxml2-dev", "libxslt1-dev", "zip", "unzip", "rsync"
    )
    .pip_install("empy==3.3.4", "pyserial==3.5", "kconfiglib==14.1.0", "jsonschema", "jinja2", "pyros-genmsg")
    .run_commands(
        "git clone --depth 1 --branch v1.14.3 --recursive --shallow-submodules https://github.com/PX4/PX4-Autopilot.git /opt/PX4-Autopilot",
        "git -C /opt/PX4-Autopilot/platforms/nuttx/NuttX/nuttx fetch --tags --depth 1",
    )
    .pip_install("future==1.0.0")
    .run_commands("cd /opt/PX4-Autopilot && make px4_sitl_default -j4")
    .add_local_file("tools/patch_px4_sitl_scheduler.py", "/opt/patch_px4_sitl_scheduler.py", copy=True)
    .run_commands(
        "python /opt/patch_px4_sitl_scheduler.py", "cd /opt/PX4-Autopilot && make px4_sitl_default -j4"
    )
)


@app.function(image=px4_base_image, timeout=120, retries=0, max_containers=1, serialized=True)
def build_probe():
    import hashlib
    import subprocess

    root = Path("/opt/PX4-Autopilot")
    binary = root / "build/px4_sitl_default/bin/px4"
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    )
    return {
        "commit": commit.stdout.strip(),
        "binary_bytes": binary.stat().st_size,
        "binary_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
    }


volume = modal.Volume.from_name("embernet-isaac", create_if_missing=True)
probe_image = px4_base_image.add_local_python_source("embernet")
isaac_image = (
    px4_base_image.add_local_python_source("embernet")
    .add_local_dir("artifacts/embernet/isaac/assets", "/opt/embernet-assets")
    .add_local_dir("artifacts/embernet/isaac/nvidia-vegetation", "/opt/nvidia-vegetation")
    .add_local_file("artifacts/embernet/pretrained/fire-smoke-yolov8n/model.onnx", "/opt/fire-smoke.onnx")
    .add_local_file("artifacts/embernet/embernet-v2/mission.pt", "/opt/mission.pt")
)


@app.function(
    image=isaac_image,
    gpu="L40S",
    cpu=8,
    memory=32768,
    timeout=900,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    serialized=True,
    volumes={"/runs": volume},
)
def isaac_probe(run_id):
    from embernet.isaac.job import execute_trial

    return execute_trial(run_id, "px4", volume, license_acknowledged=True)


@app.function(
    image=probe_image,
    cpu=4,
    memory=8192,
    timeout=300,
    retries=0,
    max_containers=1,
    serialized=True,
    volumes={"/runs": volume},
)
def protocol_probe(run_id):
    import traceback
    from pathlib import Path

    from embernet.isaac.px4_probe import run_probe

    target = Path("/runs") / run_id
    target.mkdir(exist_ok=False)
    try:
        result = run_probe(target)
    except Exception:  # noqa: BLE001 -- save full trial failure before returning evidence
        (target / "exception.txt").write_text(traceback.format_exc())
        result = {"passed": False}
    volume.commit()
    return {"result": result, "files": [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()]}


@app.local_entrypoint()
def main(mode: str = "build", run_id: str = "px4-protocol-v1"):
    import json

    if mode == "isaac":
        import os
        import subprocess
        import sys

        billing = subprocess.run(
            [
                sys.executable,
                "-m",
                "modal",
                "billing",
                "summary",
                "--json",
                "--profile",
                os.environ.get("MODAL_PROFILE", "nikhilthakuraan"),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=45,
        )
        summary = json.loads(billing.stdout)
        if float(summary["billed_cost"]) > 0 or abs(float(summary["adjustments"]["credits"])) > 29.1:
            raise RuntimeError("Insufficient verified free credits")
        result = isaac_probe.remote(run_id)
    else:
        result = build_probe.remote() if mode == "build" else protocol_probe.remote(run_id)
    target = Path("artifacts/embernet/px4")
    target.mkdir(parents=True, exist_ok=True)
    if mode == "build":
        (target / "build.json").write_text(json.dumps(result, indent=2))
    else:
        for name in result["files"]:
            path = target / run_id / name
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as stream:
                for chunk in volume.read_file(f"{run_id}/{name}"):
                    stream.write(chunk)
    print(json.dumps(result, indent=2))

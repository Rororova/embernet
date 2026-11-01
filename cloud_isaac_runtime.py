"""Isaac runtime on an RTX GPU. User approved NVIDIA license terms on 2026-10-31."""

import json
import os
from pathlib import Path

import modal

RUNTIME_VERSION = os.environ.get("EMBERNET_ISAAC_VERSION", "6.2.0.0")
if RUNTIME_VERSION not in ("5.1.0", "6.2.0.0"):
    raise ValueError("Unsupported pinned Isaac version")
app = modal.App("embernet-isaac")
volume = modal.Volume.from_name("embernet-isaac", create_if_missing=True)
runtime_base_image = (
    modal.Image.from_registry("ubuntu:22.04", add_python="3.11" if RUNTIME_VERSION == "5.1.0" else "3.12")
    .apt_install(
        "git",
        "git-lfs",
        "build-essential",
        "libvulkan1",
        "vulkan-tools",
        "libegl1",
        "libgl1",
        "libglib2.0-0",
        "libxrender1",
        "libsm6",
        "libxext6",
        "libice6",
        "libxt6",
        "libxi6",
        "libxrandr2",
        "libxcursor1",
        "libxinerama1",
        "libnss3",
        "libasound2",
        "libgomp1",
        "libgbm1",
    )
    .env(
        {
            "NVIDIA_DRIVER_CAPABILITIES": "all",
            "OMNI_KIT_ACCEPT_EULA": "YES",
            "XDG_RUNTIME_DIR": "/tmp/embernet-xdg",
            "XDG_CACHE_HOME": "/runs/cache/xdg",
            "CUDA_CACHE_PATH": "/runs/cache/cuda",
        }
    )
    .pip_install(f"isaacsim[all,extscache]=={RUNTIME_VERSION}", extra_index_url="https://pypi.nvidia.com")
    .pip_install(
        "pillow==11.3.0",
        "scipy==1.16.0",
        "pymavlink==2.4.49",
        "pyyaml==6.0.2",
        "onnxruntime==1.23.1",
        "imageio[ffmpeg]==2.37.0",
    )
    .run_commands(
        "git clone --depth 1 --branch v5.1.0 https://github.com/PegasusSimulator/PegasusSimulator.git /opt/pegasus",
        'test "$(git -C /opt/pegasus rev-parse HEAD)" = 644da37e9d5268e5f9a34e78bdcfd57a8bab82b4',
        "git -C /opt/pegasus lfs pull",
    )
    .apt_install("libglu1-mesa", "libxkbcommon0")
)
image = (
    runtime_base_image.add_local_python_source("embernet")
    .add_local_dir("artifacts/embernet/isaac/assets", "/opt/embernet-assets")
    .add_local_dir("artifacts/embernet/isaac/nvidia-vegetation", "/opt/nvidia-vegetation")
    .add_local_file("artifacts/embernet/pretrained/fire-smoke-yolov8n/model.onnx", "/opt/fire-smoke.onnx")
    .add_local_file("artifacts/embernet/embernet-v2/mission.pt", "/opt/mission.pt")
)


@app.function(
    image=image,
    gpu="L40S",
    cpu=8,
    memory=32768,
    timeout=900,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume},
)
def runtime_trial(run_id, mode, license_acknowledged=False):
    from embernet.isaac.job import execute_trial

    return execute_trial(run_id, mode, volume, license_acknowledged)


@app.local_entrypoint()
def main(run_id: str = "isaac62-boot-v1", mode: str = "boot", accept_nvidia_eula: bool = False):
    import subprocess
    import sys

    if not accept_nvidia_eula:
        raise ValueError("Pass --accept-nvidia-eula only after accepting NVIDIA terms")
    profile = os.environ.get("MODAL_PROFILE", "nikhilthakuraan")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Select one of the user-authorized Modal profiles")
    billing = subprocess.run(
        [sys.executable, "-m", "modal", "billing", "summary", "--json", "--profile", profile],
        capture_output=True,
        text=True,
        timeout=45,
        check=True,
    )
    budget = json.loads(billing.stdout)
    used = abs(float(budget["adjustments"]["credits"]))
    if float(budget["billed_cost"]) > 0 or 30 - used < 0.75:
        raise RuntimeError("Insufficient verified free credits for this bounded trial")
    target = Path("artifacts/embernet/isaac") / run_id
    target.mkdir(parents=True, exist_ok=True)
    (target / "billing-before.json").write_text(json.dumps(budget, indent=2))
    print(f"Free-credit guard: ${30 - used:.2f} remaining on {profile}; trial bound below $0.75", flush=True)
    call = runtime_trial.spawn(run_id, mode, license_acknowledged=True)
    print(f"Bounded Isaac call: {call.object_id}", flush=True)
    result = call.get()
    for name in result["files"]:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        with (target / name).open("wb") as stream:
            for chunk in volume.read_file(f"{run_id}/{name}"):
                stream.write(chunk)
    print(json.dumps(result, indent=2))
    if not result["process"]["success"]:
        raise RuntimeError(f"Isaac process failed; full logs downloaded to {target}")

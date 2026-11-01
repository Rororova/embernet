"""Bounded RTX/Vulkan capability probe; no Isaac installation or EULA acceptance."""

import json

import modal

app = modal.App("embernet-isaac-preflight")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libvulkan1", "vulkan-tools", "libegl1", "libgl1")
    .env({"NVIDIA_DRIVER_CAPABILITIES": "all"})
)


@app.function(
    image=image,
    gpu=["A10", "L4", "L40S"],
    cpu=2,
    memory=4096,
    timeout=120,
    retries=0,
    max_containers=1,
    scaledown_window=2,
)
def probe():
    import glob
    import subprocess

    results = {}
    for name, command in {
        "gpu": ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        "vulkan": ["vulkaninfo", "--summary"],
        "libraries": ["ldconfig", "-p"],
    }.items():
        run = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        stdout = run.stdout
        if name == "libraries":
            stdout = "\n".join(
                line
                for line in stdout.splitlines()
                if any(k in line.lower() for k in ("vulkan", "nvidia", "libegl"))
            )
        results[name] = {"exit": run.returncode, "stdout": stdout[-12000:], "stderr": run.stderr[-3000:]}
    results["icd_files"] = glob.glob("/usr/share/vulkan/icd.d/*") + glob.glob("/etc/vulkan/icd.d/*")
    results["devices"] = [p for p in glob.glob("/dev/nvidia*") + glob.glob("/dev/dri/*")]
    print(json.dumps(results, indent=2), flush=True)
    return results


@app.local_entrypoint()
def main():
    from pathlib import Path

    with modal.enable_output():
        result = probe.remote()
    out = Path("artifacts/embernet/isaac")
    out.mkdir(exist_ok=True)
    (out / "modal-preflight.json").write_text(json.dumps(result, indent=2), encoding="utf-8")

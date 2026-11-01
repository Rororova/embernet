"""Bounded native worker execution and durable evidence; no hardware connection."""

import json
from pathlib import Path


def execute_trial(run_id, mode, volume, license_acknowledged=False):
    import hashlib
    import os
    import shutil
    import subprocess
    import sys
    import time
    from importlib.metadata import version

    import embernet.isaac

    if not license_acknowledged or mode not in ("boot", "flight", "fleet", "px4"):
        raise ValueError("Explicit license consent and a supported trial are required")
    if not run_id.replace("-", "").isalnum():
        raise ValueError("Invalid run ID")
    os.makedirs("/tmp/embernet-xdg", mode=0o700, exist_ok=True)
    out = Path("/runs") / run_id
    out.mkdir(exist_ok=False)
    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    source = Path(embernet.isaac.__file__).parent
    provenance = {
        "runtime": version("isaacsim"),
        "python": sys.version,
        "mode": mode,
        "gpu": gpu.stdout.strip(),
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob("*.py")},
        "model_sha256": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (Path("/opt/mission.pt"), Path("/opt/fire-smoke.onnx"))
        },
    }
    (out / "runtime.json").write_text(json.dumps(provenance, indent=2))
    started = time.monotonic()
    env = dict(os.environ, EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED="YES", PYTHONUNBUFFERED="1")
    with (out / "kit-console.log").open("w") as console:
        try:
            run = subprocess.run(
                [sys.executable, "-m", "embernet.isaac.worker", "--mode", mode, "--output", str(out)],
                stdout=console,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=780,
                check=False,
            )
            status = {"return_code": run.returncode, "elapsed_seconds": time.monotonic() - started}
        except subprocess.TimeoutExpired:
            status = {"return_code": -1, "timeout": True, "elapsed_seconds": time.monotonic() - started}
    status["completed_report"] = (out / "report.json").is_file()
    status["exception_recorded"] = (out / "exception.txt").is_file()
    status["success"] = (
        status["return_code"] == 0 and status["completed_report"] and not status["exception_recorded"]
    )
    (out / "process.json").write_text(json.dumps(status, indent=2))
    kit_logs = Path(
        f"/usr/local/lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages/isaacsim/kit/logs/Kit"
    )
    for log in kit_logs.rglob("*.log"):
        shutil.copy2(log, out / log.name)
    volume.commit()
    return {
        "process": status,
        "files": [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()],
    }

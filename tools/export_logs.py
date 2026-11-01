"""Download every available EMBERNET application log from this build day."""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

output = Path("artifacts/embernet/logs")
output.mkdir(parents=True, exist_ok=True)
environment = {**os.environ, "MODAL_PROFILE": "nikhilthakuraan", "PYTHONUTF8": "1"}
base = [sys.executable, "-m", "modal"]
listed = subprocess.run(
    base + ["app", "list", "--json"],
    env=environment,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=60,
    check=True,
)
apps = [app for app in json.loads(listed.stdout) if app["description"] == "embernet-training"]
(output / "apps.json").write_text(json.dumps(apps, indent=2), encoding="utf-8")
index = []
containers = set()
until = datetime.now(UTC).isoformat()
for app in apps:
    identifier = app["app_id"]
    args = base + [
        "app",
        "logs",
        identifier,
        "--since",
        "2026-10-30T18:30:00Z",
        "--until",
        until,
        "--timestamps",
        "--show-container-id",
        "--show-function-call-id",
        "--show-function-id",
    ]
    result = subprocess.run(
        args, env=environment, capture_output=True, text=True, encoding="utf-8", timeout=90, check=False
    )
    (output / f"{identifier}.log").write_text(result.stdout, encoding="utf-8")
    (output / f"{identifier}.stderr.log").write_text(result.stderr, encoding="utf-8")
    index.append(
        {
            "app_id": identifier,
            "state": app["state"],
            "exit_code": result.returncode,
            "lines": len(result.stdout.splitlines()),
            "file": f"{identifier}.log",
        }
    )
    print(f"{identifier}: {len(result.stdout.splitlines())} lines; exit {result.returncode}", flush=True)
    containers.update(re.findall(r"\bta-[A-Za-z0-9]+", result.stdout))
for identifier in sorted(containers):
    result = subprocess.run(
        base + ["container", "logs", identifier, "--all", "--timestamps"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    (output / f"container-{identifier}.log").write_text(result.stdout, encoding="utf-8")
    (output / f"container-{identifier}.stderr.log").write_text(result.stderr, encoding="utf-8")
for identifier in ["im-62A7Xh2MmkUDuRHvrG9PsV"]:
    result = subprocess.run(
        base + ["image", "logs", identifier, "--all"],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
        check=False,
    )
    (output / f"image-{identifier}.log").write_text(result.stdout, encoding="utf-8")
    (output / f"image-{identifier}.stderr.log").write_text(result.stderr, encoding="utf-8")
rates = subprocess.run(
    base + ["billing", "summary", "--for", "2026-10", "--json"],
    env=environment,
    capture_output=True,
    text=True,
    encoding="utf-8",
    timeout=60,
    check=False,
)
(output / "billing-after.json").write_text(rates.stdout, encoding="utf-8")
(output / "index.json").write_text(
    json.dumps(
        {
            "workspace": "nikhilthakuraan",
            "since": "2026-10-30T18:30:00Z",
            "until": until,
            "applications": index,
            "note": "All available stdout/stderr/system entries in the build-day range; no default last-100 truncation.",
        },
        indent=2,
    ),
    encoding="utf-8",
)

"""Export available PX4/cloud app and build logs, including failed attempts."""

import argparse
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--console", action="append")
    args = parser.parse_args()
    root = Path("artifacts/embernet")
    target = root / "cloud/provider-logs"
    target.mkdir(parents=True, exist_ok=True)
    consoles = [p for folder in ("px4", "cloud") for p in (root / folder).glob("*console.log")]
    if args.console:
        consoles = [Path(p) for p in args.console]
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in consoles)
    apps = set(re.findall(r"\bap-[A-Za-z0-9]{20,26}\b", text))
    images = set()
    for p in consoles:
        ids = re.findall(r"Built image (im-[A-Za-z0-9]+)", p.read_text(encoding="utf-8", errors="replace"))
        if ids:
            images.add(ids[-1])

    def download(item):
        kind, identifier = item
        extra = ["--tail", "20000", "--timestamps"] if kind == "app" else ["--all"]
        command = [
            sys.executable,
            "-m",
            "modal",
            kind,
            "logs",
            identifier,
            *extra,
            "--profile",
            os.environ.get("MODAL_PROFILE", "nikhilthakuraan"),
        ]
        try:
            r = subprocess.run(command, capture_output=True, timeout=40, check=False)
            data = r.stdout + r.stderr
            status = r.returncode
        except subprocess.TimeoutExpired as error:
            data = (error.stdout or b"") + (error.stderr or b"")
            status = "bounded live tail"
        path = target / f"{kind}-{identifier}.log"
        path.write_bytes(data)
        return {"kind": kind, "id": identifier, "status": status, "bytes": len(data)}

    items = [("app", identifier) for identifier in sorted(apps)] + [
        ("image", identifier) for identifier in sorted(images)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(download, items))
    (target / "inventory.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({"exports": len(results), "bytes": sum(r["bytes"] for r in results)}))


if __name__ == "__main__":
    main()

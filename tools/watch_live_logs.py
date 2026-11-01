"""Wait for one bounded shared run, then download its complete native logs."""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import modal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("sandbox_id")
    args = parser.parse_args()
    if not re.fullmatch(r"live-[0-9a-f]{12}", args.run_id) or not re.fullmatch(
        r"sb-[A-Za-z0-9]+", args.sandbox_id
    ):
        raise ValueError("Invalid session identity")
    root = Path(__file__).resolve().parents[1]
    sandbox = modal.Sandbox.from_id(args.sandbox_id)
    deadline = time.monotonic() + 720
    print("Waiting for bounded run " + args.run_id, flush=True)
    while time.monotonic() < deadline:
        if sandbox.poll() is not None:
            time.sleep(5)
            subprocess.run(
                [sys.executable, str(root / "tools/download_live_logs.py"), args.run_id],
                cwd=root,
                check=True,
                timeout=180,
            )
            print("Complete native logs downloaded", flush=True)
            return
        time.sleep(10)
    raise TimeoutError("Session did not finish within the bounded log-watch window")


if __name__ == "__main__":
    main()

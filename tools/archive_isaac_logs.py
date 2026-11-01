"""Download all available Isaac experiment app logs and complete image-build layers."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("artifacts/embernet/isaac")
TARGET = ROOT / "cloud-logs"


def main():
    TARGET.mkdir(parents=True, exist_ok=True)
    consoles = list(ROOT.glob("*console.log"))
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in consoles)
    apps = sorted(set(re.findall(r"\bap-[A-Za-z0-9]{20,26}\b", text)) | {"ap-fCtPDWZ9dOJSrurnn7A3a7"})
    # Last built image for each console includes its ancestors with --all.
    images = sorted(
        {
            ids[-1]
            for p in consoles
            if (
                ids := re.findall(
                    r"Built image (im-[A-Za-z0-9]+)", p.read_text(encoding="utf-8", errors="replace")
                )
            )
        }
    )
    images = sorted(set(images) | {"im-Lb3bVJeLcsXhWzecwOG8Hk"})
    results = []
    for kind, identifiers in (("app", apps), ("image", images)):
        for identifier in identifiers:
            extra = ["--tail", "20000", "--timestamps"] if kind == "app" else ["--all"]
            run = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "modal",
                    kind,
                    "logs",
                    identifier,
                    *extra,
                    "--profile",
                    "nikhilthakuraan",
                ],
                capture_output=True,
                timeout=60,
                check=False,
            )
            path = TARGET / f"{kind}-{identifier}.log"
            path.write_bytes(run.stdout + run.stderr)
            results.append(
                {"kind": kind, "id": identifier, "exit_code": run.returncode, "bytes": path.stat().st_size}
            )
    (TARGET / "inventory.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

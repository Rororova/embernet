"""Download every session file, with hashes; control invites are never read or exported."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import modal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    args = parser.parse_args()
    if not args.run_id.startswith("live-") or not args.run_id.replace("-", "").isalnum():
        raise ValueError("Invalid run ID")
    volume = modal.Volume.from_name("embernet-live-logs")
    root = Path("artifacts/embernet/cloud") / args.run_id
    root.mkdir(parents=True, exist_ok=True)
    entries = [
        e for e in volume.iterdir(args.run_id, recursive=True) if e.type == modal.volume.FileEntryType.FILE
    ]

    def fetch(entry):
        relative = Path(entry.path).relative_to(args.run_id)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with target.open("wb") as stream:
            for data in volume.read_file(entry.path):
                stream.write(data)
                digest.update(data)
        return {"path": relative.as_posix(), "bytes": target.stat().st_size, "sha256": digest.hexdigest()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(fetch, entries))
    (root / "download-manifest.json").write_text(json.dumps(files, indent=2))
    print(
        json.dumps(
            {"run_id": args.run_id, "files": len(files), "bytes": sum(f["bytes"] for f in files)}, indent=2
        )
    )


if __name__ == "__main__":
    main()

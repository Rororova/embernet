"""Create an auditable local log/report bundle without credential or binary model files."""

import hashlib
import json
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
artifacts = root / "artifacts/embernet"
sources = list((artifacts / "logs").glob("*"))
sources += [p for p in artifacts.rglob("*.json") if "review" not in p.parts and "logs" not in p.parts]
sources += list((artifacts / "evaluation").glob("*.csv"))
sources += [
    p
    for folder in ("isaac", "px4", "cloud")
    for p in (artifacts / folder).rglob("*")
    if p.suffix in (".log", ".jsonl", ".txt", ".md", ".ulg", ".bson")
]
sources += list((root / "context").glob("*.md"))
sources += [root / "requirements.windows.lock.txt"]
sources = sorted(
    {
        p
        for p in sources
        if p.is_file()
        and ".private." not in p.name
        and p.name not in ("bundle-manifest.json", "project-manifest.json")
    }
)
manifest = {
    str(p.relative_to(root)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources
}
(artifacts / "logs/bundle-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
sources.append(artifacts / "logs/bundle-manifest.json")
target = artifacts / "EMBERNET-logs-and-reports.zip"
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for source in sources:
        archive.write(source, source.relative_to(root))
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    for name, digest in manifest.items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == digest
print(f"Verified {len(sources)} files in {target} ({target.stat().st_size} bytes)")

"""Package source, checkpoints, evidence and logs using an explicit allowlist."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts/embernet"
files = set()
for folder in ("embernet", "context", "tests", "tools", "config"):
    files.update(p for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
for name in (
    "README.md",
    "AGENTS.md",
    "PRODUCT.md",
    "DESIGN.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "requirements.windows.lock.txt",
    "Start-EMBERNET.cmd",
    "Start-EMBERNET.ps1",
    "Setup-EMBERNET.ps1",
    "Run-EMBERNET-Isaac.ps1",
    "Run-EMBERNET-Cloud.ps1",
    "cloud_train.py",
    "cloud_isaac_runtime.py",
    "cloud_isaac_probe.py",
    "cloud_px4.py",
    "cloud_live.py",
    "cloud_render_probe.py",
):
    files.add(ROOT / name)
files.add(ROOT / ".impeccable/design.json")
for folder in (
    "embernet-v1",
    "embernet-v2",
    "pretrained",
    "real-perception",
    "logs",
    "release-review",
    "release-demo",
    "isaac",
    "px4",
    "cloud",
):
    files.update(p for p in (ART / folder).rglob("*") if p.is_file() and "settings" not in p.parts)
files.update(p for p in (ART / "evaluation").rglob("*") if p.suffix in (".json", ".csv"))
excluded = {
    "upgrade_visual_ui.py",
    "upgrade_rerun_scene.py",
    "fix_scene_buffers.py",
    "retire_legacy.py",
    "rerun-overview.png",
    "evidence-mobile.png",
    "field-preview.usda",
}
files = sorted(
    p
    for p in files
    if p.is_file()
    and p.name not in excluded
    and ".private." not in p.name
    and "nvidia-vegetation" not in p.parts
    and "nvidia-wildland" not in p.parts
    and "nvidia-city" not in p.parts
    and "nvidia-tower" not in p.parts
)
manifest = {
    str(p.relative_to(ROOT)).replace("\\", "/"): {
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in files
}
manifest_path = ART / "project-manifest.json"
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
target = ART / "EMBERNET-project.zip"
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in files:
        archive.write(path, "EMBERNET/" + path.relative_to(ROOT).as_posix())
    archive.write(manifest_path, "EMBERNET/artifacts/embernet/project-manifest.json")
with zipfile.ZipFile(target) as archive:
    assert archive.testzip() is None
    for path, record in manifest.items():
        assert hashlib.sha256(archive.read("EMBERNET/" + path)).hexdigest() == record["sha256"], path
print(
    json.dumps(
        {
            "archive": str(target),
            "files": len(files) + 1,
            "bytes": target.stat().st_size,
            "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        },
        indent=2,
    )
)

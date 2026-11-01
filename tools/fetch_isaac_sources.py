"""Audit public source and asset manifests without installing Isaac or accepting its EULA."""

import json
import re
from pathlib import Path
from urllib.request import Request, urlopen

OUT = Path("artifacts/embernet/isaac/sources")
OUT.mkdir(parents=True, exist_ok=True)


def read(url):
    with urlopen(Request(url, headers={"User-Agent": "EMBERNET/0.1"}), timeout=45) as response:
        return response.read()


tag = json.loads(read("https://api.github.com/repos/PegasusSimulator/PegasusSimulator/git/ref/tags/v5.1.0"))
sha = tag["object"]["sha"]
if tag["object"]["type"] == "tag":
    sha = json.loads(read(tag["object"]["url"]))["object"]["sha"]
(OUT / "pegasus-revision.json").write_text(json.dumps({"tag": "v5.1.0", "commit": sha}, indent=2))
tree = json.loads(
    read(f"https://api.github.com/repos/PegasusSimulator/PegasusSimulator/git/trees/{sha}?recursive=1")
)
(OUT / "pegasus-tree.json").write_text(json.dumps(tree, indent=2))
interesting = [
    x["path"]
    for x in tree["tree"]
    if x["type"] == "blob"
    and any(
        s in x["path"]
        for s in (
            "examples/",
            "multirotor.py",
            "backends/backend.py",
            "px4_mavlink_backend.py",
            "params.py",
            "state.py",
        )
    )
]
print("PEGASUS", sha, "relevant files", interesting[:45])
index = read(
    "https://raw.githubusercontent.com/NVIDIA-Omniverse/simready-central/main/submissions/nvidia/simready-assets"
).decode()
(OUT / "nvidia-simready-index.txt").write_text(index)
matches = [
    line
    for line in index.splitlines()
    if re.search("exting|traffic|cone|water|tank|tree|forest|drone|barrier", line, re.IGNORECASE)
]
(OUT / "simready-candidates.json").write_text(json.dumps(matches, indent=2))
print("NVIDIA matching packages", len(matches))
print("\n".join(matches[:20]))

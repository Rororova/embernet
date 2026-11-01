"""Read public publisher manifests; never reads local account credentials."""

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

OUT = Path("artifacts/embernet/real-perception/sources")
OUT.mkdir(parents=True, exist_ok=True)
URLS = {
    "model": "https://huggingface.co/api/models/rabahdev/fire-smoke-yolov8n",
    "dataset": "https://www.kaggle.com/api/v1/datasets/view/brycehopkins/flame-3-computer-vision-subset-sycan-marsh",
    "files": "https://www.kaggle.com/api/v1/datasets/list/brycehopkins/flame-3-computer-vision-subset-sycan-marsh?pageSize=10000",
}
for name, url in URLS.items():
    with urlopen(Request(url, headers={"User-Agent": "EMBERNET/0.1"}), timeout=45) as response:
        data = json.load(response)
    (OUT / f"{name}.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    if name == "model":
        print(name, data["sha"])
    elif name == "dataset":
        print(name, {k: v for k, v in data.items() if "license" in k.lower() or "version" in k.lower()})
    else:
        files = data.get("datasetFiles", [])
        while data.get("nextPageToken"):
            page_url = (
                URLS["files"].split("?")[0]
                + "?"
                + urlencode({"pageSize": 200, "datasetVersionNumber": 1, "pageToken": data["nextPageToken"]})
            )
            with urlopen(Request(page_url, headers={"User-Agent": "EMBERNET/0.1"}), timeout=45) as response:
                data = json.load(response)
            files.extend(data.get("datasetFiles", []))
        inventory = [{"name": f["name"], "bytes": f["totalBytes"]} for f in files]
        (OUT / "inventory.json").write_text(json.dumps(inventory, indent=2), encoding="utf-8")
        print(name, len(files), "examples", [f["name"] for f in files[:: max(1, len(files) // 12)]])

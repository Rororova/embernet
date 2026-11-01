"""Fetch the small, attributed visual assets used by the live city scenario."""

import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path("artifacts/embernet/isaac/assets")
FILES = {
    "px4-iris/iris.stl": {
        "url": "https://raw.githubusercontent.com/PX4/PX4-SITL_gazebo-classic/ab7dbc572b4519238f8263ef4a288e6eb80a6076/models/iris/meshes/iris.stl",
        "bytes": 3999884,
        "source": "3DR Iris mesh by Thomas Gubler, maintained by Lorenz Meier/PX4",
    },
    "px4-iris/model.config": {
        "url": "https://raw.githubusercontent.com/PX4/PX4-SITL_gazebo-classic/ab7dbc572b4519238f8263ef4a288e6eb80a6076/models/iris/model.config",
        "source": "PX4 SITL Gazebo Classic model attribution",
    },
    "city-materials/asphalt_02/diffuse.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_diff_1k.jpg",
        "bytes": 731707,
        "md5": "fa19772d4817754c3efab708c651f5a8",
        "source": "Poly Haven asphalt_02, CC0",
    },
    "city-materials/asphalt_02/roughness.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_rough_1k.jpg",
        "bytes": 544032,
        "md5": "ec80a2929797c1b3ffc121c4f665585a",
        "source": "Poly Haven asphalt_02, CC0",
    },
    "city-materials/asphalt_02/normal.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_nor_gl_1k.jpg",
        "bytes": 1240122,
        "md5": "338da8de636ea36133170578cac82e8e",
        "source": "Poly Haven asphalt_02, CC0",
    },
    "city-materials/concrete_wall_006/diffuse.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/concrete_wall_006/concrete_wall_006_diff_1k.jpg",
        "bytes": 769415,
        "md5": "62ac61307a3321ecec26e1abd045f2ab",
        "source": "Poly Haven concrete_wall_006, CC0",
    },
    "city-materials/concrete_wall_006/roughness.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/concrete_wall_006/concrete_wall_006_rough_1k.jpg",
        "bytes": 255004,
        "md5": "660e38696f8c92d1585b17b7cc01cc06",
        "source": "Poly Haven concrete_wall_006, CC0",
    },
    "city-materials/concrete_wall_006/normal.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/concrete_wall_006/concrete_wall_006_nor_gl_1k.jpg",
        "bytes": 1195078,
        "md5": "337cf8d33598e1ecd036ef3727a4b36d",
        "source": "Poly Haven concrete_wall_006, CC0",
    },
    "city-materials/brick_wall_001/diffuse.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/brick_wall_001/brick_wall_001_diffuse_1k.jpg",
        "bytes": 574381,
        "md5": "955d2d4500eb549be0f2873305782798",
        "source": "Poly Haven brick_wall_001, CC0",
    },
    "city-materials/brick_wall_001/roughness.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/brick_wall_001/brick_wall_001_rough_1k.jpg",
        "bytes": 211093,
        "md5": "618ceca60a4321aecc6d61eebe53d551",
        "source": "Poly Haven brick_wall_001, CC0",
    },
    "city-materials/brick_wall_001/normal.jpg": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/brick_wall_001/brick_wall_001_nor_gl_1k.jpg",
        "bytes": 295279,
        "md5": "be151875ed0897fc716aeef6daac8bd5",
        "source": "Poly Haven brick_wall_001, CC0",
    },
}


def main():
    manifest = {"files": {}}
    for relative, spec in FILES.items():
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        request = Request(spec["url"], headers={"User-Agent": "EMBERNET-city-assets/1.0"})
        with urlopen(request, timeout=90) as response:
            payload = response.read()
        if "bytes" in spec and len(payload) != spec["bytes"]:
            raise RuntimeError(f"Unexpected asset size: {relative}")
        if "md5" in spec and hashlib.md5(payload).hexdigest() != spec["md5"]:
            raise RuntimeError(f"Asset MD5 mismatch: {relative}")
        target.write_bytes(payload)
        manifest["files"][relative] = {
            "url": spec["url"],
            "source": spec["source"],
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        print(f"Verified {relative}", flush=True)
    (ROOT / "city-assets-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

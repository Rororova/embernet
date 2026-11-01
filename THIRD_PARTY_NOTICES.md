# Third-party assets and models

- Three.js 0.186.1 and included addons: MIT; retained at
  `embernet/ui/vendor/LICENSE`. Forest, quadrotor and person GLBs are authored here.
- Rajdhani font: see its accompanying license in `embernet/ui/fonts/`.
- Fire/smoke checkpoint: rabahdev/fire-smoke-yolov8n, Hugging Face revision
  13017fe8af477c25f5298d168e2dfede4b000753. Model card and AGPL-3.0 text are
  included in `artifacts/embernet/pretrained/fire-smoke-yolov8n/`. ONNX is derived
  from those weights. Ultralytics supplies the architecture/export classes.
- FLAME 3 CV subset, Bryce Hopkins et al., Sycan Marsh, Kaggle version 1:
  https://www.kaggle.com/datasets/brycehopkins/flame-3-computer-vision-subset-sycan-marsh/versions/1
  Publisher metadata reports MIT. Source metadata, original names and hashes are
  retained beside the 48 selected RGB/temperature pairs. Originals are unmodified.
  Paper: https://arxiv.org/abs/2412.02831; DOI: 10.21227/w0mz-aq48.
- Real-detector fine-tuning data: Hajorda/flameye-wildfire-detection, revision
  361a3dea8b877482af9f4ed80eff77ffd39926ef, publisher license CC-BY-4.0.
  https://huggingface.co/datasets/Hajorda/flameye-wildfire-detection
  Only the pinned shards listed in the candidate dataset manifest are sampled.
  FlamEye combines D-Fire (CC0 collection notice and third-party source caveats),
  Pyro-SDIS and AI for Mankind; original source notices and attribution remain
  applicable. The upstream dataset card is retained with the candidate artifacts.
  Derived fine-tuned checkpoints remain AGPL-3.0 like the base YOLOv8n model.

Dependency licenses remain with their packages. The only Poly Haven-origin assets
are the HDR skies redistributed in NVIDIA's content listed under the wildland entry.

- NVIDIA SimReady Central barrier_wall_plastic_orange_a03 and
  fireExtinguisher_abc_a03: CC-BY-4.0, creator NVIDIA, no asset edits.
  https://huggingface.co/datasets/nvidia/simready-assets/tree/653d91e182011f357cf1644013cc94ddf194d349
  https://creativecommons.org/licenses/by/4.0/
  Full file hashes, upstream BOM and package metadata are preserved per asset
  under artifacts/embernet/isaac/assets/. Scene composition is authored here.
- Isaac Sim / Omniverse Kit: separately installed from NVIDIA, user-accepted
  terms; their binary runtimes are excluded from project archives.
- Pegasus v5.1.0: BSD-3-Clause, Marcelo Jacinto and contributors; installed only
  in the isolated cloud image from pinned upstream commit. PX4 is not installed.

- NVIDIA Black Oak vegetation and its materials/textures: official Omniverse
  sample content used under accepted NVIDIA terms; not bundled in source ZIP.
  config/isaac/vegetation.json and tools/fetch_nvidia_vegetation.py preserve
  exact source paths, recorded hashes and separate download instructions.
  https://docs.omniverse.nvidia.com/composer/latest/prod_content/mount-content.html

- NVIDIA City Tower Demo Pack NVD@10011: NVIDIA authored building, facade, city
  and site USD assemblies and bundled textures, acquired from the official
  downloadable content packs. Runtime composition converts units and scales
  the tower; original asset files remain separate. Archive SHA256 and exact
  source URL are recorded in context/ARCHITECTURAL_RUN.md. NVIDIA Omniverse
  content/software terms apply; raw vendor packs are excluded from this ZIP.
  https://docs.omniverse.nvidia.com/usd/latest/usd_content_samples/downloadable_packs.html
  tools/fetch_nvidia_tower.py reproduces the accepted R&D asset download.

- NVIDIA wildland content: Omniverse Assets/Vegetation (trees, shrubs, grasses,
  rocks, debris), Isaac 6.2 Base/Natural materials, Particles textures and Skies,
  used under accepted NVIDIA terms and not bundled in the source ZIP. The sky HDRs
  keep their upstream filenames from NVIDIA's content (Poly Haven origin).
  config/isaac/wildland.json pins every file's source path, size and SHA-256;
  tools/fetch_nvidia_wildland.py reproduces the download.

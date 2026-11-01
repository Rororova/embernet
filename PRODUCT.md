# EMBERNET

EMBERNET combines a research simulator for decentralized wildfire-response drones with a separate real-observation review. Researchers and demo operators can run repeatable forest scenarios, introduce incidents and radio faults, inspect aircraft decisions, and compare pretrained RGB detections with source thermal measurements.

The core workflow starts with a scenario seed and six aircraft by default. Choose reference or neural perception and baseline or learned mission decisions, reset with those settings, then launch, pause, resume, or change simulation speed. Neural choices become available when their checkpoints are loaded.

The primary presentation is a live Three.js forest scene with recognizable suppression quadrotors, conifers, terrain, field-station geometry, people, fire, smoke, and simulated discharge. Operators can orbit the scene, follow the selected aircraft, use Scene POV, or enter Focus view. The settings drawer contains scenario setup, incident placement and mesh faults. Fire, person, and animal incidents can be placed in the scene or entered by coordinates. Fleet buttons provide an alternative to selecting aircraft in 3D.

Inspection combines the selected aircraft's local incident ledger, decision reason, resources, peers heard, model input thumbnails, and observed decision events. Simulator truth is explicitly labeled and separate from actor knowledge. Water effects require an executed simulated discharge; assignment to a suppression task alone does not establish discharge.

The standard launcher opens the browser scene. Native Rerun is opt-in with `-Rerun` or `-TelemetryOnly` and provides telemetry/replay. It decodes the shared forest, aircraft and person GLB arrays into native Mesh3D geometry, with additional fire/smoke geometry. Recording and optional live output use explicit sink fanout. Latest recording CLI verification passes; final native visual verification remains pending. Browser controls export the recording and mission replay. Preserve trained autonomy, downloaded training logs and original reports.

The interactive world's CNN remains a synthetic-trained prototype using 64×64 procedural RGB/IR images; Scene POV is a presentation camera. Its existing results establish synthetic-domain behavior only.

`/perception` reviews 48 downloaded FLAME 3 v1 RGB/Celsius-TIFF pairs from one prescribed burn. The default `real-perception-v1-20261101-e1` detector is a four-epoch, real-image fine-tune of the pinned Hugging Face `rabahdev/fire-smoke-yolov8n` checkpoint (3,011,238 parameters), exported to ONNX for CPU inference. Training used 900 annotated real images and 260 validation images from pinned FlamEye shards; FLAME 3 stayed out of training, checkpoint selection and threshold tuning. Operators browse independent observations, overlays, thermal measurements, source labels, timing warnings and provenance. The original pretrained baseline report is preserved.

At fixed defaults, the fine-tune's RGB fire-or-smoke warnings occurred on 24/24 source-fire and 0/24 source-no-fire samples; the original baseline had three false warnings. All positive warnings came from smoke; flame-only recall remains 0/24. This small single-burn sample does not establish broad generalization. Thermal threshold agreement with all folder labels may reproduce the labeling heuristic and is not independent validation. Raw EXIF dates indicate 2022 while the publisher describes 2023; the camera clock is unverified. The page presents independent samples, without a verified flight timeline, calibrated severity, world localization or suppression inference. Recorded footage does not respond to simulated actions. See [context/REAL_PERCEPTION.md](context/REAL_PERCEPTION.md) for current evidence and [context/REAL_DATA_PERCEPTION_HANDOFF.md](context/REAL_DATA_PERCEPTION_HANDOFF.md) for the broader direction.

Product commitments:

- Actors use their own state/observations and delivered messages only; reports retain their original evidence timestamps.
- A bid does not establish an acknowledged commitment. Safe release requires fresh acknowledged capacity and matching versions.
- Survivor evidence outranks fire size; deferred incidents remain reviewable.
- Learning proposes tasks and bids; explicit negotiation and flight safety remain independent.
- Physical actuation is disabled. Interactive fire, cameras, thermal values, and demand estimates are synthetic; recorded thermal measurements retain their source assumptions. A person reached is not a rescue.
- PX4/Isaac/ROS/ns-3 and physical sensors or radios remain future integrations until implemented and verified.

Current implementation lives in `embernet/`; `.legacy/before-embernet/` is retired. Operational truth, run results, setup, and limitations belong in [context/README.md](context/README.md), [context/STATUS.md](context/STATUS.md), and the linked module documents. Browser visual guidance is in [DESIGN.md](DESIGN.md).

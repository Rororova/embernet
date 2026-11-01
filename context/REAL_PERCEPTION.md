# Real-data perception

Implemented after the user requested an existing small Hugging Face model and
delegated integration. Historical REAL_DATA_PERCEPTION_HANDOFF.md describes the
earlier direction; no real data had been obtained at that time.

## Model/runtime

`rabahdev/fire-smoke-yolov8n`, revision
`13017fe8af477c25f5298d168e2dfede4b000753`, AGPL-3.0, 3,011,238 parameters.
Classes smoke/fire. Downloaded PT: 6.23 MB; exported FP32 ONNX: 12.25 MB.
Publisher reports D-Fire training; not independently audited. Checkpoint loading
uses weights_only=True with explicit installed-class allowlisting. ONNX checker
and Torch/ONNX parity passed (max absolute difference 0.00138). Normal runtime
uses ONNX Runtime CPU, not pickle or remote code.

`real_perception.py`: RGB letterbox 640x640, confidence .25, class-aware NMS .45,
inverse image-coordinate mapping, annotated images. CLI: `embernet perceive SOURCE`.
No uncalibrated mapping from image boxes into mission world coordinates. The default
is the verified fine-tune when installed, with fallback to the original checkpoint.

## Real-image fine-tune: real-perception-v1-20261101-e1

The base checkpoint was fine-tuned for four epochs on an NVIDIA A10 in Modal
(398.62 seconds, seed 217, 640 pixels, batch 16, AdamW lr0 .0005, lrf .1). Training
used 900 annotated real images and 260 validation images from pinned FlamEye
Parquet shards (`Hajorda/flameye-wildfire-detection`, revision
`361a3dea8b877482af9f4ed80eff77ffd39926ef`). Exact categories: 200 D-Fire fire,
400 new Pyro/AI-for-Mankind smoke, 100 D-Fire smoke-only and 200 negatives for
training; 50/120/30/60 respectively for validation. The base was already trained
on D-Fire; Pyro/AI-for-Mankind are the added sources. This is a small mixed-source
fine-tune, not a from-scratch or cross-burn experiment.

Source shards and every downloaded artifact are SHA-256 verified. Publisher boxes
are structurally validated; boundary overflows up to 1% are clipped. A 24-image
sheet covering all categories and new sources was visually spot-checked, not
independently relabelled. FlamEye validation selects the checkpoint but may share
scenes/adjacent frames. No FLAME 3 image entered training, selection or tuning.
Selected validation: precision .7717, recall .7136, mAP50 .7579, mAP50-95 .4248.
Exported ONNX parity max absolute error is .000305. Checkpoints, manifests,
contact sheet, training curves and logs are under
`artifacts/embernet/real-perception-v1-20261101-e1/`. Failed attempts a1-d1 are
retained with their causes; e1 is the only completed candidate. Final billing
snapshot: $19.73 free credits applied and $0 billed for the cycle; all five
perception-training apps (four failed attempts plus e1) are stopped.

## Data/evidence

Audited publisher Kaggle v1: 2,952 files, 622 fire + 116 no-fire pairs with four
modalities each. Selected 24 evenly spaced IDs per class; downloaded 48 corrected
FOV RGB + original Celsius TIFF pairs (66,398,595 bytes). Publisher API reports
MIT. Originals, public source names, sizes and SHA-256 hashes are retained.
Held-out inspection sample; no FLAME 3 training, checkpoint selection or threshold
tuning. One Sycan Marsh prescribed burn; no cross-burn validation or independent
box/mask annotations.
Several raw camera timestamps say 2022 while the publisher describes 2023; the
review flags the discrepancy and never manufactures capture chronology.

Thermal statistics retain all finite source temperatures, including values above
600Â°C. Preview clips display to 10â€“150Â°C, never the measurements. Baseline:
â‰¥0.05% pixels at â‰¥100Â°C. Calibration/saturation remain sensor assumptions;
residual RGB/thermal offsets up to ~20 pixels preclude asserted dense alignment.

## Results

Original pretrained baseline: RGB fire-or-smoke warnings on 24/24 source-fire
samples and 3/24 source-no-fire samples (precision .8889, specificity .875).
Fine-tuned e1 on the same fixed 48 samples: 24/24 source-fire and 0/24
source-no-fire warnings (precision/recall/specificity 1.0 on this small set).
FLAME 3 remained held out, so this is a valid comparison of these observations,
not proof of broad generalization. Both models' positive warnings came from smoke;
flame-only recall remains 0/24. Do not describe either as successful flame
detection. Thermal threshold agrees with all 48 folder labels, but may reproduce
their original labeling heuristic. No severity, survivor assessment, water-demand
inference or localization accuracy is validated. CPU per-frame times are in the
respective reports, not a hardware FPS promise.

## Review/reproduction

`/perception` shows independent recorded observations, both modalities, overlays,
source labels, temperatures, errors and provenance. It serves the e1 review when
installed; the original baseline report remains unchanged at
`/evidence/report.json`. Frame order is not a verified flight timeline. Interactive
/ retains its procedural CNN and trained mission actor; recorded data does not
change when simulated water is used.

Baseline tools: audit_perception_sources.py â†’ fetch_flame3_sample.py â†’
prepare_pretrained_detector.py â†’ benchmark_real_perception.py. Fine-tuning:
`tools/launch_perception_training.py RUN_ID --epochs 4`, then
`tools/fetch_perception_training.py RUN_ID`. `cloud_perception.py` enforces unique
runs, a single GPU container, 1800-second timeout and no retries; the launcher
checks free-credit headroom before dispatch. The benchmark accepts `--model` and
`--output` for candidate evaluation without overwriting baseline evidence. Network
steps are public inbound requests; local export needs model-tools extra. Models,
data and reports live under artifacts/embernet/.

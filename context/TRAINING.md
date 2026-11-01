# Training

## Perception

64x64 RGB plus synthetic IR. Separate CNN encoders fuse features, then predict
three segmentation masks (fire/person/animal) and normalized fire severity.
Loss: positive-weighted BCE + Dice + fire-masked severity MAE; AdamW.
Runtime uses image-only connected components above 0.55 probability and projects
centroids/areas to the synthetic footprint. Truth IDs/labels never enter inference.

Procedural data varies ground, trees, flames, sizes, intensity and subjects, with
hot-rock negatives. The training and runtime renderer are shared. This is
synthetic-domain evidence, not real-camera performance or thermal calibration.

V1: 1,536 training / 256 validation images, 10 epochs, seed 210. IoU fire/person/
animal = 0.9035/0.8921/0.8381; severity MAE 0.03394. V2 specifically includes
1.5–4m fire radii omitted from V1, using 2,048 images, 12 epochs, seed 211.
V2 IoU fire/person/animal = 0.9217/0.9383/0.9033, severity MAE 0.05091, on
NVIDIA A10. Its sampled validation size distribution differs from V1.

## Real-image detector fine-tuning

`cloud_perception.py` fine-tunes the pinned fire/smoke YOLOv8n checkpoint on real
annotated images, separately from the synthetic CNN above. The completed
`real-perception-v1-20261101-e1` run used 900 training and 260 validation images,
four epochs, seed 217, batch 16, AdamW lr0 .0005/lrf .1 on one A10. Exact source
shards, deterministic category quotas and image hashes are recorded in its dataset
manifest. D-Fire was already represented in the base model; new smoke examples
come from Pyro-SDIS and AI for Mankind. FlamEye validation is checkpoint-selection
evidence only, not independent scene generalization.

FLAME 3 is excluded from training, selection and threshold tuning. Its 48-sample
comparison improved fire-or-smoke warning specificity from .875 to 1.0 while
retaining 24/24 source-fire warnings; flame-only recall remains 0/24. See
REAL_PERCEPTION.md for artifacts, failed attempts and limitations. Launch only via
`tools/launch_perception_training.py` with an authorized profile and fresh billing
check; use a unique run ID and recover artifacts with the matching fetch tool.

## Mission

Inputs: 10 own-state features; 6 incident slots x12 features; 16 received peer
slots x8 features; existence/action masks. Peer attention and pooled incidents
feed a 64-unit GRU. Ten actions: search/return/relay/hold/six incident preferences.
Preferences affect bids and task proposals; award/ACK/release/safety remain explicit.
Only the critic additionally receives 12 simulator-global training features.

Warm-start: 4,320 expert decisions, 12 episodes, 10 BC epochs. Then 12 clipped-PPO
updates over single fire -> competing fires -> survivors -> scarce resources ->
partitions. Gamma .99, GAE .95, clip .2, entropy .015, gradient clip .5 and a small
continuing imitation loss. PPO uses stored hidden states and one-step truncated
gradients; BC uses zero initial hidden states. Full sequence BPTT is future work.

Mission training uses reference sensors. Combining learned vision is a separate
evaluation. Validation seeds 61001/61002 select weights; held-out 91001–91004
evaluate. V1 selected update 8: baseline mean 36.2235, learned 40.7695. Four
synthetic scenarios do not establish statistical or field superiority. Preserve
original reports; runtime changes require fresh regressions.

Files per run: vision.pt, mission.pt, mission-bc.pt, vision-report.json,
mission-report.json, summary.json. V2 reuses the V1 mission policy. Load trusted
local weights with weights_only=True. Original V1 reports remain unchanged.

## Compute

Both profiles authorized; nikhilthakuraan credits verified before use. Initial
L4-only jobs queued without running. Availability fallback [L4,A10,T4] succeeded.
One container, 900s timeout, zero retries, 2s scale-down. Volume:
embernet-experiments. Unique run IDs prevent overwrites. Explicit dispatch:
tools/launch_training.py; recovery: tools/fetch_training.py RUN_ID.
Set process-local MODAL_PROFILE and PYTHONUTF8. Recheck free credits before new
jobs/cycles. Never log credential files.

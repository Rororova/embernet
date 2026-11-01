# EMBERNET

EMBERNET is a decentralized wildfire-response research platform with:

- a local multi-drone simulation for mission-control and coordination testing
- inspectable autonomy decisions (memory, bids, acknowledgements, safety)
- a separate real-image perception review flow (`/perception`)

It is built for experimentation, replay, and evidence-driven evaluation, not
real-world suppression deployment.

## Quick start (Windows)

1. Install `uv`.
2. Run:

```powershell
./Setup-EMBERNET.ps1
Start-EMBERNET.cmd
```

## Deck

- Live Hosted Link: https://ieirodov14--embernet-live-gateway.us-east.modal.run/
- Product Demo Video: https://drive.google.com/file/d/1oqAKpcZ8nhyMgXUtHU0b4C1HXLuV_iul/view?usp=sharing

## What is included

- 3D simulation with incidents, mesh faults, per-drone local state, and mission controls
- Baseline and learned mission decision paths
- Real-image ONNX inference and FLAME sample inspection workflow
- Telemetry and replay outputs (Rerun + JSONL)
- Optional cloud/Isaac/PX4 tracks documented under `context/`

## CLI examples

Use the project venv Python on Windows:

```powershell
.venv-embernet/Scripts/python.exe -m embernet serve --rerun
.venv-embernet/Scripts/python.exe -m embernet control pause
.venv-embernet/Scripts/python.exe -m embernet control fire --x 150 --y 120
.venv-embernet/Scripts/python.exe -m embernet perceive path/to/images
.venv-embernet/Scripts/python.exe -m pytest -q
```

Other supported commands include `embernet demo`, `embernet train vision|mission`,
`embernet replay`, and `embernet control` actions.

## Safety and scope boundaries

- Physical actuation is disabled.
- Interactive fire/smoke and many simulator signals are synthetic.
- A simulated person reached is **not** a rescue.
- Real-image review does not imply calibrated severity, localization, or suppression outcomes.
- ROS/ns-3/real radios/real flight/fire physics are only valid where explicitly implemented and verified.

## Key documentation

- [Agent context](context/README.md)
- [Runbook](context/RUNBOOK.md)
- [Status](context/STATUS.md)
- [Real perception](context/REAL_PERCEPTION.md)
- [Isaac setup and evidence](context/ISAAC_SIM.md)
- [PX4/cloud path](context/PX4_CLOUD.md)
- [Verification](context/VERIFICATION.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

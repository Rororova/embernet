# EMBERNET

Live wildfire-response research: a 3D drone swarm, decentralized incident memory,
resource negotiation, trained mission decisions, and real aerial-image review.

## Run

On this workstation, double-click **Start-EMBERNET.cmd**. It opens the live forest
at http://127.0.0.1:8780 and saves Rerun recordings. **Real observations**
opens the included FLAME 3 RGB/temperature review at http://127.0.0.1:8780/perception.

On a fresh Windows machine, install uv, run `Setup-EMBERNET.ps1`, then open the
launcher. Models, scene assets and selected real-data samples are included in the
project archive. No training or cloud account is needed to run the packaged demo.

## Included

- Recognizable quadrotors, forest/field station, fire, smoke and executed simulated
  water release. Orbit, follow, Scene POV and Focus view. Shared GLBs in Rerun.
- Six drones with separate local knowledge, delayed/lost mesh messages, retained
  deferred incidents, acknowledged commitments, safe diversion and replenishment.
- Independent safety, learned mission preferences, explicit baseline, saved replay,
  trained checkpoints and downloaded training/container/image logs.
- Pinned 3.01M-parameter fire/smoke detector, real-image fine-tuning on Modal,
  local ONNX inference, 48 held-out FLAME 3 RGB/radiometric pairs and reproducible results.

The interactive simulation retains its procedural sensor prototype. Real-image
review is separate: the completed real-data fine-tune produced fire-or-smoke
warnings on 24/24 held-out fire samples and 0/24 no-fire samples, improved from
three false warnings in the original baseline. Flame-only recall remains 0/24;
all positive warnings came from smoke. Thermal agreement with folder labels is
descriptive, not independent recognition validation.

```powershell
.venv-embernet/Scripts/python.exe -m embernet serve --rerun
.venv-embernet/Scripts/python.exe -m embernet control pause
.venv-embernet/Scripts/python.exe -m embernet control fire --x 150 --y 120
.venv-embernet/Scripts/python.exe -m embernet perceive path/to/images
.venv-embernet/Scripts/python.exe -m pytest -q
```

Fire/smoke does not establish survivorship, calibrated severity or required litres.
Person reached in simulation requires ground rescue. Hardware actuation remains
disabled. ROS/ns-3, real flight and fire physics remain future work. PX4 SITL now drives
Isaac PhysX motors; the shared cloud room is described in [PX4/cloud](context/PX4_CLOUD.md).

Isaac 6.2 cloud trials now run actual rotor-controlled PhysX flight, NVIDIA
forest/props, RGB/depth cameras and the existing trained mission actor across
three aircraft. A recorded packet outage blocks delivery and recovers after
reconnection. The main interactive dashboard still uses the kinematic backend.
Run `.\Run-EMBERNET-Isaac.ps1 -Mode fleet -AcceptNvidiaEula` or `-Mode flight`.
See [Isaac setup and evidence](context/ISAAC_SIM.md) for results, videos and limits.

[Agent context](context/README.md) · [Runbook](context/RUNBOOK.md) ·
[Real perception](context/REAL_PERCEPTION.md) · [Verification](context/VERIFICATION.md) ·
[Third-party notices](THIRD_PARTY_NOTICES.md).


The shared cloud city now uses NVIDIA architectural assets, actual PX4/PhysX
flight and NVENC H.264 video with mouse orbit/pan/zoom. The verified run received
23.95 fps and acknowledged a camera change in 578 ms. Fire/smoke remain stylized;
see [current architectural evidence](context/ARCHITECTURAL_RUN.md).
Run `.\Run-EMBERNET-Cloud.ps1` to fetch the pinned NVIDIA pack, deploy and prepare
one 600-second session within verified free credits. The public watch page is
https://nikhilthakuraan--embernet-live-gateway.us-east.modal.run . The private
control invite is kept outside release archives. Preparation alone starts no GPU.

The cloud room now runs a six-drone autonomous mission in the city or wildland, chosen at
launch: simulated-sensor discovery, mesh sharing, negotiated commitments, virtual suppression
and fresh-evidence clearance, with click-to-ignite. It uses virtual work, not real payloads;
see [swarm mission evidence and limits](context/SWARM_MISSION.md).

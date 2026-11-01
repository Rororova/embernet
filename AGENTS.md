# EMBERNET handoff

Read context/CURRENT_HANDOFF.md, README.md and STATUS.md first, then the relevant module documents.
The autonomous swarm mission is in context/SWARM_MISSION.md: world truth reaches actors only
through the labeled simulated sensor; virtual work needs an acknowledged commitment; physical
release stays off; holds use the active world's obstacles.
Old code lives in .legacy/before-embernet/; do not revive it or reuse its claims.
Latest user correction: the Isaac demo must visibly show mesh reaction, bird's-eye
and onboard views, a larger realistic city with a 30th-floor fire, better drones/
fire/surfaces and lower latency. RGB + synthetic IR is the current interpretation
of the unanswered RDR/IDR question. The verified city stream still has an opaque
smoke-card defect in the old procedural scene. NVIDIA architecture now renders;
read context/ARCHITECTURAL_RUN.md for current runs and unresolved acceptance. Keep
trained autonomy, failures and downloaded logs; never claim zero lag.

Actor inputs: own state/observations plus delivered messages only. Preserve
original evidence timestamps. A bid is not an acknowledged commitment. Safe
release counts only fresh acknowledged capacity and matching versions.
Flight safety stays independent of learning; physical actuation is disabled.
Isaac 6.2 cloud physics trials are verified; read context/ISAAC_SIM.md for scope/evidence.
Browser remains kinematic. Radio faults must set Mesh.isolated, not just a status flag.
PX4 SITL now drives verified Isaac PhysX flight. Shared cloud room: read context/PX4_CLOUD.md.
ROS/ns-3 and real hardware remain future. Never package *.private.json control invites.

Current source: 148 tests, Ruff and cloud/perception JS parser checks pass. Use
.venv-embernet/Scripts/python.exe (3.12), relevant pytest checks and Ruff.
Keep context concise and current with modes/seeds/results and limitations.
Modal is authorized within verified free quota: bounded jobs, unique run IDs,
persistent checkpoints and log downloads. Never expose credentials.

Real-data path is implemented separately at /perception. Read REAL_PERCEPTION.md.
The e1 real-image fine-tune has 24/24 fire and 0/24 no-fire warnings on held-out
FLAME3; flame-only recall remains 0/24 and warnings are smoke-only. Baseline had
3 false warnings. Never present source-thermal agreement as independent validation.
Rerun needs FileSink plus GrpcSink for live+disk; spawn(connect=True) replaces sinks.
Browser is primary; native final visual acceptance remains unverified.

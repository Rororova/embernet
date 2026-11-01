# Architecture

Runtime: `world -> renderer/sensor -> local ledger -> task preference -> mesh
negotiation -> command -> independent safety -> simulated flight -> telemetry`.

| Module | Responsibility |
| --- | --- |
| contracts.py | SI metre/second/litre schemas, normalized battery, immutable config |
| safety.py | Target/health/age/reserve/discharge validation; kinematic adapter and PX4 stub |
| perception.py | Paired RGB/IR renderer; dual CNN encoders; fire/person/animal masks and severity map; image-to-ground components |
| memory.py | Replaceable Memory protocol, incident ledger, provenance and deduplication |
| mesh.py | Range, delay, loss, multi-hop forwarding, deduplication and partitions |
| coordination.py | One Agent per drone: priorities, bids, awards, ACKs, release, deferral, ownership and navigation |
| simulation.py | Synthetic truth, observations, fire/resources, replenishment and contact measurement |
| learning.py | Local features, peer attention, GRU task actor and separate critic |
| training.py | Vision supervision, demonstrations/BC, clipped PPO/GAE and evaluation |
| telemetry.py / replay.py | Explicit Rerun stream, truth/knowledge separation, snapshot replay |
| server.py / ui/ | Optional loopback operator controls and recording exports |

Actor inputs are own state, own observations, and delivered reports. Simulator
truth is allowed only for sensors, propagation, training labels/rewards/critic,
and explicitly labeled operator inspection. Tests verify truth does not enter
actor observations before sensing.

Coordinates are right-handed Z-up local metres, X/Y [0,320] by default. A PX4
adapter must explicitly convert frames. Each drone has its own ground service
pad and cruise lane at `28 + 4*index` metres. Kinematics, not rotor physics.
Cameras use a synthetic 102m patrol footprint and a narrower 36m confirmation
view during response/verification. This models optical zoom, not extra pixels
from digital cropping. Optics do not vary with altitude. Rerun trees are scenery,
not collision geometry. Fire demand is
a scenario proxy. Person reached means response plus ground-rescue escalation,
not rescue.

Implemented external systems: PyTorch, Modal GPUs/Volumes, Rerun SDK/native
viewer, plus isolated Isaac 6.2/PhysX cloud trials (isaac/). PhysicsMission consumes
measured telemetry and emits independently checked navigation targets. Native rotor
control integrates a bounded wrench in PhysX. Browser kinematics remain separate.
PX4 SITL now consumes measured HIL sensors and returns motor outputs to PhysX;
the shared room streams native imagery through a bounded GPU Sandbox and a CPU gateway.
Read PX4_CLOUD.md. Future adapters: ROS 2, ns-3 and hardware. Pegasus 5.1 is prepared
but its older RTX runtime fails on the current cloud driver; see ISAAC_SIM.md.
No LLM or retrieval system runs in the control loop. PX4 owns eventual real
stabilization and motor control.

References: [PX4](https://docs.px4.io/main/en/flight_modes/offboard.html),
[Pegasus](https://github.com/PegasusSimulator/PegasusSimulator),
[MAPPO](https://arxiv.org/abs/2103.01955),
[Rerun](https://rerun.io/docs/reference/sdk-operating-modes),
[Modal](https://modal.com/docs/guide/gpu).

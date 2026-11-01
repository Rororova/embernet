# EMBERNET: how we drifted from the swarm objective, and how to recover

Status update: implemented and evidenced in [SWARM_MISSION.md](SWARM_MISSION.md). Neural
perception remains unconnected; the mission uses a labeled simulated sensor.

Date: 2026-11-01. This is an assessment and implementation handoff, not a claim
that the missing behavior has been built. The user's latest correction takes
precedence over earlier descriptions of the demo as complete.

## The actual objective

The user should be able to **watch autonomous drones work together inside the
simulation**: search, discover fires and possible survivors, share observations,
prioritize incidents, negotiate assignments, travel to them, perform simulated
work, and reconsider commitments when conditions change. The observer must see
both what the aircraft do and why their decisions change.

The motivating example remains the clearest acceptance case: a drone responding
to a large fire discovers a smaller fire en route. It compares arrival times,
asks whether its original team still needs it, diverts only after sufficient
remaining capacity is acknowledged, and remembers the smaller fire if it must
defer it. Possible survivors raise urgency above fire size alone.

Photoreal scenery, smooth streaming, PX4 and a website support that experience.
They do not establish that the swarm mission works.

## How we drifted

I treated improvements to the infrastructure as evidence that the user-facing
swarm objective was nearly complete. Work shifted toward cloud startup, PX4
integration, NVIDIA city assets, camera controls, video encoding and access
codes. These solved real problems, but the main demonstration remained unfinished.

The camera consequently presents a building and fire while aircraft activity is
mostly represented by sidebar text. Saying “three aircraft are Offboard” proves
a flight-controller state; it does not show coordinated firefighting. A higher
frame rate makes that view smoother without supplying the missing mission loop.

Our acceptance checks reinforced this drift: they verified transport and control
integration rather than the complete task the user wanted to observe. I should
have kept those results explicitly separate from swarm-demo acceptance.

## What exists, and what is missing

| Area | Evidence in the current project | Gap relative to the objective |
| --- | --- | --- |
| Flight | Three PX4 SITL instances drive PhysX through measured HIL sensors and motor outputs. | The observer still cannot clearly follow each aircraft doing useful work. Close-up mesh visibility remains unverified. |
| Mission logic | Local ledgers, mesh messages, bids, awards, acknowledgements, deferral and a trained mission actor exist. | Their complete causal sequence has not been demonstrated visibly in the Isaac scene. |
| Discovery | The city starts with an injected incident and accepts operator fire/person reports. | Camera observations are not the source of autonomous incident discovery in this demo. |
| Perception | A separate real-data detector/review path exists. | It is not connected to the city mission loop. Its smoke results do not establish calibrated fire severity or survivor detection. |
| Navigation | Measured positions feed the mission bridge and PX4 receives targets. | Initial climb and high-rise standoff targets are prescribed. General obstacle-aware city routing is not established. |
| Work at incidents | Drones can receive response/verification tasks and approach an incident. | The city lacks a closed simulated suppression/resource/evidence loop that visibly changes the fire and proves completion. |
| Observation | Native video, cameras, telemetry and a mesh sidebar work. | Default views do not reliably make the aircraft, their routes and their contributions legible. |
| Verification | Cloud tests pass flight, report injection, mesh isolation/reconnection, pause/resume and camera checks. | They do not require discovery, successful task execution, safe diversion, remembered-incident revisit or mission completion. |

The earlier 23.95 fps / 578 ms camera-state acknowledgement results are valid
integration measurements. They are **not acceptance of the autonomous swarm demo**.

## Concrete code gaps

- `embernet/isaac/city_live.py` creates the initial incident directly in E01's
  ledger. Subsequent reports also enter through operator commands. There is no
  camera-to-`PhysicsMission.observe()` discovery loop in this runner.
- The same runner overrides targets with an initial climb and
  `highrise_approach()`. It looks up high-rise incidents through E01's ledger.
  Execution should instead use each aircraft's own received incident version;
  an adapter must not provide location updates another drone has not received.
- `embernet/isaac/bridge.py` deliberately forces `release=False`. Keep physical
  release disabled. Add a **separate virtual work/effect interface** for simulated
  suppression, resource consumption and completion evidence; enabling a physical
  payload command is not the solution.
- `CityFire.update()` animates effects and uses incident clearance for visibility.
  That is not a fire-state model responding to verified work. Manual “Mark
  resolved” is an operator action, not proof of autonomous suppression.
- `tools/check_cloud_demo.py` asserts transport/control milestones. Its passing
  result does not require a swarm mission to finish.

These findings explain the disconnect. The exact reason aircraft meshes are
hard to see still needs diagnosis; do not assert a Fabric, viewport, scale or
transform bug without testing it.

## Recovery order

1. **Make actual aircraft visible first.** In the existing Isaac scene, verify
   each mesh follows its measured PhysX pose during takeoff and transit. Inspect
   scale, visibility, camera framing and render-transform synchronization. Use
   readable E01/E02/E03 labels and selection highlights anchored to measured poses.
   Labels must supplement visible aircraft. Do not animate a replacement flight
   path or teleport physics bodies to make a convincing video.
2. **Build one complete mission with a deterministic baseline.** Reuse the current
   environment rather than rebuilding scenery. Connect observation → local
   incident → delivered report → acknowledged assignment → navigation → virtual
   work → updated evidence → completion. Prove this before more policy training.
3. **Separate world truth from drone knowledge.** Scenario controls create fires
   and survivor evidence in the world. Aircraft acquire observations through a
   sensor adapter, subject to visibility, range and time. Initially, an explicitly
   labeled simulated sensor can establish the loop. It must not be presented as
   neural perception. Connect and evaluate the pinned RGB model afterward.
4. **Connect virtual incident effects.** Only an eligible, safely positioned
   responder with a valid commitment can contribute simulated work. Decrement
   scenario resource units, update fire state, and require fresh evidence for
   clearance. Make the effect visible. Survivor response means verification and
   rescue escalation, not a claim that a person was physically rescued.
5. **Expose coordination where the action happens.** Default framing should show
   the responders and incident. Provide fleet overview and selected-drone follow,
   routes/targets, incident priority and committed capacity, and concise reasons
   for reassignment. Display only messages actually delivered; a lost link must
   change both knowledge and behavior. Keep full details available for inspection.
6. **Demonstrate the user's diversion/memory case.** Add the smaller incident
   during transit, show the release request and acknowledgement or refusal, then
   show either a safe diversion or a deferred record with a scheduled revisit.
   Reconnect a partitioned drone and show reconciliation without refreshing old
   evidence merely because it arrived late.
7. **Evaluate learning against that same mission.** Run the rule-based baseline
   and learned actor on identical seeds and failures. Measure mission outcomes,
   safety, response time and resource use. More training is useful only after the
   visible execution loop and evaluation contract are sound.

Preserve independent safety, commitment/version checks, source timestamps,
existing checkpoints and failure logs. Validate approach routes against collision
geometry. The current coordinate clamps are not a complete obstacle planner.

## The demo we should be able to record

One repeatable scenario should show this sequence without manual task assignment:

1. Launch a visible fleet and begin search.
2. A drone observes a large fire; other drones learn about it through the mesh.
3. The team allocates acknowledged capacity and travels along visible safe routes.
4. A drone discovers a smaller fire while travelling; negotiation determines
   diversion or deferral while preserving the original response.
5. Possible survivor evidence causes visible reprioritization and verification.
6. A link fails; the affected drone uses its own retained knowledge and the team
   avoids assuming fresh unreachable capacity.
7. Drones perform virtual work, resources change, and fire state responds.
8. After reconnection, deferred work is revisited and completion is supported by
   fresh observations. A synchronized replay explains every significant decision.

The operator may introduce scenario events and faults. The operator should not
have to assign every response or manually declare the mission successful.

## What counts as done

- Actual aircraft and their movement are visible in the recorded simulation.
- Drones discover incidents through the declared sensor path; no hidden global
  incident feed supplies actor knowledge.
- Assignments and resource commitments agree with the messages and local ledgers.
- Safe diversion and deferral/revisit both succeed in reproducible cases.
- A partition affects information and coordination, then reconciles correctly.
- Simulated work changes resources and incident state; autonomous completion is
  distinguished from manual clearance.
- Video and telemetry share timestamps, incident IDs and decision events so an
  observer can connect each visible action to its cause.
- Automated mission assertions **and** an inspected recording pass. Flight status,
  labels, streaming FPS and camera acknowledgements alone cannot pass this gate.

Until those conditions are met, describe the current deliverable as an
**Isaac/PX4 integration and streaming foundation with partial mission integration**.
The autonomous swarm demonstration is unfinished. The next work should close this
gap before additional scenery, GPU upgrades or dashboard polish.

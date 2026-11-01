# Status — 2026-11-01

Click-to-place city fire: **Add fire** toolbar interaction hardened and deployed;
matching simulator image and a 600-second voucher prepared without starting a GPU.
148 full-suite tests, UI event-handler checks, Ruff and JS parsing pass. Browser
offline control inspected; live GPU fire-placement acceptance remains unverified.
See [CLICK_TO_FIRE.md](CLICK_TO_FIRE.md) for behavior, evidence and picking limits.

**Overall swarm-demo acceptance: NOT MET.** The user cannot see coordinated
mission execution. Read SWARM_OBJECTIVE_RECOVERY.md before further work.
The passing checks below concern integration; they do not establish autonomous
discovery, visible task execution, suppression or complete swarm missions.


Read [ARCHITECTURAL_RUN.md](ARCHITECTURAL_RUN.md) and CURRENT_HANDOFF.md first.
The NVIDIA Tower/City world passed full functional testing on RTX PRO 6000:
live-10e509a5b313, 64.132 sim seconds, three PX4-controlled aircraft, reports,
mesh faults, pause/resume and camera input. NVENC video averaged 23.95 received
fps; camera-state ACK improved to 578 ms. Browser mouse orbit is verified.
Native recordings, physics/telemetry and flight ULGs are downloaded. GPU stopped
after testing. Source checks: 62 tests passed, relevant Ruff and JS parsing pass.
Visual acceptance remains partial: stylized effects, occasional stalls, and
close-up aircraft visibility need work. No locked 30/60 FPS or zero-lag claim.

## Implemented

Live Three.js forest/swarm scene plus native Rerun telemetry, sharing authored
GLBs for forest/field station, physical quadrotors and people. Fire/smoke and
executed suppression effects replace point blobs. Orbit/follow/Scene POV, focus
view, settings, incident placement and mesh faults operate on the existing simulator.
Scene POV is distinct from prototype model inputs.

Real-perception path: pinned fire/smoke YOLOv8n plus completed four-epoch
real-image fine-tune `real-perception-v1-20261101-e1` on 900/260 annotated
train/validation images. Checkpoints, ONNX export, dataset/output manifests,
Modal logs and held-out reports are downloaded. /perception serves the candidate
review while retaining the original baseline report. FLAME 3 was excluded from
training, checkpoint selection and threshold tuning. See REAL_PERCEPTION.md for
scope, failed attempts and measured limitations.

Separate verified Isaac path: earlier NVIDIA forest/props evidence plus current
Metro 30 live city (`live-9980e01a1da0`). The city has 240 m PBR surfaces, 30-floor
high-rise fire, Iris shells, bird/onboard/fire cameras, RGB + synthetic IR, mesh
topology and 10 Hz latest-only streaming. 299 dual-sensor frames and three armed
Offboard aircraft were verified at startup. Smoke transparency remains broken;
no final visual or automated acceptance. Fire remains a scenario effect and IR is
not radiometric. PX4 SITL drives measured PhysX flight; fire physics is unimplemented.

Core retained: per-drone memory, unreliable bounded-hop mesh, bids/awards/ACKs,
versioned safe release, deferred reviews, stale-owner takeover, independent safety,
kinematic flight, replenishment, recurrent mission actor, procedural RGB/IR CNN,
validated loopback/CLI control, RRD and JSONL replay. Modal training/V2 refinement
completed earlier; all available experiment logs/checkpoints are downloaded.
The perception and city live jobs used bounded Modal runs.

## Evidence and boundaries

Source FLAME 3 v1 has 622 fire and 116 no-fire pairs from one prescribed burn.
Sample: 24 of each. Fine-tuned RGB fire-or-smoke warning: 24/24 fire samples,
0/24 no-fire; original baseline had 3/24 false warnings. Flame-only recall remains
0/24 and all positive warnings came from smoke. Thermal agreement may share the
source-label heuristic. No independent localization labels, verified sequence, or
cross-burn validation. Current interactive sensors remain the synthetic V2 prototype.

Actors receive only own observations and delivered messages. No uncalibrated
pixel-to-world mapping or recorded-image actuation. Isaac 6.2 cloud physics trials now pass
(see ISAAC_SIM.md): rotor-driven flight, real rendered RGB/depth, trained-policy
three-aircraft navigation and packet isolation/recovery. The browser is still kinematic.
ROS/ns-3, physical
sensors/radios/flight/suppression are future. Existing four-mode/four-seed fault
suite and failed experiments remain preserved.

## Release checks

56 pytest tests pass on current source, adding city/fire/IR, frame-prefix, camera,
mesh-partition, ceiling and Iris geometry coverage. Ruff and cloud/perception
JavaScript parser checks pass. The latest city run completed startup and dual-frame
streaming, but automated interaction acceptance and final smoke/visual review are
pending. Current full scene/camera RRD passes the Rerun CLI verifier.
Browser checks: sample navigation/empty state, orbit/follow/Scene POV, focus,
reported estimates, speed reflection and narrow fit (375px content/viewport).
Main scene captured with physical drone, forest and executed discharge.
Native GLB import stalled here; shared arrays now use Mesh3D. Native final visual
acceptance remains unverified; browser is primary and native viewing is opt-in.
Source/models/data/logs are packaged with per-file hashes and ZIP validation.

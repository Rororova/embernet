# PX4 and the shared cloud room

Current result: read [ARCHITECTURAL_RUN.md](ARCHITECTURAL_RUN.md). NVIDIA Tower/City
assets and NVENC H.264 are deployed and full-world tested. Latest run passed
functional checks, averaged 23.95 received fps and acknowledged camera state in
578 ms. Some older notes below describe superseded source-only/JPEG checkpoints.


## Boundaries

`cloud_px4.py` builds PX4 v1.14.3, commit
`1dacb4cdef2d7145754fc788fa8dc482eed74b40`. `px4_bridge.py` starts
loopback-only SITL instances: simulator TCP 4560+i, Offboard UDP 14540+i.
PhysX measured pose/velocity generate HIL IMU, magnetometer, barometer and GPS.
PX4 estimates state and returns HIL_ACTUATOR_CONTROLS. Rotor speed/thrust and
reaction torque act on the actual PhysX rigid body. No controller fallback or
pose teleportation. No hardware connection or physical payload release.

ENU/FLU → NED/FRD conversion includes the rotor reaction-torque sign. PX4 uses
`moment = ct*(position cross axis - km*axis)` with upward axis -Z in FRD.
The first Isaac run exposed a reversed yaw sign; preserved as px4-isaac-v1.
The correction has a frame/allocation regression test. v2 passed 60.008 s at
250 Hz: mean hover error 0.0209 m, final waypoint error 0.0107 m, 14,969
actuator packets. Those are errors in this simulation, not real aircraft accuracy.

Modal gVisor lacks SCHED_FIFO priorities. `patch_px4_sitl_scheduler.py` adds an
opt-in `EMBERNET_SITL_NON_RT` branch using SCHED_OTHER in POSIX tasks/workqueues.
This changes scheduling only; it does not disable arming checks or failsafes.
No realtime timing guarantee. Startup may report stale internal simulated
sensor instances and unavailable /proc/meminfo load monitoring; inspect ULogs.

## Shared session

`cloud_live.py` deploys a small CPU ASGI gateway. It serves the existing visual
language and a public watch page. One control code authorizes session start and
bounded commands. The private invite lives in
`artifacts/embernet/cloud/control-invite.private.json`; never package it.
The URL fragment is removed from the address bar and the code is held only in
sessionStorage. Requests use a Bearer header; registries and GPU environment
contain only its SHA-256 hash. No Modal credentials are exposed to visitors.

One atomic Modal Dict voucher pop precedes allocation; a named GPU Sandbox
also prevents duplicate worlds. Failure consumes the voucher. Local host renewal
checks the selected account's current billing summary before issuing another.
Default 600 s, maximum 600 s, hard Sandbox timeout duration+60 s. Credit headroom
must exceed $1.50 with zero billed cost. No automatic GPU renewal or paid fallback.
One shared world, up to eight WebSocket spectators; no per-visitor GPU.

The current world is `isaac/city_live.py`: a 240 m Metro 30 city with a fire on
the 30th floor (`150, 134, 104.4` m), three measured PhysX aircraft, a detailed
Iris shell, PBR city surfaces, animated fire/smoke and a default high-rise camera.
Kit stays on the main thread; FastAPI and JPEG fan-out run in a spawned process.
RGB and synthetic thermal-style IR frames use binary prefixes 0/1 over the
encrypted Sandbox tunnel. Target is 10 fps with latest-only delivery; this was
verified for 299 RGB + 299 IR frames at readiness, not as a latency guarantee.
The learned V2 mission actor chooses incidents; independent approach/geofence
bounds hold the high-rise stand-off. Radio isolation updates `Mesh.isolated`, and
the UI receives active links, queued packets and recent traffic for its topology.

The earlier forest world `isaac/live.py` remains at 5/9/13 m lanes for historical
evidence. The city run still has a visual failure: smoke cards appear as opaque
dark slabs. Do not claim final visual or automated acceptance. See
`CURRENT_HANDOFF.md` and `artifacts/embernet/cloud/live-9980e01a1da0/`.

Reports enter E01's local ledger with source `operator`, preserving observation
time. They propagate normally; stale reports expire from decision eligibility.
Severity is operator supplied. A possible survivor raises the existing incident's
vulnerability priority. Six capacity units per aircraft are scenario resources,
not kilograms/litres carried by the unloaded 1.5 kg rigid-body model. Fire geometry
is a scenario effect; there is no combustion model or neural severity claim.
Resolve is an operator report, not measured suppression. The real-data detector
review remains separately available in the local /perception route.

## Operation and evidence

Deploy: `.venv-embernet/Scripts/python.exe -m modal deploy cloud_live.py`.
Prepare/renew: `modal run cloud_live.py --duration 600` (set MODAL_PROFILE first).
Use the private invite to start; send others the public watch URL. To rotate the
code, add `--rotate`. Another Modal account requires its own deployment/volume.

`tools/check_cloud_demo.py` understands prefixed RGB/IR frames and exercises
spectator denial, live frames, three armed Offboard aircraft, fire/survivor
reports, isolation/reconnect, paused clock and shutdown. The latest city build has
**not passed this automated test**, and the slow-HTTP/WebSocket draining issue is
still open. Current source has 56 passing tests, Ruff and JS parser checks; these
do not replace native/browser acceptance.

Native logs persist in Modal Volume embernet-live-logs under unique live-* run IDs.
The verified city session is `live-9980e01a1da0`; failed `live-30d1525d6bd6` and
`live-64d8cb49002e` preserve USD API and prim-name failures. PX4 logs include .ulg,
parameters and console; physics/mission telemetry, commands, video and Kit logs
are saved alongside. No GPU is running at handoff. The public gateway being
deployed is not proof of a passed interaction test.

The old failed build app ap-5nsJ9yAIDnQdEEeremsNsy was stopped after its missing
cloud_isaac_runtime import repeatedly triggered alerts. The fix serializes the
remote entry functions. `px4/failed-startup-app.log` preserves the actual error.

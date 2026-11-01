# EMBERNET — current handoff (2026-11-01)

## Click-to-place city fires

See [CLICK_TO_FIRE.md](CLICK_TO_FIRE.md). The toolbar now exposes **Add fire**:
select it, then click/tap the live RGB city surface. Placement waits for a matching
native application result, shows a marker, and handles rejection/disconnect/stale
frames and accidental drags. Existing native picker/ignite path retained; it uses
the latest camera and conservative boxes, not exact frame/triangle picking.
148 full-suite tests, fire UI handler checks, Ruff and JS parsing pass. Gateway and
matching simulator image deployed/prepared with one 600-second city voucher;
no GPU started for this change. Live GPU placement/visual acceptance not rerun.
Final read-only check found `live-80c4b90bcaa9` active with the new result field;
left it running and did not inject a fire or allocate another GPU.
Older mission-status sections below are historical; current source also contains
`swarm_mission.py` and simulated range/line-of-sight sensing. This change does not
establish new end-to-end autonomous mission acceptance.

## Swarm mission recovered: read SWARM_MISSION.md first

The recovery below is implemented. Six-drone autonomous missions passed automated gates and
inspected recordings on real PX4/PhysX: city `live-a0ed6a9a7848` and wildland
`live-80c4b90bcaa9`. Limits are in [SWARM_MISSION.md](SWARM_MISSION.md). Latest user requests
done: more drones, 3x visual shells, fewer distant buildings, launch-time world switch,
click-to-ignite, full-screen UI with floating controls. Billed $0. A second session edits this
checkout (wildland): reapply against current files; never run tests during an image build.
148 tests pass. The user's "add more" message was cut off.

## Earlier correction: the swarm objective was not met

Read [SWARM_OBJECTIVE_RECOVERY.md](SWARM_OBJECTIVE_RECOVERY.md) first. The user
cannot see the swarm doing its job. Cloud flight/streaming checks passed, but
they do not prove a completed autonomous mission. Current city discovery is
operator/injected, suppression/resource effects are not closed-loop, and aircraft
visibility remains unresolved. The recovery document explains the drift, concrete
code gaps, execution order and mission-level acceptance gates. This turn is a
documentation handoff; it does not authorize claiming those gaps were fixed.


## Latest user screenshot follow-up

User opened a fresh spectator tab (1841361971). Unlocked it with the existing
private invite; the shared run live-b782257b92b9 was started and browser-verified
live with Controller access, all three PX4 vehicles Offboard, and ~28 fps.
Do not start a second GPU. The current run retains its original 600-second cap.
A hidden bounded log-download helper (PID recorded in that run's log-watch.json)
will download native logs after the session ends. Its output is at
artifacts/embernet/live-b782257b92b9-log-watch.log.

Fixed the misleading offline state: replaced the old forest placeholder with a
recorded NVIDIA city overview, explicitly labeled it as recorded/offline, hid
IR until an actual IR frame arrives, and clarified spectator/controller launch
instructions. Deployed to the CPU gateway; no GPU image rebuild was needed.
cloud.js parser check passed. Proof: run folder/browser-controller-live.png.
The previous ZIP archives precede these small UI-state fixes; workspace/cloud
are current. Native user-session logs are downloaded asynchronously on exit.

## Wildland landscape

NVIDIA forest world selected with `--world wildland`; a 6-PX4 mission passed all 20
checks there. The city stays the default: read [WILDLAND.md](WILDLAND.md).

## Architectural build and run completed

Read [ARCHITECTURAL_RUN.md](ARCHITECTURAL_RUN.md) for current evidence.
NVIDIA Tower/City assets are built, deployed and GPU-rendered on RTX PRO 6000.
Full-world hardware-video run live-10e509a5b313 passed functional acceptance:
three actual PX4 aircraft, fire/survivor reports, radio isolation/reconnect,
pause/resume and camera input. Native run completed 64.132 simulated seconds.
Video averaged 23.95 received fps; camera-state ACK was 578 ms, improved from
5.99 fps / 26.7 seconds. Browser mouse orbit is verified. Full native logs,
MP4s and PX4 ULGs are downloaded. GPU stopped after testing. A fresh 600-second RTX PRO 6000 voucher was
prepared afterward (h264-ready-console.log); Start shared swarm launches it. Free-credit guards remain in force.

Source checks: 62 tests passed; relevant Ruff and JS parser checks passed.
The remaining visual limit is significant: sprite fire/smoke are stylized, some
materials warn, close-up drone visibility needs inspection, and view changes
can still stall. Do not claim locked 30/60 FPS, zero lag or full photoreal acceptance.
Hardware H.264/WSS is implemented; public WebRTC/UDP is not.

The old city run below is historical evidence, not the current scene.

## Historical procedural city run

`live-9980e01a1da0` (sandbox stopped after verification):

- Actual Isaac 6.2 render at 960x540 from a Modal L40S; PX4/PhysX still drives all
  three aircraft. All three reached armed Offboard and climbed toward the high-rise.
- 299 RGB and 299 IR frames were received at readiness (~26 simulated seconds);
  client-reported stream was about 10 fps. This is not a latency guarantee.
- Scenario: 240 m procedural PBR city, 13 buildings, 30-floor high-rise, fire
  reported at `(150, 134, 104.4)` m. Default camera is the 30th-floor fire.
- Evidence: `artifacts/embernet/cloud/live-9980e01a1da0/` (`live-frame.jpg`,
  `live-ir.jpg`, `latest-state.json`, `live-verified.json`). The native volume also
  holds `session.mp4`, PX4 logs, telemetry, physics JSONL and Kit logs.
- Public gateway: https://nikhilthakuraan--embernet-live-gateway.us-east.modal.run
- No voucher is ready. The latest private invite is
  `artifacts/embernet/cloud/control-invite.private.json`; never print or package it.
- Latest billing: **$21.22 free credits applied, $0 billed**. Check again before
  another GPU allocation. Gateway deployment is not a GPU allocation.

Earlier failed city starts are preserved in Modal Volume `embernet-live-logs`:
`live-30d1525d6bd6` hit USD `CreateInput` misuse; `live-64d8cb49002e` hit invalid
hyphenated prim paths. Both were fixed before the verified run. Do not delete them.

## User intent and latest corrections

Build decentralized wildfire/survivor response with local evidence, mesh sharing,
commitments, trained V2 autonomy and independent safety. Keep physical actuation
disabled. The user authorized Modal only within verified free quota and accepted
NVIDIA terms; do not ask again merely because the session changed.

Latest user feedback: the Isaac demo must visibly show mesh reaction, a bird's-eye
view, much larger map, realistic surfaces/drone models/fire, dual cameras and lower
latency, using a city with a fire on the **30th floor**. “RDR/IDR” was not clarified;
the implementation uses **RGB + synthetic thermal IR**, not radar.

## What changed in this city milestone

- `isaac/city_scene.py`: 240x240 m city, roads/lane paint, 13 buildings, vehicles,
  streetlights, rooftop equipment, 30-floor high-rise, CC0 PBR asphalt/concrete/brick
  textures, procedural lit-window facades. High-rise approach holds are independent
  of the learned actor's incident choice.
- `isaac/native_airframe.py`: detailed PX4/3DR Iris STL shell, motors, translucent
  rotor discs, top accent and camera gimbal, still one 1.5 kg rigid body. The mesh
  source is attributed in `artifacts/embernet/isaac/assets/px4-iris/`; upstream
  standalone license was not found, so review before redistribution.
- `isaac/effects.py`: animated 30th-floor fire and smoke-sprite geometry. Fire is
  visible. **Smoke cards render as opaque dark slabs in the final frame**—a known
  visual defect that must be fixed.
- `isaac/cameras.py`: uncalibrated thermal-style IR conversion from the live RGB
  frame. The current IR is visibly city/fire, but it is not radiometric.
- `isaac/city_live.py`: city live world, initial 30th-floor report, high-rise
  approach bounds, dual JPEG stream, 10 Hz target, bird/onboard/follow/overview/fire
  cameras and mesh topology state.
- `live_api.py`: binary sensor frames are prefixed RGB=0, IR=1; bounded camera
  modes; city coordinates/altitude; transport stays in a spawned process.
- `ui/cloud.html/css/js` v3: RGB main feed, IR inset, bird/onboard/fire controls,
  live mesh graph with link/queue/packet status and persistent incident rows.
- `cloud_live.py` now launches `embernet.isaac.city_live`.
- `tools/prepare_city_assets.py` downloads and verifies the small visual assets.
- `tools/check_cloud_demo.py` understands prefixed RGB/IR frames but its automated
  acceptance has **not been rerun** and its slow-HTTP keepalive design still needs
  hardening.

## Verification and limitations

Current source: **56 tests pass**, Ruff passes, cloud/perception JavaScript parser
checks pass. New tests cover city/fire constants, thermal output, frame prefixes,
camera/altitude bounds, mesh partition state, independent ceiling, Iris STL and the
real-perception integration. Focused tests do not substitute for browser or native
acceptance.

Still open:

1. Smoke transparency/readability is broken (opaque dark cards over the fire).
2. The fire sprite is stylized; surfaces and buildings are substantially improved
   but not photoreal city assets. No final user visual verdict.
3. Mesh graph reaction, bird's-eye, onboard camera, IR quality and real perceived
   latency need one manual browser pass with an actual live session.
4. The automated `tools/check_cloud_demo.py` run (reports, mesh isolation/reconnect,
   pause, reconnect, graceful stop) is not passed. Fix continuous WebSocket draining
   before using it; do not hide keepalive failures.
5. Previous cloud acceptance remains unpassed. The gateway is deployed, not proof of
   a passed interaction test.
6. If the user meant radar by “RDR,” add a separate radar view; do not relabel the
   synthetic IR as radar.
7. Project/log ZIPs are stale; do not present them as containing this city build.

## Preserved earlier evidence

- Real perception e1: 24/24 held-out fire and 0/24 no-fire warnings, baseline three
  false warnings, **flame-only recall still 0/24**. See REAL_PERCEPTION.md.
- PX4 v2: 60.008 s, mean hover error 0.0209 m, final waypoint 0.0107 m. See
  PX4_CLOUD.md and ISAAC_SIM.md.
- Previous forest live `live-f2ab4945ccd8`: 76.64 s native completion, three
  armed/offboard aircraft, but automated WebSocket acceptance failed. Preserve.
- Local browser simulation remains kinematic on port 8780; it is separate from the
  Isaac city and the real-image `/perception` review.

## Main files

- Root: `cloud_live.py` (gateway/voucher/image/Sandbox), `cloud_px4.py` (PX4 image),
  `cloud_gateway.py` (auth/session).
- `embernet/live_api.py` (transport, auth, dual-frame protocol, command bounds).
- `embernet/isaac/city_live.py` (current world); `city_scene.py`, `effects.py`,
  `cameras.py`, `native_airframe.py`, `px4_bridge.py`, `bridge.py`.
- `embernet/isaac/live.py` remains the earlier forest world for historical evidence.
- `embernet/ui/cloud.*` (current live UI), `tools/check_cloud_demo.py`.
- Assets: `artifacts/embernet/isaac/assets/`; evidence:
  `artifacts/embernet/cloud/live-9980e01a1da0/`.

## Resume sequence

1. Fix smoke material transparency and re-check the fire presentation from the
   default fire camera, bird's-eye and onboard views.
2. Open the live UI and manually exercise E02 isolate → link/node change → reconnect,
   report/survivor, pause/resume and all camera modes. Record actual frame cadence
   and browser responsiveness; do not claim “no lag.”
3. Harden the acceptance harness with continuous WebSocket draining, then run it
   against a fresh city session. Preserve any failure and its logs.
4. Run full pytest/Ruff/JS checks; update STATUS, PX4_CLOUD and verification notes.
5. Check billing/app state, issue exactly one fresh bounded voucher, and leave either
   a verified live session or no GPU running. Never package the private invite.

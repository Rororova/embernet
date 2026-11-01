# NVIDIA architectural run — 2026-11-01

Latest request: build and actually run the photoreal scene on a larger GPU.
This supersedes the older source-only notes in VISUAL_REBUILD.md.

## Scene and reproduction

The image now contains NVIDIA City Tower Demo Pack NVD@10011. Download:
https://d4i3qtqj3r0z5.cloudfront.net/AECO_CityTowerDemoPack_NVD%4010011.zip
Size 2,797,027,818 bytes; SHA256
`03cfb5c643934b26b6876c36112036cd3584c09c3736ef7c237508ef242cf35f`.
tools/fetch_nvidia_tower.py pins the archive, supports resume, validates extraction
paths, and checks the existing accepted NVIDIA license record. Raw vendor packs
stay outside the project ZIP; source metadata and fetcher reproduce them.

embernet/isaac/authored_city.py composes BaseBuilding, Facade02A, City and Site
assemblies. Whole World is deliberately avoided because its Boardwalk reference
contains a missing filename. Centimetres become ENU metres; the tower is scaled
to 108 m. The incident at (150,134,104.4) is scenario-designated floor 30, not an
independently verified floor count in the vendor architecture. Conservative
44×40×108 m tower collision and flat ground remain. Architectural geometry and
textures now render; older USD crate and some ScarletOak MDL warnings remain.
Fire/smoke remain animated sprites, not physically simulated combustion.

Run-EMBERNET-Cloud.ps1 fetches assets, deploys and prepares a bounded session.
Default RTX-PRO-6000 uses 12 CPU/64 GiB RAM. The free-credit guard still applies.
No paid-overage authorization was inferred. Public watch gateway:
https://nikhilthakuraan--embernet-live-gateway.us-east.modal.run
Controller invite stays in artifacts/embernet/cloud/control-invite.private.json;
never publish it or include it in archives. Start vouchers are single-use.

## Actual runs and unresolved acceptance

All evidence is under artifacts/embernet/cloud/<run-id>/.

| Run | Native result | Acceptance result |
| --- | --- | --- |
| live-d4a5be51224e | 40.024 sim s, 3 PX4 armed/Offboard, actual authored frames | RFC websocket heartbeat failed; not accepted |
| live-43173e96538f | 35.144 sim s, 3 armed/Offboard, operator fire and survivor received | HTTP RemoteProtocolError at mesh request; not accepted |
| live-67768dce13b8 | 11.404 sim s, all armed/Offboard seen; clean stop | Application heartbeat expired during takeoff; not accepted |
| live-8d2660e0f6de | 112.012 sim s, three PX4 aircraft flown; full native logs downloaded | Functional checks passed; 5.99 received RGB fps and 26.672 s camera ack fail the performance goal |

All three native runs completed without a native exception. Complete native
files, MP4s and PX4 ULGs were downloaded with SHA256 manifests: approximately
69.2 MB, 69.1 MB and 39.0 MB respectively. A completed native report does not
mean end-to-end or visual acceptance passed.

Full-world H.264 run **live-10e509a5b313 passed functional acceptance**.
Actual result: 64.132 simulated seconds, all three PX4 aircraft armed/Offboard,
16,033 HIL sensor and 16,020 actuator packets per vehicle, minimum separation
9.965 m, 20 applied commands, clean native completion. The test verified operator
fire/survivor reports, mesh isolation/reconnect, pause/resume, spectator denial
and persistent camera input. Complete native logs/MP4/ULGs were downloaded
(33 native files, 99,255,070 bytes), plus local transport/client evidence.

Received video averaged **23.952 fps** before manual review; camera-state ACK
was **578 ms**, compared with 26,672 ms in v4. Full-run heartbeat median was
328 ms; worst was 9,375 ms (cold-start/stall evidence remains). Maximum measured
frame gap was 1.485 s. Browser snapshots showed 25–29 fps in ordinary views,
with transient drops during view changes. Do not call this locked 30/60 FPS or
zero lag. Native rendering/physics is now the main steady-rate limit.

Browser verification captured overview, actual mouse orbit (-45 to -70 degrees),
follow and onboard selection. browser-before-orbit.png / browser-after-orbit.png
show the changed 3D perspective. Follow capture does not establish close-up
visibility of the aircraft mesh; inspect that separately before claiming it.
Bird/mobile hardware-video capture was not completed within the review window.
Architecture renders; fire/smoke still show stylized sprites and require further
visual work. The GPU stopped after the test to conserve credits. A fresh bounded
voucher can be prepared without starting a GPU. Native v4 rendered 7,420 frames at 25.06 fps overall while
the JPEG client received 5.99 fps. Its late render median was 12.2 ms and capture
median 23.1 ms. This isolates the major backlog to transport, not render time.

## Isolated transport fix

CPU-only encrypted-tunnel JPEG probe: 3.168 fps, while a separate persistent
control connection acknowledged commands in 234–266 ms. The v4 recorder's disk
writes had median 0 ms / max 16 ms; local writes did not explain its ~25-second
stream RTT. The earlier disk-blocking theory is not the established root cause.

Verified actual NVENC encoding: 120 synthetic 960×540 frames in 0.767 s using
Ubuntu FFmpeg and h264_nvenc on RTX PRO 6000. Imageio's bundled FFmpeg lacked
required NVENC options; that failed attempt is retained in the logs.

Verified full hardware-video tunnel using a static architectural frame:
30.858 fps received across 609 frames, steady heartbeat RTT ~282–312 ms, control
acknowledgements 313–547 ms. This is a transport test, not full Isaac scene FPS.
Evidence: h264-transport-probe.json, cpu-transport-probe.json, rtx-pro-preflight.json.
Both probes were bounded and terminated after testing.

embernet/video_stream.py runs FFmpeg NVENC at 960×540 / nominal 30 Hz / 1.2 Mbps,
no B frames, ultra-low-latency tune. AUD-delimited access units carry channel 2,
key-frame flag and an unsigned 64-bit presentation timestamp. A 60-packet ring
and key-frame recovery bound backlog. Browser WebCodecs decodes to a canvas;
mouse input still targets the underlying image hit area. The independent IR
JPEG preview is limited to 2 Hz. Unsupported browsers retain labeled JPEG preview.
Native recordings and raw physics/PX4 evidence remain independent of video encoding.

Authenticated /ws/control now handles acknowledged mission commands and camera
input; code authentication is explicitly acknowledged, with a 30-second initial
auth deadline and four control sockets maximum. Retries reuse request_id. A
separate control connection keeps input independent of media backpressure.
/ws/camera remains camera-only. Camera motion cannot actuate an aircraft.
The full-world test uses this persistent control channel and hardware video.

## Transport and performance changes

- Mouse orbit/pan/zoom sends bounded camera-only input over authenticated
  /ws/camera. Flight controls remain independent; presets are retained.
- API commands accept bounded request_id keys; repeated HTTP requests return
  the original queued sequence. A lock serializes deduplication and submission;
  the cache retains 256 requests. Browser and test retry with the same ID.
- Tests use fresh HTTP connections. Previously pooled connections failed after
  idle periods. No camera/mission command is silently duplicated on retries.
- RGB and IR channels are counted separately. Earlier combined FPS counters
  doubled the apparent RGB frame rate. Application ping/pong checks replace
  RFC ping for the custom transport; expiry still closes stalled connections.
- Thermal-style preview generation moved to the separate HTTP process/thread.
  It remains derived from RGB, uncalibrated, and not independent thermal truth.
- Three PX4 sensor/actuator exchanges overlap; forces and PhysX stay on the main
  thread and all exchanges join before physics advances. There is no fallback
  controller or pose teleport. Physics remains 250 Hz simulated time.
- Native render pacing targets 30 Hz with at least four physics steps between
  captures. Default viewport updates are disabled because capture uses its own
  Replicator render product. Main-loop rate-limit setting was already false in
  v3; do not attribute an improvement to disabling a limiter that was not on.
  Post-reset world-pacing.json records the final setting in subsequent images.
- v3 late-frame native render was ~13 ms, whole capture ~21 ms, but this is
  not received FPS or input latency. render-metrics.jsonl preserves timings.
- v4 test recorder writes latest JPEGs on a background thread every 0.5 s.
  Previously synchronous repeated writes inside the websocket reader could
  block heartbeat processing on the OneDrive workspace. This is a hypothesis
  being tested, not a confirmed server-root-cause claim. Compression is disabled
  for the Python JPEG receiver. transport-diagnostics.json records receive
  timestamps, heartbeat RTT and image-write durations even on failure.

Hardware H.264 streaming over HTTPS/WSS is now implemented and transport-tested.
Public WebRTC UDP/TURN traversal is not implemented.
Do not promise 30/60 FPS, zero lag or photoreal combustion without evidence.

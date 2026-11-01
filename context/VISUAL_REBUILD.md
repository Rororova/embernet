# Photoreal scene and responsive POV — user correction, 2026-11-01

Current result: read [ARCHITECTURAL_RUN.md](ARCHITECTURAL_RUN.md). NVIDIA Tower/City
assets and NVENC H.264 are deployed and full-world tested. Latest run passed
functional checks, averaged 23.95 received fps and acknowledged camera state in
578 ms. Some older notes below describe superseded source-only/JPEG checkpoints.


## Rendering GPU upgrade

User explicitly authorized a larger GPU. New preparation defaults to
RTX-PRO-6000, 12 CPU cores and 64 GiB RAM; `--gpu L40S` retains the earlier
profile. Run-EMBERNET-Cloud.ps1 exposes -Gpu. No automatic model fallback.
Current deployment/config is not silently changed; prepare again to select it.

cloud_render_probe.py completed on an actual NVIDIA RTX PRO 6000 Blackwell
Server Edition (97,887 MiB exposed VRAM, driver 610.57.04). Vulkan enumerated the
NVIDIA device and NVENC API capability query returned status 0. Evidence:
artifacts/embernet/cloud/rtx-pro-preflight.json and its console log. This proves
capability availability, not encoding throughput, scene FPS or input latency.
The probe exited; it does not leave an idle GPU allocated.

GPU and host-memory/cpu resource prices are recorded in cloud_resources.py
(Modal prices checked 2026-11-01). The free-credit guard reserves at least $1.50
for each bounded session, including the +60 s cleanup window, compute margin and
egress allowance. It rejects nonfinite billing evidence, prior billed cost or
insufficient free credits. No permission to incur paid overage was inferred.

Isaac's direct WebRTC media path requires a reachable UDP port as well as TCP
signaling. The existing HTTPS Sandbox tunnel is not that media path. Verify a
supported UDP/TURN route before representing WebRTC as implemented or working.

## Scene and camera work

User rejected the procedural Metro 30 appearance, awkward POV changes and lag.
Their reference is NVIDIA's downloadable OpenUSD content packs:
https://docs.omniverse.nvidia.com/usd/latest/usd_content_samples/downloadable_packs.html
This is a scene/interaction rebuild. Cosmetic dashboard changes do not satisfy it.

Implemented this turn, **source only, not deployed or visually accepted**:

- Direct left-drag orbit, right/shift-drag pan, wheel zoom on the RGB image.
  Pointer capture supports dragging beyond the image; preset cameras remain.
- Persistent authenticated /ws/camera input instead of one HTTPS request per
  mouse sample. Pending mouse samples are replaced, sent at most 20 Hz. Camera
  rate limiting is independent of mission commands. All poses remain bounded;
  camera controls never actuate an aircraft. Only control-code holders operate
  the shared camera. Existing spectator behavior is preserved.
- Native city camera accepts interactive orbit/pan for all presets. Onboard
  dragging switches to follow. This still relies on the existing JPEG stream;
  no FPS or latency improvement has been measured or claimed.
- NVIDIA City Demo pack downloaded (197,454,903 bytes) and extracted locally.
  SHA256 c7c6117973e776b903ea5128b37472e852d41e53767c928d587a70d9ef13da27.
  artifacts/embernet/isaac/nvidia-city/audit.json records composition results:
  0 unresolved composition errors, Z-up, 0.01 m/unit, 15 materials, 11 composed
  meshes and 15,226 Xforms. USD 0.7 crate deprecation warnings are present.
  Preserve attribution/license provenance. Raw vendor content is excluded from
  the project ZIP until the redistribution boundary has been reviewed.

The downloaded pack is city context; it is not proof of a photoreal close-up
30th-floor tower. Inspect the City Tower/Tower packs for facade detail and the
Particle/Extensions packs for fire/smoke. Explicitly normalize source units and
resolve texture/MDL dependencies. Do not place a centimetre-scale world directly
into a metre-scale PX4/PhysX mission or retain intersecting procedural buildings.

Streaming direction to investigate: NVIDIA's Isaac 6.2 WebRTC livestream path,
hardware video encoding, adaptive quality, and direct input. Verify public
UDP/TURN traversal with the selected cloud provider; an HTTPS Sandbox tunnel
alone is not proof that WebRTC media will connect.
https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/manual_livestream_clients.html
https://docs.omniverse.nvidia.com/ov/ovs/latest/low-latency-streaming.html

Acceptance must include native screenshots from fire/follow/onboard/bird views,
working mouse POV in the browser, and measured received FPS, frame gaps and
input-to-visible-response latency under motion. Aim for sustained 30 fps or
better as a first interactive target; 60 fps and a latency threshold must be
validated against actual hardware/network. Do not call an artificially
interpolated or duplicated frame stream smooth physics. Keep PX4, learned
autonomy, mesh and independent safety; render cadence should not alter sensors
or overwrite physics poses. No GPU was launched for this source-only change.

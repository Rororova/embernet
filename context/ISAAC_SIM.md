# Isaac Sim — implemented and verified

## Current result
Isaac Sim 6.2.0.0 runs on Modal L40S with actual PhysX integration, rotor-allocated
forces, RGB/depth rendering and measured telemetry. The existing browser mission
remains kinematic. These are separately repeatable cloud physics trials; there
is no continuous cloud streaming service or PX4 connection.

| Trial in artifacts/embernet/isaac/ | Result |
| --- | --- |
| isaac62-boot-v1 | Gravity/collision and RGB/depth pass; cube settled at 0.500 m. Its hard-coded engine label was stale: ENGINE-NOTE.md preserves the correction; Kit banner proves 6.2. |
| isaac62-flight-v3 | 250 Hz, 18.008 s measured time; hover at 3 m then 5 m waypoint. 450 telemetry rows, 187 video frames, real onboard RGB/depth and ONNX inference. |
| isaac62-flight-v4 | Same flight with 117 detailed NVIDIA oaks, close follow camera and world force [0.8,0.25,0] N during 8–12 s. Passed recovery/waypoint thresholds. Ground projection residual 0.006 m at the H pad. |
| isaac62-fleet-v2 | Three PhysX aircraft, existing V2 GRU mission actor, 36.008 s measured time. Final heights 4.999/8.999/12.999 m; minimum center separation 26.667 m. E02 isolated at 12–22 s: zero deliveries during isolation, 13 after reconnect. Total 84 delivered, 15 lost. |

Inspect report.json, runtime.json (runtime/model/source hashes), process.json,
telemetry.jsonl, MP4, RGB PNGs and full console/Kit logs in each run. radio-audit.json
records actual per-node deliveries. RGB/depth are rendered sensors; the existing
small pretrained fire/smoke ONNX model ran on an onboard frame and returned zero
candidates in the no-fire scene. No incident detections or fire decisions were
fabricated. The policy was trained earlier, not retrained in Isaac.

## Contracts and limits
- bridge.py reuses per-aircraft ledgers, mesh, policy and independent safety.
  Only measured telemetry changes poses; original observation identity/time is
  validated. set_connection() changes both status and actual Mesh isolation.
- controller.py / rotors.py compute bounded motor allocation and net rotor wrench.
  PhysX integrates forces/torques; body poses are never reset during flight.
  Rendering steps are separate from 250 Hz physics. Camera-follow transforms
  affect the camera only.
- native_airframe.py is an unloaded 1.5 kg research quad with estimated inertia
  and a body collision box. This is not a validated 18 L firefighting airframe.
  Tree trunks use collision proxies; foliage is visual. No obstacle-avoidance,
  fire/suppression physics, real rescue or calibrated thermal is validated here.
- PhysicsMission resources/incident demand remain scenario estimates. Physical
  discharge and all hardware connections remain disabled. PX4 SITL is not installed.
- The three-aircraft test covers navigation and actual mesh isolation/recovery,
  with zero incident observations. It does not validate learned fire prioritization
  in Isaac. Existing kinematic fire/memory regression results remain separate.

## Runtime decision and retained failures
Local host has Intel Arc and ~32 GB RAM, no NVIDIA RTX. L40S preflight proved Vulkan
1.4.341, driver 610.57.04 and ~48 GB VRAM; CUDA availability alone was insufficient.
Original compatible pair was Isaac 5.1 / Python 3.11 with Pegasus v5.1.0, commit
644da37e9d5268e5f9a34e78bdcfd57a8bab82b4. Installed missing libGLU, but corrected
5.1 still SIGSEGVs in RTX scene creation. NVIDIA reports the same class of newer-
driver incompatibility; Modal owns that host driver. 6.2's updated renderer works.
Pegasus compatibility with 6.x is not assumed. Its separate prepared 5.1 backend
remains in flight_trial.py / pegasus_backend.py; it has not flown.

First 6.2 flight failed on an unsupported ground-plane color argument. Kit's fast
shutdown masked the Python exception with exit 0. worker.py now saves exceptions
before cleanup; parent requires a completed report and no exception. Full failed
runs remain preserved. Fleet-v1 changed a connected flag without cutting packets;
RADIO-NOTE.md limits it to navigation/rendering evidence. Fleet-v2 corrected this
and a regression test checks queued-packet rejection plus reconnection.

## Assets and consent
User explicitly approved NVIDIA license acceptance on 2026-10-31 for EMBERNET R&D.
license-consent.json records that scope. 5.1 and 6.2 additional-license article
text is identical (June 9, 2025 terms), verified in license-version-check.json.
Other users must accept terms for themselves via the launcher flag.

Two NVIDIA SimReady props are CC-BY-4.0: barrier_wall_plastic_orange_a03 (46 files,
44,233,757 bytes), fireExtinguisher_abc_a03 (34 files, 13,184,561 bytes). Pinned HF
revision 653d91e182011f357cf1644013cc94ddf194d349; every non-thumbnail dependency
is size/SHA-256 checked against upstream BOM. Original files and attribution remain.
NVIDIA Black Oak plus five MDLs/nine textures total 35,081,285 bytes. These sample
assets and Isaac/Kit binaries are excluded from the project ZIP; the launcher
fetches audited content separately. config/isaac/vegetation.json preserves source
URLs/hashes. Source centimeters are converted once to meter physics. Authored
colors are converted from sRGB to linear; nested prop instancing is disabled in
scene composition to avoid Fabric missing-prototype errors. Final fleet console
has no Error/Traceback entries. Ground/station/pads are authored geometry.

## Repeat, spending and logs
```powershell
.\Run-EMBERNET-Isaac.ps1 -Mode flight -AcceptNvidiaEula
.\Run-EMBERNET-Isaac.ps1 -Mode fleet -AcceptNvidiaEula
```
Mode boot runs a smoke test. The default is 6.2.0.0/Python 3.12. The environment
EMBERNET_ISAAC_VERSION=5.1.0 selects the legacy image in direct Modal CLI runs.
The PowerShell launcher explicitly selects the verified 6.2 default.
Main Python remains isolated from NVIDIA's environment. Authorized Modal profiles:
nikhilthakuraan (used) and ieirodov14 (unused). Free-credit guard reads the selected
profile before each trial. One L40S container, 900 s function / 780 s child timeout,
no retries, 2 s scaledown. Last billing snapshot: $18.51 monthly credits used,
$0 billed; no GPU containers remain. Current probe/trial increment is about $0.89
of free credits from the initial $17.62 snapshot; billing can settle later.

All available app/image logs were downloaded with tools/archive_isaac_logs.py;
console/Kit output is also preserved per run. Cloud logs include the failed trials.
Run logs/calibration/reports are included in the refreshed log ZIP; videos/models,
source and CC-BY assets are in the project ZIP. No credentials are packaged.

Primary sources: https://github.com/isaac-sim/IsaacSim/issues/912
https://github.com/isaac-sim/IsaacSim/issues/677
https://modal.com/docs/guide/cuda
https://docs.isaacsim.omniverse.nvidia.com/6.2.0/installation/install_python.html
https://docs.omniverse.nvidia.com/composer/latest/prod_content/mount-content.html

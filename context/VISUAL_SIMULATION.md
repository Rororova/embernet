# Visual simulation

The user rejected point blobs as the final presentation and clarified that
Rerun should not be the sole visual experience. The target is the quality of
Rerun's own examples, with recognizable aircraft and an inspectable environment.

## Implementation

- `visual_assets.py` authors shared GLB triangle meshes for the forest/field
  station, suppression quadrotor and person. Assets use Z-up metres, vertex
  normals and linear glTF colors. Models include airframe arms, four motor/rotor
  sets, camera pod, suppressant tank, nozzle, landing gear and service pads.
- `ui/forest3d.js` renders those assets with local Three.js 0.186.1, physical
  lighting, shadows, haze, orbit/follow/POV cameras, fire/smoke and water effects.
- `telemetry_scene.py` uses the same GLBs in native Rerun through decoded Mesh3D arrays and adds dynamic
  aircraft transforms, flame meshes, smoke, subject labels and suppression.
- Actual `discharge` metadata is added to snapshots. Water effects require an
  executed simulated release; task intent alone does not trigger water.
- Main controls retain existing live state, placement, mesh faults, ledger,
  flight resources, model inputs and decision events. The settings drawer can
  be opened; Focus view gives the scene more space. Assets are served locally.
- Start-EMBERNET.cmd opens the visual simulation and saves Rerun recordings. -Rerun enables native viewing; -TelemetryOnly
  keeps the native telemetry path. Existing trained policy and simulator actions
  drive the views; rendering never dispatches aircraft commands autonomously.

## Perception boundary

The 3D scene is a presentation of the synthetic world. Its drone-camera POV is
distinct from the 64x64 procedural inputs currently consumed by the prototype
CNN. Model input thumbnails are labeled. Real-data FLAME 3 inspection now lives at /perception; see REAL_PERCEPTION.md. It
is separate from this interactive world and is not a verified video trajectory. See REAL_DATA_PERCEPTION_HANDOFF.md
before making perception claims or starting a new training experiment.

Geometry is authored for this project; vendored Three.js retains its MIT license.
No Poly Haven asset was incorporated: public metadata/download attempts did not
provide usable files. Terrain material detail remains procedural. Camera/rotor
animation and smoke are visual models, not calibrated sensor or flight physics.

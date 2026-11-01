# NVIDIA wildland scene — 2026-11-01

Forest landscape for the wildfire scenario, built separately from the city world.
The request was landscape only: no animals are included. No NVIDIA animal asset was
found in the prefixes searched, and the SimReady prop search timed out.

## Files

- `embernet/isaac/wildland_terrain.py`: deterministic terrain, ground masks and plant
  placement. No Kit or USD imports; `terrain_height(x, y)` is the shared height source.
- `embernet/isaac/wildland_scene.py`: `build_wildland(stage, asset_root, output)`.
  Authors terrain, a 10 m collision mesh, three PointInstancers, sun and HDR sky.
- `embernet/isaac/wildland_render.py`: fixed-view look-development render with timings.
- `cloud_wildland.py`: free-credit-guarded job. `pipeline` runs wholly on Modal, so a
  dropped local connection cannot strand it. Assets are fetched by Modal straight from
  NVIDIA into Volume `embernet-wildland-assets`; large local uploads failed repeatedly.
- `config/isaac/wildland.json`, `tools/fetch_nvidia_wildland.py`: 192 pinned files,
  884 MB. The two unresolved `OmniPBR.mdl` entries are built into Kit.

Run from the repo root (needs `MODAL_PROFILE`), with a new run ID each time:

```bash
.venv-embernet/Scripts/python.exe -m modal run --detach cloud_wildland.py --run-id wildland-look-v7
```

Collect the result with `modal volume get embernet-isaac <run-id>`. In Git Bash set
`MSYS_NO_PATHCONV=1` or `/` paths are rewritten.

## Current result

`wildland-look-v6` (`artifacts/embernet/isaac/wildland-look-v6/`, with `contact-sheet.jpg`):
successful RTX PRO 6000 render of 7 views. 83,863 trees, 25,891 understory plants and
rocks, 163,870 grass clumps; 1.2 km mission square inside 12.7 km of visual terrain.
Median 60 ms per frame at 1080p on an otherwise still scene; 11.4 GB VRAM; 83 s from
start to `world.reset()`. This is a fixed-camera render time, not streamed or live FPS.
Run total on this profile: $3.73 of free credits shown, $0 billed (other work included).

Acceptance is the reviewer's eye on stills only: no user verdict yet. Weakest areas are
bare orange duff on open slopes, pale rock patches on the far hills, smooth terrain
close to the camera and the absence of atmospheric haze. The `forest` view still has a
branch in the foreground. Do not call it photoreal without user acceptance.

## Lessons kept from failed runs

- `wildland-look-v2` segfaulted in RTX SceneDB: nested branch instancers multiplied
  into millions of instances (fir 549 and oak 3,735 per tree). `_flatten_plant` merges
  fir, pines, oak and barberry into one mesh per material. Colorado spruce stays
  nested (454 per tree; 15.6M triangles if flattened). Rhododendron was removed.
- Grass_Short assets are 14 cm lawn mats. Uniform scaling made 3.5 m floating discs,
  so they scale height only and tilt to the terrain normal.
- MDL `let` blocks cannot reassign variables; `fresnel_layer` takes a float `ior`.
- A detail value above 1 in `edge()` leaked unmasked layers across the whole ground.
- Modal rejects build steps after `add_local_*` without `copy=True`.
- Replicator's camera prim is the parent Xform; lens attributes are on its child Camera.
- The ground mask must be flipped: image rows run north to south, MDL v the opposite.
- Red cedar, cedar shrub and juniper rendered near-black (juniper foliage has no bound
  material in the source stage). All were replaced; juniper and cedar files remain in
  the manifest. The cedar cause was not established.

## Live mission

`--world wildland` selects this scene in `embernet/isaac/city_live.py`; the city stays
the default. The map shifts by `MISSION_ORIGIN` so the pad is the mission origin, and
PX4, mesh, safety and the 240 m mission box keep their coordinates. Relief inside the
box is compressed to +16 m so the 66 m lanes clear the canopy; outer hills stay tall.
The map is now 800 m with 2.8 km of visual terrain and 17.7k trees (see `wildland-look-v6`
for the larger earlier build). The city map is unchanged.
Incidents sit on the ground at the city mission's x/y, so `obstacles=()`.

- `wild-cae9de9fc57b` (15 Hz render, 480 s): did not finish, 74 sim seconds. Capture,
  overlay and encode cost 57 ms a frame and starved physics (0.18x real time).
- `wild-ee0ebcebab50` (5 Hz, 900 s): **all 20 mission checks passed**, complete at sim
  170 s, 6 PX4 aircraft, 0.45x real time, minimum separation 3.66 m. It predates the
  soft fire material.
- `wild-681ac17df0e4` (5 Hz, 900 s): final code. **All 21 checks passed**, complete at
  sim 170 s, 6 PX4 aircraft armed, 0.40x real time, 4.88 frames/s rendered, minimum
  separation 3.64 m. `session.mp4` is in `artifacts/embernet/cloud/wild-681ac17df0e4/`.

- `wild-9eb467ecbf70` (5 Hz, 900 s): current fast build on the 800 m map. **All 21
  checks passed**, complete at sim 132 s (was 170 s), 0.54x real time, minimum
  separation 6.8 m. PX4 limits and `Config.speed` are 80 m/s, but the measured peak was
  45.3 m/s (37 m/s typical) against 9.3 m/s before: a 240 m box has no room for the
  ~320 m run-up. Airframe drag is a simple linear term, so this is not a validated Iris
  flight envelope. After completion drones keep flying search patrols at speed.
  Later change: outer-belt trees now avoid the road past the map edge; not re-flown.

Live wildland therefore runs at 5 Hz. The gateway does this from the voucher world.
`cloud_wildland_live.py` runs one headless mission without touching the shared session.
Start a viewable session with `Run-EMBERNET-Cloud.ps1 -World wildland`; that replaces
the shared voucher's world, so coordinate with anyone using the city session.

Soft fire: `CityFire(soft=True)` uses MDL `cutout_opacity` with
`/rtx/raytracing/fractionalCutoutOpacity`. An `opacityThreshold` gave hard discs. The
city still uses the old sprite path, so its smoke-card defect is not fixed by this.

## Limits

- Collision is the terrain only. Trees, shrubs and rocks are visual, so flight must
  stay above the canopy (tallest placed stems reach about 39 m at maximum scale).
- The mission uses the 240 m box inside the 800 m map; drones do not roam the rest.
- Altitude lanes are absolute, not terrain following. The compressed box makes that safe.
- The browser view of a live wildland session has not been exercised.
- Fire and smoke are animated sprites, not combustion. There are no charred trees.
- Fabric logs `PopulatePointInstancerBucket invalid protoIndex` for deactivated nested
  instancers; renders were unaffected in the reviewed views.

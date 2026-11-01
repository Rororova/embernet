# Swarm mission loop — 2026-11-01

Implements the recovery in [SWARM_OBJECTIVE_RECOVERY.md](SWARM_OBJECTIVE_RECOVERY.md).
Mission logic is Isaac-free and rehearsed locally; `isaac/city_live.py` supplies measured
PhysX poses and PX4 armed state.

## Modules

- `mission_world.py`: world truth (`ScenarioWorld`) and `SimulatedSensor`: range, line of
  sight against obstacle boxes, noise, time. Labeled simulated, not neural perception.
- `routing.py`: conservative boxes measured from authored triangles, corner routing and
  per-slot holds. Holds take the active world's obstacles; never rely on the city default.
- `swarm_mission.py`: sensor → ledger → mesh → assignment → hold → virtual work → clearance.
  `PhysicsMission` still forces physical release off. Virtual work needs an acknowledged
  unexpired commitment, arrival at the hold, a fresh own sensor sighting and a safety check.
- `mission_acceptance.py`: mission gates. `mission_harness.py`: point-mass rehearsal; tests
  only, never evidence of flight. `overlay.py`: burned-in markers at measured poses.
- `tools/run_swarm_mission.py`: unattended run, one live ignite after completion, log fetch.

Operator events and clicks change world truth only. Aircraft must still detect them.

## Scenario

Six aircraft (2–8 supported), lanes 66 m+ above every measured roof except the tower.
Large fire sized so five aircraft cannot cover the report. Small fire seen in transit.
Sequence: refused release → deferred → survivor → safe release/diversion → E06 partition →
capacity expiry → reconnection → deferred fire served → fresh negative clearance.

## Protocol bugs the mission exposed

- A new incident owner renewed a previous owner's commitment; the aircraft rejected every
  renewal and the zombie commitment blocked allocation. Renewal now requires `owner == self`.
- Escalation was overwritten by later sightings; it is now terminal in merge.
- All aircraft requested release at once; the nearest asks and owners grant one at a time.
- Released aircraft resumed search; they now close on the incident while awaiting award.

## Evidence (artifacts/embernet/cloud/<run>/)

| Run | Result |
| --- | --- |
| live-f27378fa4504 | Failed at start: camera attribute None. No flight |
| live-77d999bc0698 | 20/20 gates, 141.0 s; recording rejected: framing, diversion, smoke, wall time |
| live-014215bcea21 | Passed, 132.0 s, default mission camera, no browser input; 5% black frames at the small fire before the exposure fix |
| live-ae4bc0146502 | Stored false: a browser added F03 7 s after completion. Rescored separately; original kept |
| live-2b765376aa59 | Hit the 900 s cap at 120 s mission time (RTF 0.165). Failed; browser held manual camera |
| live-d2bfb1c426b2 | Mission passed; 46 black frames all from manual orbits inside geometry |
| live-a0ed6a9a7848 | **All gates passed**, 132.0 s, 0/6,485 dark, min separation 5.97 m, clearance 18.5 m, live ignite F03 at (120,106). Bird's-eye view: an open browser tab sent one camera command |
| live-3e9b4b6b9124 | Wildland launched from the switch; not completed. My hold used city boxes, so aircraft held at 117 m and lost the fire at 7% remaining |
| live-80c4b90bcaa9 | **Wildland, all gates passed**, 119.0 s, launched by the world switch, default mission camera with 3x shells, no browser input, 0/1,215 dark, RTF 0.51, min separation 6.77 m, terrain clearance 4.29 m, live ignite F03 at (163,228). Inspected: aircraft and rotors recognizable; only about 4.9 rendered fps |

Accepted evidence: city `live-a0ed6a9a7848`, wildland `live-80c4b90bcaa9`. Later fix after
the city run: holds use active-world obstacles. City holds are unchanged by it but no city GPU
run followed. Live full-screen UI was tested in a browser only against a local stand-in.

Visibility: 3x shells proven by colour/diff probes within 110 px at 6 m range; centroid error
is 1–26 px and is polluted by scene change, so it is not a pose-accuracy figure.

## Performance (measured, same mission)

| Run | fps received by render loop | Real-time factor | Frame ms |
| --- | --- | --- | --- |
| before overlay fix | 9.5–11.6 | 0.19–0.26 | 55 |
| after | 13.5 | 0.30 | 30 |

Text rasterization in the overlay was the largest frame cost; labels are now cached stamps.
Rendering was 14 ms, so removing buildings alone would not have helped much. 645 of 987
context buildings beyond 600 m are deactivated; the run-to-run change was 15→10 ms render,
one sample only. Sandbox speed varies (0.165–0.30). Do not claim 10x, locked FPS or zero lag.

Rule-based vs trained actor in the point-mass rehearsal, seeds 41–50: both 10/10; median
completion 137.5 s vs 154.5 s; minimum separation 5.0 vs 3.7 m. Baseline stays default.
Rehearsal only, recorded before later fixes; not a flight comparison.
Results: `artifacts/embernet/mission-policy-comparison.json`.

## Limits

- Close-range fire/smoke sprites remain crude. Smoke is translucent now but blocky.
- Aircraft shells are 3x visual scale only; mass, inertia and collision are unchanged, and
  the frame and UI say so.
- City mission camera with 3x shells has no full recording: open browsers kept overriding it.
  Wildland has one. Manual orbit returns to the mission camera after 20 s without input, but
  a selected camera mode stays selected. At 60 s in wildland the ground fire sits just below
  the frame: the mission camera still needs to weight the incident more.
- Wildland renders far slower than the city (about 4.9 vs 13.5 fps) despite a higher real-time
  factor. It flies with the other session's higher PX4 limits; measured peaks are lower than
  the 80 m/s limit.
- Worlds are chosen at launch. Changing world needs a new session and voucher.
- Ignite covers the 240 m mission area, up to 12 fires. Scripted 4-drone seed 41 reaches 3.0 m
  separation in rehearsal.
- No neural perception in this loop. Obstacle boxes are conservative, not a general planner.
- Session cap raised to 1,200 s within the free-credit guard. Billed $0 throughout.

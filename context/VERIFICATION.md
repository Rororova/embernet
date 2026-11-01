# Current release verification — 2026-11-01

Latest: live-10e509a5b313 passed full cloud functional acceptance on actual
RTX PRO 6000 / Isaac 6.2 / three PX4 vehicles. H.264 averaged 23.952 received fps,
camera-state ACK 578 ms; mouse orbit was browser-verified. All 33 native files
were downloaded, and the received H.264 sample decoded with zero errors. See
ARCHITECTURAL_RUN.md for timings, evidence and remaining visual limits.


62 tests pass, Ruff and both JavaScript parser checks pass. Coverage includes
candidate ONNX inference, deterministic real-data preparation, city/fire constants,
synthetic IR, prefixed RGB/IR frames, camera/altitude bounds, mesh partition state,
independent flight ceiling and detailed Iris geometry, alongside the earlier core
suite. Candidate ONNX checker/parity passed (max absolute error .000305); all 48
held-out FLAME 3 pairs were processed at fixed defaults. Candidate warnings are
24/24 source-fire and 0/24 source-no-fire; flame-only recall remains 0/24.
See REAL_PERCEPTION.md and the e1 evaluation summary.

Metro 30 live city `live-9980e01a1da0` started natively, reached three armed
Offboard aircraft, and delivered 299 RGB + 299 synthetic IR frames at about 10 fps
client-side. The 30th-floor fire and PBR city are visible and the mesh/IR state is
present in the UI. This is not final acceptance: **smoke sprites render as opaque
dark cards**, the automated interaction test is not passed, radar was not
implemented, and “no lag” is not established. Evidence is preserved under
artifacts/embernet/cloud/live-9980e01a1da0/.

Full current RRD is ~19 MB and passes `rerun rrd verify`, including geometry and
camera data. Initial viewer-enabled files were header-only: viewer connection
replaced the file sink. Explicit FileSink/GrpcSink fan-out fixes this; the
regression test checks complete independent destinations. Old partial files
remain archival failures, not successful exports.

Browser: observed sample navigation/empty state, camera switching, focus view,
truth/report mode and speed reflection. Narrow DOM fit verified at 375px.
Primary evidence: release-review/swarm-follow-close.png and real-observations-pair.png.
Native GLB importer stalled on this host; native telemetry now decodes shared
GLB geometry into Mesh3D. CLI file verification passes, native visual acceptance
remains pending. Do not use the failed white capture as proof of a native pass.

## Earlier autonomy evidence (preserved)


The earlier core suite had 25 passing tests. Coverage includes deferred retention, stale
reports, survivor priority, deduplication, command validation/reserve/interlocks,
release authority and versions, expired/unacknowledged capacity, partition
expiry, multi-hop delivery, actor truth isolation, deterministic missions,
vision gradients, recurrent masks, API validation and Rerun recording.
Ruff and JavaScript syntax checks pass. Additional cases verify actual stale
incident verification waypoints, smaller-fire release requests, stale-owner
takeover, subject response without water, and cached return/service behavior.

Native Rerun launched after correcting executable PATH; disk recording verified.
Current seed-41 reference mission, 180s: 2 fires contained, person reached,
1 replenishment, 0 safety interventions/contacts. Initial integrated V1 neural
mission: person reached, 1 fire contained, 0 safety interventions/contacts.
Residual small fire motivated V2 vision refinement; preserve that failure result.

Final integrated V2 seed-41 run: 2/2 fires contained, person reached, one
replenishment, zero safety interventions/contacts. Native viewer inspected live;
proof is review/rerun-live.png. JSONL-to-Rerun reconstruction verified for 180 frames.

Fresh seeds 92001â€“92004, 150s each, E03 isolated during 40â€“60s:

| Sensor / policy | Mean score | Fires contained / 11 |
| --- | ---: | ---: |
| Reference / baseline | 36.376 | 9 |
| Reference / learned | 38.852 | 10 |
| Neural / baseline | 38.536 | 10 |
| Neural / learned | 38.674 | 10 |

All 16 runs reached their one person and measured zero safety interventions or
contacts. Final neural/neural leaves one incident active at the 150s cutoff.
Before explicit stale-incident revisits, that combination contained 11/11;
the final behavior favors rechecking remembered reports and this outcome is
reported rather than hidden. This small suite is a regression check, not proof
of statistical superiority. Matrix includes source and checkpoint SHA-256 hashes.

Original GPU mission test, using reference sensors: baseline mean score 36.2235,
learned 40.7695 on four held-out seeds. See original reports for per-seed metrics.

Evidence: artifacts/embernet/embernet-v1/, evaluation/reference/,
evaluation/learned/, logs/. Browser review captures are in review/; the mobile
full-page capture has stitching artifacts and does not prove a mobile pass.

Limits: no physical flight/discharge, real-camera validation, calibrated thermal
or fire physics, real rescue, hardware mesh or PX4/Isaac integration. Contacts
measure <1.5m at simulator steps, not swept-volume collision geometry. Ownership
reconciliation under partitions is best-effort, not distributed consensus.

Browser review disposition: Pass for the original findings after one corrective
batch. Fleet nodes persist, paused selection updates cameras, scale follows map
units, and mobile exports/fit are corrected. Final viewport width390 reported
scrollWidth375. Independent review was source/screenshots; not a full device test.

| Original UI finding | Final review status |
| --- | --- |
| Fleet polling destroys keyboard focus | Resolved |
| Paused map selection leaves stale cameras | Resolved |
| Fixed distance scale | Resolved |
| Mobile exports and horizontal fit | Resolved |

## Isaac cloud verification
38 source tests pass, including measured-state/no-teleport contracts, source/time
validation, gravity-balanced control, rotor allocation, depth projection, and a
queued-packet isolation/reconnect test. Isaac 6.2 boot, 250 Hz hover/waypoint,
force-disturbance recovery and three-vehicle learned-policy navigation passed on
L40S. Fleet-v2 audits zero isolated-node deliveries during its 10 s outage and 13
after reconnect. Full reports, runtime/source hashes and MP4s are under isaac/.
First fleet run's flag-only outage claim was corrected and retained with a note.
See ISAAC_SIM.md for exact metrics, failed 5.1 startup and scope. These are ideal
unloaded-airframe/no-fire trials, not validation of real hardware or fire physics.

# EMBERNET

A decentralized drone swarm for fire and survivor response, simulated in NVIDIA Isaac
Sim. Six PX4-controlled aircraft search a world with no shared map of the incident.
Each one keeps its own ledger, shares evidence over a lossy radio mesh, negotiates who
responds, and keeps working when the mesh breaks.

**Live demo: <https://ieirodov14--embernet-live-gateway.us-east.modal.run>**
[![Watch the EMBERNET demo video](https://drive.google.com/thumbnail?id=FILE_ID&sz=w1280)](https://drive.google.com/file/d/FILE_ID/view)

> [!IMPORTANT]
> **Visit the demo. Do not run EMBERNET locally until you have finished the
> [base configuration](#base-configuration).**
>
> A fresh clone does not reproduce the demo. The demo runs on a cloud RTX GPU with Isaac
> Sim, PX4 and licensed NVIDIA assets. A local run gives you a separate, simpler
> simulation, and trained models and scene assets are not in this repository. Launching
> the cloud scripts as they stand will fail, because they only accept specific accounts.
> Once configured for your own account, they spend real money.

## Using the demo

Open the link in a desktop browser, in a wide window. Nothing needs installing. On
narrow windows the toolbar covers the top of the picture. The first frames can take a
few minutes if a session is still warming up.

| | Spectator (anyone with the link) | Controller (private control code) |
| --- | --- | --- |
| Watch the live video and synthetic IR | Yes | Yes |
| Read everything under **Panels** | Yes | Yes |
| Change the view, or drag to orbit | No, you see the controller's view | Yes |
| Add fires or survivor evidence | No | Yes |
| Isolate a drone's radio | No | Yes |
| Pause, or end the session | No | Yes |

Most readers are spectators, and that is enough: the mission runs by itself with no
operator input. **Select Panels first.** That drawer holds the data the analysis below
relies on.

### Controller actions

Unlock by entering the control code under **Panels → Room access**.

- **View** switches between Mission, Bird's-eye, Overview, Fire, Follow and Onboard.
  **Drone** picks the aircraft for Follow and Onboard.
- **Drag** orbits, **right-drag or Shift-drag** pans, and the **wheel** zooms. A manual
  orbit returns to the mission camera after 20 seconds without input.
- **Add fire**: set Size and Heat, select Add fire, then click the ground or a building.
  Press Escape to cancel. Placement uses the latest camera and conservative obstacle
  boxes, so it is approximate on a moving view.
- **Panels → Add a fire or survivor by position** does the same by coordinates.
- **Panels → Radio fault** isolates a drone, then reconnects it.
- **End** stops the session for everyone.

An operator fire changes world truth only. It appears in **World truth**, but no drone
knows about it until one detects it. Watching that gap close is the best test you can
run yourself.

## Reading the screen

**In the picture**

- Ringed markers are aircraft, labeled with their ID and current task (`E01 respond`,
  `E03 return`).
- Diamonds are fires, labeled with the incident and how many aircraft are committed.
- A line from an aircraft to a fire shows who is responding.
- The minimap is at the bottom right. The latest decisions are at the bottom left.
- The inset at the top right is synthetic thermal IR derived from the render. It is
  uncalibrated and is not a sensor measurement.

Aircraft shells are drawn at 3× scale so they are visible. Flight physics use the real
1.5 kg airframe.

**In the status bar**

| Field | Meaning |
| --- | --- |
| Sim | Simulated mission time. Every timestamp in the logs uses this clock |
| Left | Real seconds until this session ends |
| Mesh | Packets delivered / packets lost, cumulative |
| RGB fps received | Video actually reaching your browser, not the render rate |

**In Panels**

| Panel | What it tells you |
| --- | --- |
| Decision log | The last 10 mission decisions, newest first |
| Aircraft | Each drone's altitude, remaining capacity, mesh state, PX4 mode, task and reason |
| What the swarm believes | The shared incident ledger: status, evidence age, who knows, who is committed |
| World truth | The scenario's real state. Observer only; aircraft never read it |
| Mesh | Live link graph, links up, packets in transit, recent packet traffic |

The difference between **World truth** and **What the swarm believes** is the point of
the project. Aircraft act only on their own sensor readings and delivered messages, so
the two panels are expected to disagree for a while.

## What a mission looks like

Each session plays the same scripted scenario. This is the accepted city run
(`live-a0ed6a9a7848`), in simulated seconds. The live demo followed the same course when
checked, also finishing at 132.0 s.

| Sim time | What happens | Where to see it |
| --- | --- | --- |
| 0 | Fires are placed. No aircraft knows about them | World truth is populated, the ledger is empty |
| 16 | Two drones detect fires with their simulated sensors | `Sensor detected fire at confidence…` |
| 37–55 | A responder asks to leave and is refused, because the others can't cover the demand | `Refused E01 release: others cover 50.0 of 55.6 required` |
| 38 | The new incident is remembered instead of dropped | `Release refused; keeping commitment…` |
| 71 | A survivor signal begins and several drones detect it | `Sensor detected person…` |
| 71–72 | Coverage is now sufficient, so the responder is released and diverts | `Released responder; acknowledged team still covers demand` |
| 75 | E06's radio is cut | Mesh shows E06 isolated, Aircraft shows `isolated` |
| 88 | Virtual work contains the first fire | `Virtual work contained the fire; awaiting clearance` |
| 90 | The team stops counting E06's capacity, while E06 keeps acting alone | `Team no longer counts E06; commitment expired` |
| 91 | The survivor is verified up close and ground rescue is requested | `Possible survivor verified at close range…` |
| 92 | Clearance needs fresh evidence. Owners out of reach are replaced locally | `Four fresh negative observations; cleared`, `Owner … unreachable` |
| 99–103 | E06 reconnects and ledgers merge without rewriting timestamps | `Ledgers merged after reconnection; evidence times preserved` |
| 128–132 | The deferred fire is served and cleared. Drones refill and the mission ends | `All fires cleared by fresh observations; survivor escalated` |

Simulation runs slower than real time. In the session checked, the mission took about
10 of the session's 20 minutes. After **Mission complete**, drones go back to searching
and nothing new happens unless a controller adds a fire. If you arrive at that point,
wait for the next session or read the aftermath using the checks below.

## Analyzing the demo

Do not judge the swarm by whether the drones look busy. Ask these questions, and take
the answers from the panels. The Decision log shows only the last 10 entries, so catch
the early refusals live or note them as they scroll past.

| Question | How to check | A good result |
| --- | --- | --- |
| Did knowledge arrive honestly? | Compare World truth with the ledger early in the run | Fires exist in World truth before any incident appears |
| Is evidence really being shared? | Watch **known by** rise above the number of drones that saw it | Incidents reach `known by 6` through the mesh |
| Do commitments mean anything? | Compare a bid with **committed** in the ledger | `Bid sent; awaiting acknowledged assignment` does not count as committed |
| Does the swarm refuse unsafe moves? | Look for `Refused … release` with its numbers | A drone stays until the others cover the demand |
| Is deferred work remembered? | Follow the refused incident to the end | It gets served, not lost |
| Does a partition really partition? | During 75–99 s, watch E06 in Mesh and Aircraft | E06 is isolated, yet still sensing and deciding |
| Does the team react to lost capacity? | Look for `Team no longer counts E06` | Unreachable capacity is dropped |
| Is the reunion clean? | After 103 s, check evidence age in the ledger | Original times survive the merge |
| Is clearance earned? | Read how each fire ended in World truth | `contained by virtual work`, not `manually cleared` |
| Is capacity real to the logic? | Watch capacity fall in Aircraft | Drones return to their pads and replenish |

**Reading the radio numbers.** Loss is simulated on purpose. In one live snapshot the
Mesh field read 11,823 delivered and 2,925 lost, with 12 of 15 links up. Those aren't
failures: links also drop with range, and the mission is meant to work through them.
Sustained traffic and isolation of the right node are what matter.

**As a controller,** the most useful experiments are:

- Add a fire out of sight of the fleet and time the gap between World truth and the
  first detection.
- Isolate the drone that owns an incident and watch ownership move.
- Compare the Bird's-eye and Onboard views to separate the swarm picture from what one
  aircraft can see.

Avoid **Clear manually** unless you intend it. It is labeled as not autonomous and fails
the `no_manual_clearance` gate.

## If the demo is offline

The page stays up, but GPU sessions do not run around the clock. Each lasts 20 minutes
at most. New sessions restart the scenario and can leave a gap of several minutes while
warming up. Sessions also stop when a time or budget limit is reached. The current
campaign ends at 18:14 IST on 2026-11-01, or earlier if a guard trips.

`Recorded preview · offline` means the image is a recording, not a live scene. Spectators
cannot start a session, so a controller has to launch one.

## What is and isn't proven

**Verified on real PX4/PhysX runs.** Automated mission gates passed in the city
(`live-a0ed6a9a7848`, all 21 checks, 132.0 s) and wildland (`live-80c4b90bcaa9`, 119.0 s).
Minimum separation was 5.97 m and 6.77 m. The gates live in
[mission_acceptance.py](embernet/mission_acceptance.py). Live sessions are not
automatically rescored.

**Limits to keep in mind**

- Detection comes from a labeled simulated range and line-of-sight sensor, not neural
  perception.
- Suppression is virtual. No payload exists, physical release is disabled, and fire and
  smoke are animated effects, not combustion physics.
- Ground rescue is requested, never simulated.
- Video frame rate varies and is not locked. About 17–24 fps has been received in the
  city, and wildland renders far slower. Latency is not zero.
- Close-up fire and smoke remain visibly crude, and final visual acceptance is open.
- Add fire was not accepted end-to-end through the browser on a live GPU.
- ROS, ns-3, real radios and real flight are future work.

**Separate real-image work.** A fine-tuned fire/smoke detector raised warnings on 24 of
24 held-out FLAME 3 fire samples and 0 of 24 no-fire samples, on one prescribed burn.
Flame-only recall is 0 of 24, so every positive came from smoke. This detector is not
connected to the swarm. See [Real perception](context/REAL_PERCEPTION.md).

## Base configuration

Complete this before running anything. Which parts you need depends on what you want to
run.

**For any local run**

1. Use Windows. The launchers are PowerShell and `.cmd` scripts.
2. Install [uv](https://docs.astral.sh/uv/), then run `.\Setup-EMBERNET.ps1`. It installs
   Python 3.12, the dependencies and the 3D scene assets.
3. Expect `artifacts/` to be missing, because it is not in Git. Trained weights, the detector, FLAME 3 samples
   and all recorded evidence are missing from a clone. Without them the launcher falls
   back to reference sensors and the rule-based baseline, and `/perception` reports
   nothing ready. Requesting learned models that are absent gives an explicit error.

**For the cloud demo, additionally**

4. Create your own [Modal](https://modal.com) account and CLI profile.
5. Add that profile to the allowlists in [cloud_live.py](cloud_live.py) and
   [Run-EMBERNET-Cloud.ps1](Run-EMBERNET-Cloud.ps1). Only the maintainers' profiles are
   accepted today.
6. Read the NVIDIA terms in [Isaac setup](context/ISAAC_SIM.md) and record your consent in
   `artifacts/embernet/isaac/license-consent.json`. Asset fetching refuses to run without
   it.
7. For the wildland world, populate the `embernet-wildland-assets` Modal Volume.
8. Check the cost first. One session uses an RTX PRO 6000, 12 cores and 64 GiB, roughly
   $6/hour or $151/day at the rates published on 2026-11-01. The free-credit check and
   the [budget runner](context/BUDGET_RUNNER.md) are application guards, not provider caps.
9. Keep `*.private.json` control invites out of Git, archives and screenshots.

## Running it yourself

After the base configuration:

```powershell
# Local kinematic forest at http://127.0.0.1:8780, with no Isaac or PX4
.\Start-EMBERNET.cmd

# Tests and real-image inference
.venv-embernet/Scripts/python.exe -m pytest -q
.venv-embernet/Scripts/python.exe -m embernet perceive path/to/images

# Cloud room: deploys, then prepares one bounded session. Preparation starts no GPU
.\Run-EMBERNET-Cloud.ps1 -Profile <your-profile> -Seconds 600 -World city
```

The local forest is a different simulation from the demo: kinematic flight, no PX4, and
its own browser UI. The [Runbook](context/RUNBOOK.md) covers its controls and CLI.

## Documentation

- [Architecture](context/ARCHITECTURE.md) and [incident memory](context/INCIDENT_MEMORY.md)
- [Swarm mission evidence and limits](context/SWARM_MISSION.md)
- [Current state](context/STATUS.md) and [verification](context/VERIFICATION.md)
- [Isaac Sim](context/ISAAC_SIM.md), [PX4 in the cloud](context/PX4_CLOUD.md) and
  [wildland](context/WILDLAND.md)
- [Deployment](context/DEPLOYMENT_IEIRODOV14.md) and [training](context/TRAINING.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

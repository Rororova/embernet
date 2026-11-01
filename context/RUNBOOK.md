# Runbook

Windows setup: run `./Setup-EMBERNET.ps1` once (requires uv), then open
`Start-EMBERNET.cmd`. Direct: `.venv-embernet/Scripts/python.exe -m embernet serve --rerun`.
The launcher opens the live 3D forest, saves Rerun recordings, and selects V2 weights when
present. -Reference selects the baseline; -Rerun opts into native viewing on a fresh
server. -TelemetryOnly skips the browser. Open saved RRDs for replay in Rerun.
Real observations: http://127.0.0.1:8780/perception. No deployment.


Direct `serve` starts paused. Launch, change speed, add fires/people/animals, break
mesh or isolate a drone, and inspect its ledger. Settings apply on Reset.
Reference/learned sensors and policies are independent choices. Missing weights
produce explicit errors rather than hidden fallback.

Headless reference: `python -m embernet demo --seconds 180` using the venv Python.
Neural: add `--models artifacts/embernet/embernet-v2 --learned-vision --learned-policy`.
Use `--output PATH` to separate experiments. Each writes mission.rrd,
replay.jsonl and report.json. Open RRD with `.venv-embernet/Scripts/rerun.exe PATH`.
`python -m embernet replay JSONL_PATH` reconstructs a recording from snapshots;
camera pixels remain in the original RRD, not JSONL.

No browser needed for commands: `python -m embernet control launch`, `control
pause`, `control fire --x 150 --y 120`, `control person --x 155 --y 122`,
`control mesh-off`, `control mesh-on`, `control isolate --drone E03`, or
`control reset --learned --seed 41`. Prefix each with the venv Python.

Local training: `python -m embernet train vision` or `train mission`. `--small`
is a pipeline smoke test, not useful model training. For Modal, read TRAINING.md;
set `$env:MODAL_PROFILE='nikhilthakuraan'`, `$env:PYTHONUTF8='1'`, then run
`tools/launch_training.py` with the venv Python. Use unique IDs for new runs.

Errors pause the mission and appear in `/api/state`; Reset recovers. Viewer
failure does not stop disk recording. Telemetry prepends active venv Scripts to
PATH before spawning the native viewer. Sandbox viewer-settings warnings do not
invalidate recordings. Server binds only loopback; remote authentication is not
implemented. Do not expose it publicly without a separate access design.

Radio partitions do not freeze local autonomy; commitments expire without owner
renewals. Received evidence retains original times. Six drones are the verified
default; evaluate coverage/lanes before relying on other configurations.

Real-image CLI: `python -m embernet perceive IMAGE_OR_FOLDER --output PATH`.
Uses the included pinned ONNX detector. Reproduce the 48-pair inspection with
`python tools/benchmark_real_perception.py`; see REAL_PERCEPTION.md for limits.

## Isaac physics trials
Read ISAAC_SIM.md before running the separate cloud backend. Use
`.\Run-EMBERNET-Isaac.ps1 -Mode flight -AcceptNvidiaEula` or `-Mode fleet`.
The launcher verifies asset hashes and the Modal free-credit guard, then downloads
video, measured telemetry, camera calibration and complete console/Kit output.
It does not change the backend of the existing browser demo. NVIDIA binaries and
non-CC-BY oak content are fetched separately after license acknowledgement.

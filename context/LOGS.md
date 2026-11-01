# Logs

Location: `artifacts/embernet/logs/`.

- index.json: export interval, workspace, app IDs, line counts and exit codes.
- apps.json: lifecycle inventory, including unsuccessful/queued attempts.
- ap-*.log: available timestamped stdout/stderr/system events with function,
  call and container IDs; *.stderr.log preserves exporter diagnostics separately.
- billing-after.json: billing-cycle summary; collection may lag execution.
- container-ta-*.log: full container output using --all.
- image-im-*.log: all available image-build layers, not only the final layer.
- pytest.log, ruff.log and integration-evaluation.log: local verification output.
- Each model directory also holds complete epoch/update and evaluation reports.

Explicit interval starts at 2026-10-31 midnight India time, avoiding Modal's
default last-100-lines truncation. Unscheduled apps have only system records.
Refresh with `tools/export_logs.py` using the venv Python and authorized profile.
It only selects apps named embernet-training. Preserve failed runs and original
results. Never export credential files or unrelated workspace logs.

`artifacts/embernet/EMBERNET-logs-and-reports.zip` bundles these logs, model JSON
reports, the final evaluation matrix and context documents. Binary models and
RRD recordings remain in their run directories rather than inflating the log ZIP.
At the captured post-training billing snapshot billed_cost is zero; incremental
metered compute was covered by credits. Billing collection can lag.

Isaac logs: artifacts/embernet/isaac/cloud-logs/ contains all available app logs
and full image-build layers (inventory.json records exports). Per-trial folders
retain Kit console/full logs, exit/report validation, runtime/model/source hashes,
telemetry and radio audits. Failed versions and explicit correction notes are
preserved. bundle_logs.py now includes Isaac logs and JSONL in the log ZIP.

Real-perception fine-tune e1 has its own directory:
`artifacts/embernet/real-perception-v1-20261101-e1/`. It contains best/last and
ONNX checkpoints, dataset and download manifests, epoch CSV/plots, training and
FLAME 3 reports, billing snapshots, and `modal-app.log` (468 timestamped lines).
Failed a1-d1 directories retain structured failure notes and billing evidence.
Do not replace these with only the final success summary.


Architectural RTX runs (2026-11-01): native recordings and flight logs for
live-d4a5be51224e, live-43173e96538f, live-67768dce13b8, live-8d2660e0f6de and
live-10e509a5b313 are downloaded with hash manifests. Latest run contains 33 native
files / 99,255,070 bytes, including session.mp4, telemetry/physics/commands JSONL,
Kit logs, encoder.log, runtime metadata and each aircraft's ULG/BSON/PX4 console.
Local evidence also includes the received H.264 sample (decoded successfully),
transport diagnostics, screenshots, functional report and stream metrics.
Provider exports retain 35 build/app log files. Some app tails are bounded;
see provider-logs/inventory.json. Failures are preserved alongside passing runs.

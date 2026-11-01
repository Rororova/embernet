"""Fresh-seed four-way evaluation on the actual current runtime, including mesh faults."""

import csv
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from embernet.learning import PolicyRuntime
from embernet.perception import VisionRuntime
from embernet.training import scenario, score

models = Path("artifacts/embernet/embernet-v2")
output = Path("artifacts/embernet/evaluation")
output.mkdir(parents=True, exist_ok=True)
vision = VisionRuntime(models / "vision.pt")
rows = []
for seed in [92_001, 92_002, 92_003, 92_004]:
    for camera, policy in [(False, False), (False, True), (True, False), (True, True)]:
        sim = scenario(seed)
        sim.vision = vision if camera else None
        sim.policy = PolicyRuntime(models / "mission.pt") if policy else None
        sim.sensor_mode = "learned RGB/thermal" if camera else "reference sensor (oracle)"
        sim.policy_mode = "learned" if policy else "baseline"
        for tick in range(300):
            sim.mesh.isolated = {"E03"} if 40 <= sim.time < 60 else set()
            sim.step()
        row = {
            "seed": seed,
            "sensor": "learned" if camera else "reference",
            "policy": "learned" if policy else "baseline",
            "score": round(score(sim), 4),
            "fires": len(sim.fires),
            "active_remaining": sum(f.remaining > 0.2 for f in sim.fires),
            "people": sum(s.kind == "person" for s in sim.subjects),
            "person_response_seconds": next(
                (s.responded_at for s in sim.subjects if s.kind == "person"), None
            ),
            **sim.metrics,
        }
        rows.append(row)
        print(json.dumps(row), flush=True)
manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in Path("embernet").glob("*.py")}
weights = {
    p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in [models / "vision.pt", models / "mission.pt"]
}
report = {
    "seeds": [92_001, 92_002, 92_003, 92_004],
    "seconds": 150,
    "fault": "E03 isolated at 40–60s",
    "models": str(models),
    "source_sha256": manifest,
    "checkpoint_sha256": weights,
    "runs": rows,
    "interpretation": "Small synthetic regression suite. Four-way sensor/policy comparison, not field validation.",
}
(output / "matrix.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
with (output / "matrix.csv").open("w", newline="", encoding="utf-8") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

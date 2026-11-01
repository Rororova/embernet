"""Read recorded observations without rerunning decisions or inventing missing state."""

import json
from pathlib import Path
from types import SimpleNamespace

from .contracts import Config, Event, Incident, Task, VehicleState
from .simulation import Fire, Subject
from .telemetry import Telemetry


def replay_to_rerun(path, output):
    telemetry = None
    frames = 0
    with Path(path).open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("type") == "header":
                continue
            states = {}
            agents = {}
            trails = {}
            for record in row["drones"]:
                values = {key: record[key] for key in VehicleState.__dataclass_fields__}
                values["task"] = Task(values["task"])
                state = VehicleState(**values)
                states[state.id] = state
                agents[state.id] = SimpleNamespace(
                    memory=SimpleNamespace(incidents={i["id"]: Incident(**i) for i in record["incidents"]})
                )
                trails[state.id] = record["trails"]
            fires = [
                Fire(**{key: value for key, value in f.items() if key in Fire.__dataclass_fields__})
                for f in row["truth"]["fires"]
            ]
            sim = SimpleNamespace(
                c=Config(**row["config"]),
                time=row["time"],
                states=states,
                agents=agents,
                trails=trails,
                fires=fires,
                subjects=[Subject(**s) for s in row["truth"]["subjects"]],
                cameras={},
                _discharging={
                    record["id"]: record["discharge"] for record in row["drones"] if record.get("discharge")
                },
                sensor_mode=row.get("sensor_mode", "recorded sensors"),
                policy_mode=row.get("policy_mode", "recorded policy"),
                metrics=row["metrics"],
                events=[Event(**e) for e in row["events"]],
                mesh=SimpleNamespace(links=lambda _, r=row: r["mesh"]["links"]),
            )
            if telemetry is None:
                telemetry = Telemetry(output, sim)
            else:
                telemetry.log(sim)
            frames += 1
    if telemetry is None:
        raise ValueError("Replay contains no mission frames")
    telemetry.close()
    return {
        "frames": frames,
        "output": str(Path(output).resolve()),
        "cameras": "Camera pixels are in original RRD only",
    }

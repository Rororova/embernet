"""Mission-level gate over the decision log. Flight or streaming status cannot pass it."""

import json
from pathlib import Path


def _first(rows, predicate):
    return next((row for row in rows if predicate(row)), None)


def evaluate(rows, summary):
    checks = {}
    def of(kind):
        return [row for row in rows if row["kind"] == kind]

    knowledge = of("knowledge")
    checks["no_unexplained_knowledge"] = bool(knowledge) and all(r["via"] in ("sensor", "mesh") for r in knowledge)
    checks["discovered_by_sensor"] = any(r["via"] == "sensor" for r in knowledge)
    checks["shared_through_mesh"] = any(r["via"] == "mesh" for r in knowledge)
    commitments = of("commitment")
    awards = of("delivered")
    checks["commitments_match_messages"] = bool(commitments) and all(
        r.get("owner") == r["drone"]
        or any(a["message"] == r.get("message") and a["drone"] == r["drone"] for a in awards)
        for r in commitments
    )
    refusal = _first(rows, lambda r: r["kind"] == "defer")
    release = _first(rows, lambda r: r["kind"] == "release")
    divert = _first(rows, lambda r: r["kind"] == "divert")
    checks["release_refused_and_deferred"] = refusal is not None and bool(of("refusal"))
    checks["safe_diversion_after_release"] = (
        release is not None and divert is not None and release["time"] <= divert["time"]
    )
    escalation = _first(rows, lambda r: r["kind"] == "escalation")
    checks["survivor_escalated_after_diversion"] = (
        escalation is not None and divert is not None and escalation["time"] >= divert["time"]
    )
    isolate, reconnect = _first(rows, lambda r: r["kind"] == "isolate"), _first(rows, lambda r: r["kind"] == "reconnect")
    checks["partition_reconnected"] = (
        isolate is not None and reconnect is not None and reconnect["time"] > isolate["time"]
    )
    if checks["partition_reconnected"]:
        drone = isolate["drone"]
        checks["no_delivery_during_partition"] = not any(
            isolate["time"] + 1 < r["time"] < reconnect["time"]
            and (r["drone"] == drone or r.get("origin") == drone)
            for r in awards
        )
        checks["isolated_drone_kept_acting"] = any(
            r["drone"] == drone and isolate["time"] < r["time"] < reconnect["time"]
            and r["kind"] in ("review", "commitment", "ownership", "containment", "clearance")
            for r in rows
        )
    else:
        checks["no_delivery_during_partition"] = checks["isolated_drone_kept_acting"] = False
    deferred = {r["incident"]: r["time"] for r in reversed(of("defer")) if r["incident"]}
    checks["deferred_incident_revisited"] = any(
        r["kind"] in ("review", "commitment", "containment")
        and r["incident"] in deferred
        and r["time"] > deferred[r["incident"]]
        for r in rows
    )
    checks["team_dropped_unreachable_capacity"] = (
        checks["partition_reconnected"]
        and bool(of("capacity_dropped"))
        and isolate["time"] <= of("capacity_dropped")[0]["time"] <= reconnect["time"]
    )
    checks["reconciled_with_original_times"] = any(r["preserved"] for r in of("reconciled"))
    world = summary["world"]
    # Events after completion belong to a later session phase, not to this mission.
    finished = summary["completed_at"]
    fires = [f for f in world["fires"] if finished is None or f["created_at"] <= finished]
    checks["fires_contained_by_virtual_work"] = bool(fires) and all(
        f["contained_at"] is not None and not f["manual"] and f["contributors"] for f in fires
    )
    checks["capacity_consumed"] = sum(summary["capacity_used"].values()) > 0
    checks["clearance_from_fresh_observation"] = len(of("clearance")) >= len(fires)
    checks["no_manual_clearance"] = not of("manual_clear")
    checks["mission_completed"] = summary["completed_at"] is not None
    if "rendered_frames" in summary:
        checks["recording_has_no_black_frames"] = (
            summary["rendered_frames"] > 0 and summary["dark_frames"] <= summary["rendered_frames"] * 0.002
        )
    checks["separation_at_least_3m"] = summary["minimum_separation_m"] >= 3
    checks["obstacle_clearance_at_least_3m"] = summary["minimum_obstacle_clearance_m"] >= 3
    return {"passed": all(checks.values()), "checks": checks, "completed_at": summary["completed_at"]}


def evaluate_run(folder):
    folder = Path(folder)
    if not (folder / "mission-summary.json").is_file():
        return {"passed": False, "checks": {}, "completed_at": None, "error": "native run left no summary"}
    rows = [json.loads(line) for line in (folder / "decisions.jsonl").read_text().splitlines() if line]
    return evaluate(rows, json.loads((folder / "mission-summary.json").read_text()))

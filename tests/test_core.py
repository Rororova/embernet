from dataclasses import asdict, replace
from math import nan

import pytest

from embernet.contracts import Command, Commitment, Config, Detection, Message, Task, VehicleState
from embernet.coordination import Agent
from embernet.learning import observation
from embernet.memory import IncidentLedger
from embernet.mesh import Mesh
from embernet.safety import PX4Adapter, SafetySupervisor
from embernet.simulation import Simulation


def detection(x=100, now=1, kind="fire", severity=0.8):
    return Detection(kind, (x, 100, 0), 6, severity, 0.95, now, "E01")


def vehicle(drone="E01", x=100):
    return VehicleState(drone, (x, 100, 28), (x, 10, 0), stamp=1)


def test_deferred_incident_is_retained_and_reviewed_without_refreshing_evidence():
    memory = IncidentLedger()
    incident = memory.observe(detection(), "E01")
    memory.defer(incident.id, 2, "Committed to larger incident")
    original = incident.observed_at
    score = incident.priority(2)
    assert memory.incidents[incident.id].status == "deferred"
    assert incident.review_at == 8
    assert incident.priority(18) > score
    assert incident.observed_at == original
    assert not incident.fresh(100, 35)


def test_forwarding_old_evidence_does_not_make_it_fresh():
    memory = IncidentLedger()
    fresh = memory.observe(detection(now=10), "E01")
    stale = asdict(replace(fresh, observed_at=2, severity=0.1))
    memory.merge(stale)
    assert fresh.observed_at == 10
    assert fresh.severity == 0.8


def test_survivor_evidence_outweighs_large_fire():
    memory = IncidentLedger()
    small = memory.observe(detection(x=50, severity=0.2), "E01")
    memory.observe(detection(x=50, kind="person"), "E01")
    large = memory.observe(detection(x=150, severity=1), "E01")
    large.extent = 13
    assert small.priority(2) > large.priority(2)


def test_duplicate_incidents_reconcile_deterministically():
    a, b = IncidentLedger(), IncidentLedger()
    first = a.observe(detection(), "E01")
    second = b.observe(detection(x=102), "E02")
    merged_a = a.merge(asdict(second))
    merged_b = b.merge(asdict(first))
    assert merged_a.id == merged_b.id == first.id
    assert sum(i.status != "merged" for i in b.incidents.values()) == 1


@pytest.mark.parametrize("command", [Command(Task.SEARCH, (nan, 0, 28)), Command(Task.SEARCH, (1000, 0, 28))])
def test_safety_rejects_invalid_navigation(command):
    result = SafetySupervisor(Config()).check(vehicle(), command, 1)
    assert not result.allowed
    assert result.command.task == Task.HOLD


def test_reserve_overrides_learned_task_and_stale_state_holds():
    state = vehicle()
    state.battery = 0.05
    result = SafetySupervisor(Config()).check(state, Command(Task.SEARCH, (150, 150, 28)), 1)
    assert not result.allowed and result.command.task == Task.RETURN
    assert not SafetySupervisor(Config()).check(state, Command(Task.RETURN, state.home), 8).allowed


def test_physical_payload_needs_both_independent_permissions():
    state = vehicle()
    command = Command(Task.RESPOND, state.position, "I1", True)
    supervisor = SafetySupervisor(Config())
    assert supervisor.check(state, command, 1).allowed
    assert not supervisor.check(state, command, 1, physical=True).allowed
    assert not supervisor.check(state, command, 1, physical=True, human_authorized=True).allowed
    assert supervisor.check(
        state, command, 1, physical=True, human_authorized=True, independent_interlock=True
    ).allowed
    with pytest.raises(NotImplementedError):
        PX4Adapter().execute(state, command, 0.5)


def test_unacknowledged_and_expired_capacity_is_not_sufficient_for_release():
    agent = Agent("E01", 0, Config())
    incident = agent.memory.observe(detection(), "E01")
    current = Commitment(incident.id, "E02", "v1", 18, 4, 10, True, "E01")
    other = Commitment(incident.id, "E03", "v2", 100, 3, 10, False, "E01")
    agent.memory.commitments = {"E02": current, "E03": other}
    request = Message(
        "release1", "E02", "RELEASE_REQUEST", {"version": "v1", "incident_id": incident.id}, 2, "E01"
    )
    agent.receive([request], 2)
    assert not any(m.kind == "RELEASED" for m in agent.outbox)
    other.acknowledged, other.expires_at = True, 1
    agent.receive([replace(request, id="release2")], 2)
    assert not any(m.kind == "RELEASED" for m in agent.outbox)
    other.expires_at = 10
    agent.receive([replace(request, id="release3")], 2)
    assert any(m.kind == "RELEASED" for m in agent.outbox)


def test_disconnected_responder_cannot_extend_its_own_assignment():
    agent = Agent("E02", 1, Config())
    incident = agent.memory.observe(detection(), "E01")
    commitment = Commitment(incident.id, "E02", "v1", 18, 4, 5, True, "E01")
    agent.assignment = commitment
    agent.memory.commitments["E02"] = commitment
    state = vehicle("E02")
    agent.plan(state, 4)
    assert agent.assignment.expires_at == 5
    agent.plan(state, 6)
    assert agent.assignment is None


def test_release_requires_matching_version_and_owner():
    agent = Agent("E02", 1, Config())
    agent.assignment = Commitment("I1", "E02", "v1", 18, 3, 20, True, "E01")
    wrong = Message("m1", "E03", "RELEASED", {"version": "v1", "incident_id": "I1"}, 2)
    agent.receive([wrong], 2)
    assert agent.assignment is not None
    agent.receive([replace(wrong, origin="E01", payload={"version": "old", "incident_id": "I1"})], 2)
    assert agent.assignment is not None


def test_multihop_delivery_and_partition_at_arrival():
    config = Config(radio_range=70, packet_loss=0, radio_delay=0.1)
    states = {key: vehicle(key, x) for key, x in [("E01", 10), ("E02", 60), ("E03", 110)]}
    mesh = Mesh(config)
    message = Message("m1", "E01", "REPORT", {"test": True}, 0, "E03")
    mesh.send("E01", message, 0, states)
    assert not mesh.deliver(0.5, states)["E03"]
    delivered = mesh.deliver(1, states)
    assert len(delivered["E03"]) == 1
    assert mesh.stats.forwarded > 0
    mesh.send("E01", replace(message, id="m2"), 2, states)
    mesh.enabled = False
    assert all(not values for values in mesh.deliver(3, states).values())


def test_actor_observation_is_independent_of_hidden_truth():
    sim = Simulation(scenario="empty")
    before = observation(sim.agents["E01"], sim.states["E01"], sim.time)
    sim.add_fire(200, 200, 1, 12)
    after = observation(sim.agents["E01"], sim.states["E01"], sim.time)
    assert all((before[key] == after[key]).all() for key in before)


def test_default_baseline_contains_fires_and_survivor_response_is_not_rescue():
    sim = Simulation()
    sim.step(300)
    assert sim.metrics["contained"] == 2
    assert sim.metrics["survivor_responses"] == 1
    assert any("no physical rescue" in e.text for e in sim.events)
    assert sim.metrics["safety_interventions"] == 0
    assert all(0 <= state.water <= sim.c.max_water for state in sim.states.values())


def test_seeded_reference_mission_is_reproducible():
    a, b = Simulation(), Simulation()
    a.step(120)
    b.step(120)
    assert a.snapshot() == b.snapshot()

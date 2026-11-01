from embernet.contracts import Commitment, Config, Detection, Message, Task, VehicleState
from embernet.coordination import Agent
from embernet.learning import observation
from embernet.memory import IncidentLedger
from embernet.simulation import Simulation


def test_person_evidence_does_not_resurrect_a_cleared_fire():
    ledger = IncidentLedger()
    fire = ledger.observe(Detection("fire", (100, 100, 0), 5, 0.8, 0.98, 1, "E01"), "E01")
    fire.status = "cleared"
    ledger.observe(Detection("person", (101, 100, 0), 2, 0.1, 0.98, 2, "E01"), "E01")
    assert fire.status == "cleared"


def test_small_fire_can_request_release_even_when_lower_priority():
    agent = Agent("E02", 1, Config())
    large = agent.memory.observe(Detection("fire", (150, 100, 0), 10, 1, 0.99, 10, "E01"), "E01")
    small = agent.memory.observe(Detection("fire", (103, 100, 0), 2, 0.2, 0.99, 10, "E02"), "E02")
    agent.assignment = Commitment(large.id, "E02", "award1", 18, 5, 30, True, "E01")
    state = VehicleState("E02", (100, 100, 32), (100, 10, 0), stamp=10)
    command = agent.plan(state, 10)
    assert command.incident_id == large.id
    assert agent.requested_release == small.id
    assert any(m.kind == "RELEASE_REQUEST" for m in agent.outbox)
    assert small.status == "deferred"
    agent.receive(
        [Message("release", "E01", "RELEASED", {"version": "award1", "incident_id": large.id}, 11)], 11
    )
    agent.plan(state, 12)
    assert agent.diversion_target == small.id
    assert agent.assignment is None or agent.assignment.incident_id == small.id


def test_fresh_local_observer_takes_over_expired_remote_owner():
    agent = Agent("E02", 1, Config())
    incident = agent.memory.observe(Detection("fire", (100, 100, 0), 5, 0.6, 0.99, 20, "E02"), "E01")
    state = VehicleState("E02", (100, 100, 32), (100, 10, 0), stamp=20)
    agent.plan(state, 20)
    assert incident.owner == "E02"
    assert any(event.kind == "ownership" for event in agent.events)


def test_person_response_does_not_require_extinguishing_agent():
    agent = Agent("E01", 0, Config())
    incident = agent.memory.observe(Detection("person", (100, 100, 0), 2, 0, 0.99, 2, "E01"), "E01")
    state = VehicleState("E01", (100, 100, 28), (100, 10, 0), water=0, stamp=2)
    assert incident.demand() == 0
    assert observation(agent, state, 2)["mask"][4]
    command = agent.plan(state, 2)
    assert command.task == Task.RESPOND
    assert not command.release


def test_completed_service_is_not_recounted_from_a_cached_return_action():
    agent = Agent("E01", 0, Config())
    state = VehicleState("E01", (50, 10, 0), (50, 10, 0), water=18, battery=0.99, stamp=2)
    assert agent.plan(state, 2, 1).task != Task.RETURN


def test_reference_mission_has_no_proximity_contacts_and_replay_is_serializable():
    import json

    sim = Simulation()
    sim.step(360)
    assert sim.metrics["contained"] == 2
    assert sim.metrics["collisions"] == 0
    assert json.loads(json.dumps(sim.snapshot()))["time"] == 180


def test_stale_deferred_incident_gets_a_real_verification_waypoint():
    agent = Agent("E01", 0, Config())
    incident = agent.memory.observe(Detection("fire", (150, 100, 0), 3, 0.5, 0.99, 1, "E01"), "E01")
    agent.memory.defer(incident.id, 2, "Higher priority response first")
    state = VehicleState("E01", (100, 100, 28), (100, 10, 0), stamp=50)
    command = agent.plan(state, 50)
    assert command.task == Task.VERIFY
    assert command.incident_id == incident.id
    assert not command.release
    assert incident.observed_at == 1

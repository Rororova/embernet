import json
from itertools import pairwise
from math import dist

import numpy as np
import pytest

from embernet.contracts import Command, Commitment, Config, Detection, Task, VehicleState
from embernet.coordination import Agent
from embernet.memory import IncidentLedger
from embernet.mission_acceptance import evaluate
from embernet.mission_harness import rehearse
from embernet.mission_world import ScenarioWorld, SimulatedSensor
from embernet.overlay import HEIGHT, WIDTH, Projector, draw_overlay, pick_point
from embernet.routing import CITY_OBSTACLES, ROUTE_MARGIN, TOWER, clearance, route, segment_clear, standoff
from embernet.swarm_mission import FIRE_POSITION, SwarmMission, fleet_config, fleet_homes


def kinds(mission, kind):
    return [row for row in mission.log.rows if row["kind"] == kind]


@pytest.mark.parametrize("seed", [41, 42, 43])
def test_six_drone_mission_completes_every_gate_without_operator_input(seed):
    mission = rehearse(6, seed=seed)
    result = evaluate(mission.log.rows, mission.summary())
    assert result["passed"], [key for key, value in result["checks"].items() if not value]


@pytest.mark.parametrize("drones", [3, 4, 8])
def test_other_fleet_sizes_complete_the_mission(drones):
    mission = rehearse(drones, seed=41)
    assert mission.completed_at is not None
    assert mission.summary()["physical_release"] is False


def test_no_ledger_holds_an_incident_before_any_observation():
    mission = SwarmMission(6)
    assert mission.world.fires
    assert all(not agent.memory.incidents for agent in mission.bridge.agents.values())


def test_every_ledger_entry_has_a_declared_path():
    mission = rehearse(6)
    rows = kinds(mission, "knowledge")
    assert {row["via"] for row in rows} == {"sensor", "mesh"}
    for key, agent in mission.bridge.agents.items():
        assert set(agent.memory.incidents) <= {row["incident"] for row in rows if row["drone"] == key}


def test_operator_events_change_the_world_not_a_ledger():
    mission = SwarmMission(3, script=False)
    mission.add_fire((90, 90, 1), 2, 0.4, 0)
    mission.add_subject((90, 92, 1), 0)
    assert all(not agent.memory.incidents for agent in mission.bridge.agents.values())


def test_manual_clear_is_never_counted_as_autonomous():
    mission = rehearse(6)
    summary = mission.summary()
    summary["world"]["fires"][0]["manual"] = True
    assert not evaluate(mission.log.rows, summary)["checks"]["fires_contained_by_virtual_work"]


def test_fire_added_after_completion_is_outside_the_mission():
    mission = rehearse(6)
    mission.add_fire((90, 90, 1), 2, 0.4, mission.completed_at + 7)
    assert evaluate(mission.log.rows, mission.summary())["passed"]


def test_large_fire_shrinks_only_through_committed_work():
    mission = rehearse(6)
    fire = mission.world.fires[mission.large_fire]
    assert fire.contained_at is not None and not fire.manual and len(fire.contributors) >= 3
    assert all(0 <= state.water <= mission.c.max_water for state in mission.bridge.states.values())
    assert sum(mission.used_capacity.values()) >= fire.initial


def test_no_work_without_acknowledged_commitment():
    mission = SwarmMission(3)
    key, state = "E01", mission.bridge.states["E01"]
    fire = mission.world.fires[mission.large_fire]
    goal = standoff(fire.position, 0)
    state.position, state.stamp, state.healthy = goal, 1.0, True
    mission.seen[key] = {fire.id: 1.0}
    incident = mission.bridge.agents[key].memory.observe(
        Detection("fire", fire.position, 8, 0.9, 0.9, 1.0, key), key
    )
    mission._virtual_work(key, Command(Task.RESPOND, goal, incident.id), goal, 1.0)
    assert fire.remaining == fire.initial and state.water == mission.c.max_water


def test_refused_release_keeps_the_commitment_and_remembers_the_small_fire():
    mission = rehearse(6)
    assert kinds(mission, "refusal") and kinds(mission, "defer")
    first_defer = kinds(mission, "defer")[0]
    assert first_defer["time"] < kinds(mission, "divert")[0]["time"]
    assert mission.world.fires[mission.small_fire].contained_at > first_defer["time"]


def test_released_aircraft_goes_to_the_survivor_instead_of_searching():
    mission = rehearse(6)
    diverted = kinds(mission, "divert")[0]["drone"]
    assert kinds(mission, "escalation")[0]["drone"] == diverted


def test_mission_camera_keeps_a_working_formation_close():
    from embernet.isaac.city_live import mission_camera

    positions = [standoff(FIRE_POSITION, slot) for slot in range(6)]
    framing = mission_camera(positions, [FIRE_POSITION], None)
    assert dist(framing[:3], framing[3:]) < 60


def test_survivor_is_escalated_not_rescued():
    mission = rehearse(6)
    row = kinds(mission, "escalation")[0]
    assert "none simulated" in row["text"]
    assert all(s.escalated_at is not None for s in mission.world.subjects.values())


def test_partition_blocks_traffic_and_drops_unreachable_capacity():
    mission = rehearse(6)
    isolate, reconnect = kinds(mission, "isolate")[0], kinds(mission, "reconnect")[0]
    assert isolate["time"] <= kinds(mission, "capacity_dropped")[0]["time"] <= reconnect["time"]
    assert kinds(mission, "reconciled")[0]["preserved"]


def test_flight_stays_clear_of_measured_city_boxes():
    mission = rehearse(6)
    assert mission.minimum_clearance >= 3
    assert mission.minimum_separation >= 3


def test_owner_change_leaves_old_commitment_to_expire():
    config = Config(drones=2, size=240)
    agent = Agent("E01", 0, config)
    incident = agent.memory.observe(Detection("fire", (50, 50, 1), 2, 0.3, 0.9, 10, "E01"), "E01")
    agent.memory.commitments["E02"] = Commitment(incident.id, "E02", "old", 5, 3, 13, True, "E02")
    agent.bids[incident.id] = {
        "E02": {
            "drone_id": "E02", "water": 5, "battery": 1, "eta": 3, "servicing": False,
            "assigned": incident.id, "stamp": 10,
        }
    }
    agent._auction(10)
    assert agent.memory.commitments["E02"].expires_at == 13
    assert not [m for m in agent.outbox if m.kind == "AWARD"]


def test_escalation_cannot_be_reopened_by_a_later_sighting():
    ledger = IncidentLedger()
    report = ledger.observe(Detection("person", (10, 10, 1), 2, 0.2, 0.8, 5, "E01"), "E01")
    report.status = "escalated"
    newer = {**ledger.records()[0], "observed_at": 9.0, "status": "confirmed"}
    assert ledger.merge(newer).status == "escalated"
    other = IncidentLedger()
    other.merge({**ledger.records()[0], "status": "confirmed", "observed_at": 12.0})
    assert other.merge(ledger.records()[0]).status == "escalated"


def test_late_report_keeps_its_original_observation_time():
    ledger = IncidentLedger()
    source = IncidentLedger()
    report = source.observe(Detection("fire", (10, 10, 1), 2, 0.3, 0.8, 5, "E01"), "E01")
    assert ledger.merge(source.records()[0]).observed_at == report.observed_at == 5


def test_tower_blocks_the_simulated_sensor():
    world = ScenarioWorld(CITY_OBSTACLES)
    fire = world.add_fire(FIRE_POSITION, 10, 0.9)
    sensor = SimulatedSensor(world)
    assert sensor.scan("E01", (150, 110, 105), 1)[1] == [fire.id]
    assert sensor.scan("E01", (150, 190, 105), 1)[1] == []
    assert sensor.scan("E01", (150, 110, 5), 1)[1] == []


def test_sensor_does_not_see_subjects_beyond_close_range():
    world = ScenarioWorld(CITY_OBSTACLES)
    subject = world.add_subject((100, 100, 2))
    sensor = SimulatedSensor(world)
    assert sensor.scan("E01", (100, 80, 20), 1)[1] == [subject.id]
    assert sensor.scan("E01", (100, 20, 40), 1)[1] == []


def test_route_goes_around_the_tower():
    start, goal = (150, 100, 80), (150, 200, 80)
    assert not segment_clear(start, goal, CITY_OBSTACLES)
    path = [start, *route(start, goal)]
    assert path[-1] == goal
    for a, b in pairwise(path):
        assert segment_clear(a, b, CITY_OBSTACLES)


@pytest.mark.parametrize("slot", range(8))
def test_standoffs_are_clear_and_unique(slot):
    position = standoff(FIRE_POSITION, slot)
    assert clearance(position, [TOWER]) > ROUTE_MARGIN
    assert all(
        dist(position, standoff(FIRE_POSITION, other)) >= 4 for other in range(8) if other != slot
    )


def test_search_lanes_clear_measured_buildings():
    config = fleet_config(8)
    roofs = [box.high[2] for box in CITY_OBSTACLES if box is not TOWER]
    assert config.altitude > max(roofs)
    assert config.altitude + 7 * 4 <= config.ceiling


def test_projector_places_the_look_at_point_at_image_centre():
    projector = Projector((0, 0, 10), (50, 0, 10), (0, 0, 1))
    x, y, depth = projector((50, 0, 10))
    assert (x, y) == pytest.approx((WIDTH / 2, HEIGHT / 2)) and depth == pytest.approx(50)
    assert projector((-50, 0, 10)) is None
    assert projector((50, 10, 10))[0] < WIDTH / 2


def test_overlay_is_drawn_from_measured_positions():
    mission = rehearse(3, limit=30)
    frame = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
    positions = {key: state.position for key, state in mission.bridge.states.items()}
    position = positions["E01"]
    projector = Projector(np.add(position, (-10, -10, 5)), position, (0, 0, 1))
    result = draw_overlay(frame, projector, mission, positions, phase="test")
    assert result.shape == frame.shape and result.any()


def test_click_hits_the_ground_or_building_under_the_pixel():
    camera = Projector((120, 40, 60), (120, 120, 0), (0, 0, 1))
    point = pick_point(camera, 0.5, 0.5, None, (), 240)
    assert point == pytest.approx((120, 120, 1), abs=3)
    u, v = camera(FIRE_POSITION)[:2]
    hit = pick_point(camera, u / WIDTH, v / HEIGHT, None, CITY_OBSTACLES, 240)
    assert 128 <= hit[0] <= 172 and hit[2] > 90


def test_click_outside_the_mission_area_is_refused():
    camera = Projector((120, 200, 40), (120, 400, 0), (0, 0, 1))
    assert pick_point(camera, 0.5, 0.5, None, (), 240) is None


def test_click_uses_terrain_height_when_present():
    camera = Projector((120, 40, 90), (120, 120, 0), (0, 0, 1))
    point = pick_point(camera, 0.5, 0.5, lambda x, y: 20.0, (), 240)
    assert point[2] == pytest.approx(21.0)


@pytest.mark.parametrize("position", [(40, 160, 62), (220, 150, 50), (150, 200, 18), (115, 170, 19)])
@pytest.mark.parametrize("slot", range(6))
def test_rooftop_fires_get_holds_clear_of_every_building(position, slot):
    assert clearance(standoff(position, slot), CITY_OBSTACLES) >= ROUTE_MARGIN


def test_swarm_finds_a_clicked_fire_after_the_mission():
    mission = rehearse(6, limit=200)
    from embernet.mission_harness import fly

    fire = mission.add_fire((60, 90, 1), 3, 0.5, mission.time)
    positions = {key: state.position for key, state in mission.bridge.states.items()}
    now = mission.time
    while now < mission.time + 120 and fire.active and now < 400:
        now += 0.5
        targets = mission.tick(now, positions, dict.fromkeys(positions, True))
        positions = {key: fly(value, targets[key], 0.5) for key, value in positions.items()}
    assert not fire.active and fire.contributors


def test_homes_are_unique_and_decisions_serialize():
    assert len(set(fleet_homes(8).values())) == 8
    json.dumps(rehearse(3, limit=40).log.rows)
    assert VehicleState("E01", (0, 0, 0), (0, 0, 0)).healthy


def test_visual_scale_never_touches_physics():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics

    from embernet.isaac.native_airframe import IRIS_MODEL, create_airframe

    stage = Usd.Stage.CreateInMemory()
    root = create_airframe(stage, "/World/E01/body", (0, 0, 1), model_path=IRIS_MODEL, visual_scale=3.0)
    cache = UsdGeom.XformCache(0)

    def scale(prim):
        return cache.GetLocalToWorldTransform(prim).GetRow3(0).GetLength()

    assert scale(stage.GetPrimAtPath("/World/E01/body/Shell")) == pytest.approx(3.0)
    assert scale(root.GetPrim()) == pytest.approx(1.0)
    assert UsdPhysics.MassAPI(root.GetPrim()).GetMassAttr().Get() == pytest.approx(1.5)
    assert scale(stage.GetPrimAtPath("/World/E01/body/BodyCollision")) == pytest.approx(0.35)


def test_context_pruning_keeps_near_buildings_and_marks_the_rest_inactive():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom

    from embernet.isaac.authored_city import prune_context

    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World/Blocks")
    for name, x in (("Near", 100), ("Far", 900)):
        cube = UsdGeom.Cube.Define(stage, f"/World/Blocks/{name}/Box")
        cube.AddTranslateOp().Set((x, 0, 0))
    result = prune_context(stage, (0, 0), 600, "/World/Blocks")
    assert result == {"kept": 1, "removed": 1, "radius_m": 600}
    assert stage.GetPrimAtPath("/World/Blocks/Near").IsActive()
    assert not stage.GetPrimAtPath("/World/Blocks/Far").IsActive()


def test_world_is_chosen_at_launch_and_validated():
    import hashlib

    from fastapi.testclient import TestClient

    from embernet.cloud_gateway import create_gateway

    registry = {
        "config": {"control_hash": hashlib.sha256(b"code").hexdigest(), "world": "city"},
        "ticket": {"valid_until": 9e12},
    }
    launched = []

    def launch(config, ticket):
        launched.append(config["world"])
        return {"run_id": "live-x", "expires_at": 9e12}

    client = TestClient(create_gateway(registry, launch, lambda active: False))
    headers = {"Authorization": "Bearer code"}
    assert client.post("/api/start?world=moon", headers=headers).status_code == 422
    assert "ticket" in registry, "a rejected world must not consume the voucher"
    assert client.post("/api/start?world=wildland", headers=headers).status_code == 200
    assert launched == ["wildland"]


def test_holds_use_the_active_world_obstacles_not_the_city():
    open_world = SwarmMission(6, obstacles=())
    state, agent = open_world.bridge.states["E01"], open_world.bridge.agents["E01"]
    incident = agent.memory.observe(Detection("fire", (150, 134, 7), 6, 0.9, 0.9, 1, "E01"), "E01")
    state.position = (150, 100, 60)
    goal = open_world._goal("E01", Command(Task.RESPOND, (150, 134, 66), incident.id))
    assert goal[2] < 60

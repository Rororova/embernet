from pathlib import Path

import numpy as np
import pytest

from embernet.isaac.wildland_terrain import (
    HOME,
    IGNITION,
    WILDLAND_SIZE,
    burn_mask,
    forest_density,
    grid_axis,
    ground_masks,
    meadow_mask,
    place_grass,
    place_trees,
    place_understory,
    road_distance,
    terrain_height,
    terrain_normal,
)


def test_terrain_is_deterministic_with_real_relief_and_a_level_pad():
    axis = np.linspace(0, WILDLAND_SIZE, 240)
    x, y = np.meshgrid(axis, axis)
    height = terrain_height(x, y)
    assert np.isfinite(height).all()
    assert np.array_equal(height, terrain_height(x, y))
    assert height.max() - height.min() > 60
    angle = np.linspace(0, 2 * np.pi, 32)
    ring = terrain_height(HOME[0] + 25 * np.cos(angle), HOME[1] + 25 * np.sin(angle))
    assert np.ptp(ring) < 0.2
    assert terrain_normal(*HOME)[2] > 0.999


def test_visual_terrain_axis_is_monotonic_and_contains_the_mission_square():
    axis = grid_axis()
    assert (np.diff(axis) > 0).all()
    assert axis[0] < -800 and axis[-1] > WILDLAND_SIZE + 800
    assert np.count_nonzero((axis >= 0) & (axis <= WILDLAND_SIZE)) == 321


def test_masks_separate_meadow_road_and_burn():
    masks = ground_masks(128)
    assert masks.min() >= 0 and masks.max() <= 1
    assert all(masks[..., channel].max() > 0.5 for channel in range(4))
    assert meadow_mask(*HOME[:2]) > 0.9
    assert road_distance(*HOME) < 12
    assert burn_mask(IGNITION[0] + 14, IGNITION[1] + 12) > 0.9
    assert burn_mask(*HOME) == 0


def test_plants_stay_on_the_ground_and_off_the_pad_and_road():
    trees = place_trees()
    assert 5000 < trees["x"].size < 140000
    assert set(np.unique(trees["species"])) == set(range(7))
    assert np.abs(trees["z"] - terrain_height(trees["x"], trees["y"])).max() < 0.31
    assert np.hypot(trees["x"] - HOME[0], trees["y"] - HOME[1]).min() > 34
    assert road_distance(trees["x"], trees["y"]).min() > 8
    assert forest_density(*HOME) == 0
    understory = place_understory()
    assert road_distance(understory["x"], understory["y"]).min() > 6
    grass = place_grass()
    assert 5000 < grass["x"].size < 500000


def test_wildland_stage_composes_with_vegetation_in_metres(tmp_path):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics

    from embernet.isaac.wildland_scene import build_wildland

    root = Path("artifacts/embernet/isaac/nvidia-wildland")
    if not (root / "Vegetation/Trees/Douglas_Fir.usd").is_file():
        pytest.skip("NVIDIA vegetation is fetched separately, not redistributed in the project")
    stage = Usd.Stage.CreateInMemory()
    report = build_wildland(stage, root, tmp_path)
    assert not stage.GetCompositionErrors()
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    trees = UsdGeom.PointInstancer(stage.GetPrimAtPath("/World/Wildland/Trees"))
    assert len(trees.GetPositionsAttr().Get()) == report["trees"]
    assert max(trees.GetProtoIndicesAttr().Get()) == 6
    cache = UsdGeom.BBoxCache(0, ["default", "render"])
    oak = cache.ComputeWorldBound(stage.GetPrimAtPath("/World/Wildland/Trees/Prototypes/P05"))
    assert oak.ComputeAlignedRange().GetSize()[2] == pytest.approx(16, abs=1)
    assert stage.GetPrimAtPath("/World/Wildland/TerrainCollision").HasAPI(UsdPhysics.CollisionAPI)
    assert (tmp_path / "wildland-ground/ground-mask.png").is_file()


def test_live_scenario_keeps_every_lane_above_ground_and_canopy():
    from embernet.isaac.wildland_live import WILDLAND_VIEWS, scenario
    from embernet.isaac.wildland_scene import TREES
    from embernet.isaac.wildland_terrain import MISSION_RELIEF, MISSION_SIZE, mission_ground
    from embernet.swarm_mission import SwarmMission, fleet_homes

    axis = np.linspace(0, MISSION_SIZE, 49)
    relief = [mission_ground(x, y) for x in axis for y in axis]
    assert max(relief) <= MISSION_RELIEF + 0.1
    tallest = max(row[2] for row in TREES) * 1.45
    swarm = SwarmMission(6, sink=None, **scenario())
    assert min(agent.altitude for agent in swarm.bridge.agents.values()) > MISSION_RELIEF + 25
    assert tallest < 40
    assert all(abs(mission_ground(*home[:2])) < 0.01 for home in fleet_homes(8).values())
    world = swarm.world.records()
    assert all(fire["position"][2] == pytest.approx(mission_ground(*fire["position"][:2]) + 1) for fire in world["fires"])
    assert swarm.sensor.scan("E01", (150.0, 110.0, 66.0), 0.0)[0]
    assert set(WILDLAND_VIEWS) == {"bird", "overview", "fire"}


def test_only_the_wildland_world_raises_px4_limits():
    from embernet.isaac.px4_bridge import airframe_script
    from embernet.isaac.wildland_live import CRUISE_SPEED, PX4_LIMITS, scenario

    assert "MPC_XY_VEL_MAX 8\n" in airframe_script()
    assert "MPC_XY_VEL_MAX 80.0\n" in airframe_script(PX4_LIMITS)
    assert PX4_LIMITS["MPC_TILTMAX_AIR"] < PX4_LIMITS["FD_FAIL_P"]
    assert scenario()["speed"] == CRUISE_SPEED == 80

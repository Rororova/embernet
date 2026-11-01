from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from embernet.contracts import Command, Config, Task
from embernet.isaac.bridge import PhysicsMission
from embernet.isaac.cameras import thermal_frame
from embernet.isaac.city_live import mesh_view
from embernet.isaac.city_scene import CITY_SIZE, FIRE_FLOOR, FIRE_POSITION
from embernet.isaac.native_airframe import stl_mesh
from embernet.live_api import FRAME_IR, FRAME_RGB, LiveCommand, pack_frame
from embernet.routing import standoff
from embernet.safety import SafetySupervisor


def test_city_scenario_has_a_large_map_and_thirtieth_floor_fire():
    assert CITY_SIZE == 240
    assert FIRE_FLOOR == 30
    assert 100 < FIRE_POSITION[2] < 110
    for index in range(8):
        target = standoff(FIRE_POSITION, index)
        assert target[1] < FIRE_POSITION[1]
        assert 0 <= target[2] <= 140


def test_synthetic_ir_is_sensor_styled_and_explicitly_not_radiometric():
    rgb = np.zeros((64, 64, 3), dtype=np.uint8)
    rgb[20:44, 20:44] = (255, 80, 5)
    image, metadata = thermal_frame(rgb, seed=41)
    assert image.size == (640, 360)
    assert metadata["radiometric"] is False
    assert metadata["estimated_hot_color_max_c"] > 100
    assert np.asarray(image).max() > 200


def test_dual_sensor_frames_are_prefixed_and_validated():
    jpeg = b"\xff\xd8" + b"payload"
    assert pack_frame(FRAME_RGB, jpeg) == b"\x00" + jpeg
    assert pack_frame(FRAME_IR, jpeg) == b"\x01" + jpeg
    with pytest.raises(ValueError, match="Invalid sensor frame"):
        pack_frame(FRAME_RGB, b"not-jpeg")


def test_city_camera_and_altitude_commands_are_bounded():
    for mode in ("mission", "follow", "onboard", "bird", "overview", "fire"):
        assert LiveCommand(action="camera", camera=mode).camera == mode
    assert LiveCommand(action="incident", z=104.4).z == 104.4
    with pytest.raises(ValidationError):
        LiveCommand(action="camera", camera="invalid")
    with pytest.raises(ValidationError):
        LiveCommand(action="incident", z=150)


def test_mesh_view_shows_queue_and_partition_reaction():
    config = Config(drones=3, size=240, ceiling=140, radio_range=190)
    homes = {"E01": (45, 30, 0.45), "E02": (60, 30, 0.45), "E03": (75, 30, 0.45)}
    mission = PhysicsMission(config, homes)
    for key, position in homes.items():
        mission.telemetry(key, position=position, stamp=0)
    view = mesh_view(mission)
    assert len(view["links"]) == 3 and all(link["active"] for link in view["links"])
    mission.set_connection("E02", False)
    view = mesh_view(mission)
    assert view["isolated"] == ["E02"]
    assert [link["active"] for link in view["links"]] == [False, True, False]


def test_city_ceiling_remains_independently_checked():
    config = Config(drones=3, size=240, ceiling=140)
    mission = PhysicsMission(config, {"E01": (45, 30, 0.45), "E02": (60, 30, 0.45), "E03": (75, 30, 0.45)})
    state = mission.states["E01"]
    state.healthy, state.stamp = True, 1
    assert SafetySupervisor(config).check(state, Command(Task.SEARCH, (150, 134, 112)), 1).allowed
    assert not SafetySupervisor(config).check(state, Command(Task.SEARCH, (150, 134, 141)), 1).allowed


@pytest.mark.skipif(
    not Path("artifacts/embernet/isaac/assets/px4-iris/iris.stl").is_file(),
    reason="Iris visual asset is not installed",
)
def test_iris_stl_is_detailed_finite_geometry():
    points, normals = stl_mesh("artifacts/embernet/isaac/assets/px4-iris/iris.stl")
    assert len(points) == 79996 * 3
    assert normals.shape == points.shape
    assert 0.4 < np.ptp(points[:, 1]) < 0.6

import numpy as np
import pytest

from embernet.contracts import Config, Detection, Task
from embernet.isaac.bridge import PhysicsMission, enu_to_ned
from embernet.isaac.controller import GeometricController
from embernet.isaac.projection import optical_pose_from_usd, project_depth_pixel


def mission():
    return PhysicsMission(Config(drones=2), {"E01": (20, 15, 0), "E02": (60, 15, 0)})


def test_planning_never_teleports_physics_and_stale_state_holds():
    loop = mission()
    loop.telemetry("E01", position=(20, 15, 8), stamp=0)
    before = loop.states["E01"].position
    loop.tick(0.5)
    assert loop.states["E01"].position == before
    result = loop.tick(3)
    assert result["E01"].task == Task.HOLD
    assert loop.states["E01"].stamp == 0


def test_local_observations_require_true_source_and_original_time():
    loop = mission()
    loop.tick(1)
    detection = Detection("fire", (30, 30, 0), 2, 0.5, 0.9, 1, "E01")
    loop.observe("E01", [detection])
    assert len(loop.agents["E01"].memory.incidents) == 1
    assert not loop.agents["E02"].memory.incidents
    with pytest.raises(ValueError):
        loop.observe("E02", [detection])


def test_hover_balances_gravity_and_position_error_commands_tilt():
    controller = GeometricController()
    thrust, torque = controller.wrench([0, 0, 2], [0, 0, 0], [0, 0, 0, 1], [0, 0, 0], [0, 0, 2])
    assert thrust == pytest.approx(1.5 * 9.81)
    np.testing.assert_allclose(torque, 0)
    _, torque = controller.wrench([0, 0, 2], [0, 0, 0], [0, 0, 0, 1], [0, 0, 0], [2, 0, 2])
    assert torque[1] > 0
    with pytest.raises(ValueError):
        controller.wrench([0, 0, 2], [0, 0, 0], [0, 0, 0, 0], [0, 0, 0], [2, 0, 2])


def test_enu_ned_round_trip_and_camera_depth_units():
    assert enu_to_ned(enu_to_ned((2, 3, 4))) == (2, 3, 4)
    camera = np.eye(4)
    camera[2, 3] = 10
    optical = optical_pose_from_usd(camera)
    k = [[100, 0, 50], [0, 100, 50], [0, 0, 1]]
    np.testing.assert_allclose(project_depth_pixel((50, 50), 10, k, optical), [0, 0, 0])
    np.testing.assert_allclose(project_depth_pixel((60, 50), 10, k, optical), [1, 0, 0])


def test_rotor_allocation_reconstructs_hover_and_body_moments():
    from embernet.isaac.rotors import RotorAllocator

    allocator = RotorAllocator()
    motors, actual = allocator.allocate(14.715, [0.1, -0.08, 0.02])
    np.testing.assert_allclose(actual, [14.715, 0.1, -0.08, 0.02], atol=1e-9)
    assert np.all((motors > 0) & (motors < 1100))
    motors, actual = allocator.allocate(1000, [0, 0, 0])
    assert np.max(motors) <= 1100
    assert actual[0] < 1000


def test_physics_bridge_radio_fault_blocks_queued_packets_and_reconnects():
    from embernet.contracts import Message

    loop = mission()
    loop.mesh.loss = 0
    loop.mesh.send("E01", Message("queued", "E01", "STATUS", {}, 0), 0, loop.states)
    loop.set_connection("E02", False)
    assert "E02" in loop.mesh.isolated and not loop.states["E02"].connected
    assert not loop.mesh.deliver(2, loop.states)["E02"]
    loop.set_connection("E02", True)
    loop.mesh.send("E01", Message("restored", "E01", "STATUS", {}, 2), 2, loop.states)
    assert [m.id for m in loop.mesh.deliver(4, loop.states)["E02"]] == ["restored"]

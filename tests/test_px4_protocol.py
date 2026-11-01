import numpy as np
import pytest

from embernet.isaac.px4_bridge import ENU_NED, FLU_FRD, airframe_script, sensor_values
from embernet.isaac.rotors import RotorAllocator


def test_sensor_axes_gravity_gps_and_pressure_at_rest():
    values = sensor_values(np.zeros(3), np.array([2, 3, 4]), np.zeros(3), [0, 0, 0, 1], np.array([1, 2, 3]))
    np.testing.assert_allclose(values["accel_frd"], [0, 0, -9.80665])
    np.testing.assert_allclose(values["gyro_frd"], [1, -2, -3])
    np.testing.assert_allclose(values["velocity_ned"], [3, 2, -4])
    np.testing.assert_allclose(values["mag_frd"], [0.007, -0.21523, 0.42741])
    assert values["latitude"] == pytest.approx(47.397742)
    assert 950 < values["pressure_hpa"] < 960
    higher = sensor_values(np.array([10, 20, 50]), np.zeros(3), np.zeros(3), [0, 0, 0, 1], np.zeros(3))
    assert higher["latitude"] > values["latitude"] and higher["longitude"] > values["longitude"]
    assert higher["pressure_hpa"] < values["pressure_hpa"]


def test_simulator_motor_geometry_matches_px4_frd_axes():
    rotor = RotorAllocator()
    forces = np.array([4.0, 3.0, 2.0, 1.0])
    wrench = rotor.matrix @ forces
    frd_positions = rotor.locations @ FLU_FRD
    torque_frd = sum(np.cross(p, [0, 0, -f]) for p, f in zip(frd_positions, forces))
    np.testing.assert_allclose(torque_frd[:2], (FLU_FRD @ wrench[1:])[:2], atol=1e-12)
    script = airframe_script()
    params = {
        line.split()[2]: float(line.split()[3])
        for line in script.splitlines()
        if line.startswith("param set-default")
    }
    px4_torque = np.zeros(3)
    for i, (p, f) in enumerate(zip(frd_positions, forces)):
        axis = np.array([0.0, 0.0, -1.0])
        px4_torque += f * (np.cross(p, axis) - params[f"CA_ROTOR{i}_KM"] * axis)
    np.testing.assert_allclose(px4_torque, FLU_FRD @ wrench[1:], atol=1e-12)
    assert "CA_ROTOR_COUNT 4" in script and "CA_ROTOR0_PY -0.22" in script
    assert "ARMING_CHECK" not in script and "CBRK" not in script
    np.testing.assert_allclose(ENU_NED @ ENU_NED, np.eye(3))

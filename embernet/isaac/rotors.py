"""Four-rotor allocation in FLU; an explicit research airframe, not hardware calibration."""

import numpy as np


class RotorAllocator:
    def __init__(self, arm=0.22, yaw_ratio=0.016, thrust_constant=8.54858e-6, max_speed=1100):
        self.locations = np.array([[arm, arm, 0], [-arm, arm, 0], [-arm, -arm, 0], [arm, -arm, 0]])
        self.thrust_constant, self.max_speed = thrust_constant, max_speed
        self.matrix = np.vstack(
            (np.ones(4), self.locations[:, 1], -self.locations[:, 0], np.array([1, -1, 1, -1]) * yaw_ratio)
        )
        self.inverse = np.linalg.inv(self.matrix)

    def allocate(self, thrust, torque):
        requested = np.array([thrust, *torque], float)
        if requested.shape != (4,) or not np.isfinite(requested).all():
            raise ValueError("Invalid requested wrench")
        rotor_thrust = np.clip(self.inverse @ requested, 0, self.thrust_constant * self.max_speed**2)
        actual = self.matrix @ rotor_thrust
        return np.sqrt(rotor_thrust / self.thrust_constant), actual

"""Geometric position/attitude controller for a simulation-only Pegasus backend."""

import numpy as np


def rotation_xyzw(quaternion):
    q = np.asarray(quaternion, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-8:
        raise ValueError("Invalid orientation")
    x, y, z, w = q / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


class GeometricController:
    def __init__(self, mass=1.5, inertia=(0.029125, 0.029125, 0.055225), max_speed=5.0):
        if mass <= 0 or max_speed <= 0:
            raise ValueError("Invalid airframe limits")
        self.mass = float(mass)
        self.inertia = np.diag(inertia)
        self.max_speed = float(max_speed)

    def wrench(self, position, velocity, quaternion, angular_velocity, target):
        vectors = [np.asarray(v, dtype=float) for v in (position, velocity, angular_velocity, target)]
        if any(v.shape != (3,) or not np.isfinite(v).all() for v in vectors):
            raise ValueError("Invalid controller state")
        position, velocity, omega, target = vectors
        rotation = rotation_xyzw(quaternion)
        desired_velocity = np.clip(1.4 * (target - position), -self.max_speed, self.max_speed)
        acceleration = 2.8 * (desired_velocity - velocity)
        acceleration[:2] = np.clip(acceleration[:2], -4.0, 4.0)
        acceleration[2] = np.clip(acceleration[2], -5.0, 7.0)
        force = self.mass * (acceleration + np.array([0.0, 0.0, 9.81]))
        z = force / np.linalg.norm(force)
        heading = np.array([1.0, 0.0, 0.0])
        y = np.cross(z, heading)
        y /= np.linalg.norm(y)
        x = np.cross(y, z)
        desired = np.column_stack((x, y, z))
        error_matrix = (desired.T @ rotation - rotation.T @ desired) * 0.5
        error = np.array([error_matrix[2, 1], error_matrix[0, 2], error_matrix[1, 0]])
        torque = (
            -np.array([3.0, 3.0, 1.0]) * error
            - np.array([0.35, 0.35, 0.15]) * omega
            + np.cross(omega, self.inertia @ omega)
        )
        thrust = float(np.clip(force @ rotation[:, 2], 0.0, 2.5 * self.mass * 9.81))
        return thrust, torque

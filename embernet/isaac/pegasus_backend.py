"""Simulation-only rotor backend; it cannot open a hardware connection."""

import numpy as np
from pegasus.simulator.logic.backends.backend import Backend, BackendConfig

from .controller import GeometricController


class RotorWaypointBackend(Backend):
    def __init__(self, target=(0, 0, 3)):
        super().__init__(BackendConfig())
        self.controller = GeometricController()
        self.target = np.asarray(target, float)
        self.state = None
        self.rotors = np.zeros(4)
        self.running = False

    def update_state(self, state):
        self.state = state

    def update_sensor(self, sensor_type, data):
        pass

    def update_graphical_sensor(self, sensor_type, data):
        pass

    def input_reference(self):
        return self.rotors.tolist()

    def update(self, dt):
        if not self.running or self.state is None:
            self.rotors[:] = 0
            return
        state = self.state
        thrust, torque = self.controller.wrench(
            state.position, state.linear_velocity, state.attitude, state.angular_velocity, self.target
        )
        self.rotors = self.vehicle.force_and_torques_to_velocities(thrust, torque)
        if not np.isfinite(self.rotors).all():
            raise RuntimeError("Nonfinite motor command")

    def start(self):
        self.running = True

    def stop(self):
        self.running = False
        self.rotors[:] = 0

    def reset(self):
        self.state = None
        self.rotors[:] = 0

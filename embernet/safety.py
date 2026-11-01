"""Independent command validation. Does not import policy, memory, or simulator truth."""

from dataclasses import dataclass, replace
from math import dist, isfinite

from .contracts import Command, Config, Task, VehicleState


@dataclass(frozen=True)
class SafetyDecision:
    command: Command
    allowed: bool
    reason: str


class SafetySupervisor:
    def __init__(self, config: Config):
        self.c = config

    def reserve(self, state: VehicleState) -> float:
        return dist(state.position, state.home) / self.c.speed / self.c.battery_seconds + 0.09

    def check(
        self,
        state: VehicleState,
        command: Command,
        now: float,
        *,
        physical=False,
        human_authorized=False,
        independent_interlock=False,
    ) -> SafetyDecision:
        def reject(reason, return_home=False):
            fallback = Command(
                Task.RETURN if return_home else Task.HOLD,
                state.home if return_home else state.position,
                reason=reason,
            )
            return SafetyDecision(fallback, False, reason)

        if len(command.target) != 3 or not all(isfinite(v) for v in command.target):
            return reject("Rejected non-finite navigation target")
        if not state.healthy or now - state.stamp > 2.0 or state.stamp > now:
            return reject("Hold: unhealthy vehicle or stale telemetry")
        x, y, z = command.target
        if not (0 <= x <= self.c.size and 0 <= y <= self.c.size and 0 <= z <= self.c.ceiling):
            return reject("Hold: target outside mission boundary")
        if command.task not in (Task.RETURN, Task.HOLD) and state.battery <= self.reserve(state):
            return reject("Return: protected energy reserve", True)
        trip = dist(state.position, command.target) + dist(command.target, state.home)
        if (
            command.task not in (Task.RETURN, Task.HOLD)
            and trip / self.c.speed / self.c.battery_seconds + 0.07 >= state.battery
        ):
            return reject("Return: insufficient energy for outbound trip and recovery", True)
        if command.release:
            if state.water <= 0 or command.task != Task.RESPOND or dist(state.position, command.target) > 5.0:
                return reject("Hold: payload target or resources invalid")
            if physical and not (human_authorized and independent_interlock):
                return reject("Physical discharge requires human authorization and independent interlock")
        return SafetyDecision(replace(command), True, "Command accepted")


class SimulatedFlight:
    """Kinematic reference adapter; no rotor dynamics and no physical connection."""

    simulated = True

    def __init__(self, config: Config):
        self.c = config

    def execute(self, state: VehicleState, command: Command, dt: float) -> VehicleState:
        distance = dist(state.position, command.target)
        travel = min(distance, self.c.speed * dt)
        ratio = travel / distance if distance else 0.0
        state.position = tuple(a + (b - a) * ratio for a, b in zip(state.position, command.target))
        state.task, state.target = command.task, command.target
        state.incident_id, state.reason = command.incident_id, command.reason
        landed = command.task == Task.RETURN and dist(state.position, state.home) < 1.0
        state.battery = max(0.0, state.battery - dt / self.c.battery_seconds * (0.15 if landed else 1.0))
        state.stamp += dt
        return state


class PX4Adapter:
    """Reserved integration boundary, deliberately incapable of sending commands."""

    simulated = False

    def execute(self, state: VehicleState, command: Command, dt: float) -> VehicleState:
        raise NotImplementedError("PX4 SITL integration is not implemented; use SimulatedFlight")

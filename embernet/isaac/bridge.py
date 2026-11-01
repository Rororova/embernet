"""Mission decisions from measured states; this module never advances vehicle poses."""

from dataclasses import replace
from math import isfinite

from ..contracts import Config, Detection, VehicleState
from ..coordination import Agent
from ..mesh import Mesh
from ..safety import SafetySupervisor


class PhysicsMission:
    """Reuse local ledgers/protocol/policy with external physics observations."""

    def __init__(self, config: Config, homes: dict, policy=None):
        if len(homes) != config.drones:
            raise ValueError("One home is required per aircraft")
        self.c, self.time, self.policy = config, 0.0, policy
        self.states = {
            key: VehicleState(
                key, tuple(home), tuple(home), water=config.max_water, healthy=False, stamp=-10.0
            )
            for key, home in homes.items()
        }
        self.agents = {key: Agent(key, index, config) for index, key in enumerate(sorted(homes))}
        self.mesh, self.safety = Mesh(config), SafetySupervisor(config)
        self.events = []
        self.new_events = []
        self.last_deliveries = {key: [] for key in homes}

    def set_connection(self, key, connected):
        if key not in self.states:
            raise ValueError("Unknown aircraft")
        self.states[key].connected = bool(connected)
        if connected:
            self.mesh.isolated.discard(key)
        else:
            self.mesh.isolated.add(key)

    def telemetry(self, key, *, position, stamp, battery=1.0, water=None, healthy=True):
        if key not in self.states:
            raise ValueError("Unknown aircraft")
        if len(position) != 3 or not all(isfinite(float(x)) for x in (*position, stamp, battery)):
            raise ValueError("Nonfinite measured state")
        if stamp < self.states[key].stamp:
            raise ValueError("Out-of-order measured state")
        if not 0 <= battery <= 1 or (water is not None and not 0 <= water <= self.c.max_water):
            raise ValueError("Invalid resources")
        state = self.states[key]
        state.position = tuple(float(x) for x in position)
        state.stamp, state.battery, state.healthy = float(stamp), float(battery), bool(healthy)
        if water is not None:
            state.water = float(water)

    def observe(self, key, detections: list[Detection]):
        if key not in self.agents:
            raise ValueError("Unknown aircraft")
        for detection in detections:
            if detection.source != key or not 0 <= self.time - detection.observed_at <= 2:
                raise ValueError("Observation source/time mismatch")
            if not all(
                isfinite(float(v))
                for v in (*detection.position, detection.extent, detection.confidence, detection.severity)
            ):
                raise ValueError("Nonfinite observation")
            if (
                not 0 <= detection.confidence <= 1
                or not 0 <= detection.severity <= 1
                or detection.extent <= 0
            ):
                raise ValueError("Invalid observation evidence")
            self.agents[key].memory.observe(detection, key)

    def tick(self, now):
        if not isfinite(now) or now < self.time:
            raise ValueError("Mission clock must be monotonic")
        self.time = float(now)
        inboxes = self.mesh.deliver(self.time, self.states)
        self.last_deliveries = {
            key: [
                {
                    "id": m.id,
                    "origin": m.origin,
                    "kind": m.kind,
                    "incident": m.payload.get("incident_id", m.payload.get("id")),
                }
                for m in messages
            ]
            for key, messages in inboxes.items()
        }
        for key, agent in self.agents.items():
            agent.receive(inboxes[key], self.time)
        selected = self.policy.actions(self) if self.policy else {}
        commands = {}
        for key, agent in self.agents.items():
            state = self.states[key]
            command = agent.plan(state, self.time, selected.get(key))
            checked = self.safety.check(state, command, self.time)
            command = checked.command
            # Payload is a scenario effect. Never send physical release through this bridge.
            command = replace(command, release=False)
            state.task, state.target, state.incident_id, state.reason = (
                command.task,
                command.target,
                command.incident_id,
                command.reason,
            )
            commands[key] = command
        for key, agent in self.agents.items():
            for message in agent.outbox:
                self.mesh.send(key, message, self.time, self.states)
            agent.outbox = []
            self.events.extend(agent.events)
            self.new_events.extend(agent.events)
            agent.events = []
        self.events = self.events[-400:]
        return commands


def enu_to_ned(vector):
    if len(vector) != 3 or not all(isfinite(float(v)) for v in vector):
        raise ValueError("Invalid ENU vector")
    x, y, z = vector
    return (float(y), float(x), -float(z))

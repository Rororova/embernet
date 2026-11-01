"""Deterministic synthetic world. Truth generates sensors, never agent decisions."""

import random
from dataclasses import asdict, dataclass, replace
from math import dist, sqrt

import numpy as np

from .contracts import Config, Detection, Event, Task, VehicleState
from .coordination import Agent
from .mesh import Mesh
from .perception import CameraObject, render_camera
from .safety import SafetySupervisor, SimulatedFlight


@dataclass
class Fire:
    id: str
    x: float
    y: float
    initial: float
    remaining: float
    severity: float
    created_at: float
    contained_at: float | None = None

    @property
    def radius(self):
        return sqrt(max(0.01, self.remaining) / 0.38)


@dataclass
class Subject:
    id: str
    kind: str
    x: float
    y: float
    created_at: float
    responded_at: float | None = None


class Simulation:
    def __init__(self, config=None, *, vision=None, policy=None, scenario="forest"):
        self.c = config or Config()
        self.rng = random.Random(self.c.seed)
        self.time = 0.0
        self.states: dict[str, VehicleState] = {}
        self.agents: dict[str, Agent] = {}
        for k in range(self.c.drones):
            drone_id = f"E{k + 1:02}"
            home = (self.c.size * (k + 0.5) / self.c.drones, 15.0, 0.0)
            self.states[drone_id] = VehicleState(drone_id, home, home, water=self.c.max_water)
            self.agents[drone_id] = Agent(drone_id, k, self.c)
        self.mesh = Mesh(self.c)
        self.safety, self.flight = SafetySupervisor(self.c), SimulatedFlight(self.c)
        self.vision, self.policy = vision, policy
        self.sensor_mode = "learned RGB/thermal" if vision else "reference sensor (oracle)"
        self.policy_mode = "learned mission policy" if policy else "rule-based baseline"
        self.fires: list[Fire] = []
        self.subjects: list[Subject] = []
        self.events: list[Event] = []
        self.cameras = {}
        self.metrics = {
            "water_used": 0.0,
            "safety_interventions": 0,
            "replenishments": 0,
            "collisions": 0,
            "survivor_responses": 0,
            "contained": 0,
            "burned_proxy": 0.0,
        }
        self.trails = {key: [] for key in self.states}
        self.history: list[dict] = []
        self.observation_misses = {}
        self._last_sense = -10.0
        self._contacts = set()
        self._discharging = {}
        self.scenario = scenario
        if scenario != "empty":
            self.add_fire(self.c.size * 0.30, self.c.size * 0.34, 0.45, 5.0)
            self.add_fire(self.c.size * 0.69, self.c.size * 0.67, 0.85, 8.0)
            self.add_subject(self.c.size * 0.70, self.c.size * 0.66, "person")
            self.add_subject(self.c.size * 0.44, self.c.size * 0.72, "animal")

    def add_fire(self, x, y, severity=0.6, radius=5.0):
        if not (
            0 <= x <= self.c.size and 0 <= y <= self.c.size and 0.1 <= severity <= 1 and 1 <= radius <= 15
        ):
            raise ValueError("Fire position, severity or radius is outside scenario limits")
        if len(self.fires) >= 64:
            raise ValueError("Scenario incident limit reached; reset the mission")
        demand = radius * radius * 0.38 + severity * 4
        fire = Fire(f"F{len(self.fires) + 1:03}", x, y, demand, demand, severity, self.time)
        self.fires.append(fire)
        self.events.append(Event(self.time, "operator", "CONTROL", "Fire added to simulator truth", fire.id))
        return fire

    def add_subject(self, x, y, kind="person"):
        if kind not in ("person", "animal") or not (0 <= x <= self.c.size and 0 <= y <= self.c.size):
            raise ValueError("Subject kind or position is invalid")
        if len(self.subjects) >= 64:
            raise ValueError("Scenario subject limit reached")
        subject = Subject(f"S{len(self.subjects) + 1:03}", kind, x, y, self.time)
        self.subjects.append(subject)
        return subject

    def _sense(self):
        span = self.c.sensor_radius * 2
        all_objects = [
            CameraObject("fire", f.x, f.y, f.radius, f.severity) for f in self.fires if f.remaining > 0.2
        ]
        all_objects += [
            CameraObject(s.kind, s.x, s.y, 3.0 if s.kind == "person" else 3.6) for s in self.subjects
        ]
        images, centers, ids, spans = [], [], [], []
        for key, state in self.states.items():
            if state.position[2] < 8:
                continue
            footprint = 36.0 if state.task in (Task.RESPOND, Task.VERIFY) else span
            objects = [
                obj
                for obj in all_objects
                if abs(obj.x - state.position[0]) < footprint / 2 - 2
                and abs(obj.y - state.position[1]) < footprint / 2 - 2
            ]
            image, _, _ = render_camera(
                objects, state.position[:2], footprint, seed=self.c.seed + self.agents[key].index
            )
            self.cameras[key] = image
            images.append(image)
            centers.append(state.position[:2])
            ids.append(key)
            spans.append(footprint)
        if self.vision and images:
            detected = self.vision.detect_batch(images, centers, spans, self.time, ids)
        else:
            detected = []
            for key, footprint in zip(ids, spans):
                state = self.states[key]
                detections = [
                    Detection(obj.kind, (obj.x, obj.y, 0.0), obj.radius, obj.severity, 0.98, self.time, key)
                    for obj in all_objects
                    if dist(state.position[:2], (obj.x, obj.y)) < footprint / 2 - 2
                ]
                detected.append(detections)
        for key, detections, footprint in zip(ids, detected, spans):
            agent = self.agents[key]
            for detection in detections:
                old_ids = set(agent.memory.incidents)
                incident = agent.memory.observe(detection, key)
                if incident.id not in old_ids:
                    agent.event(
                        self.time,
                        "detection",
                        f"Detected {detection.kind}; confidence {detection.confidence:.0%}",
                        incident.id,
                    )
            # Clearance requires repeated fresh camera absence with the target fully in view.
            for incident in agent.memory.incidents.values():
                if incident.kind != "fire" or incident.status in ("cleared", "merged"):
                    continue
                distance = dist(self.states[key].position[:2], incident.position[:2])
                visible = distance < max(2.0, footprint / 2 - incident.extent - 3)
                present = any(
                    d.kind == "fire" and dist(d.position, incident.position) < max(13, incident.extent)
                    for d in detections
                )
                token = (key, incident.id)
                self.observation_misses[token] = (
                    self.observation_misses.get(token, 0) + 1 if visible and not present else 0
                )
                if self.observation_misses[token] >= 4:
                    incident.status, incident.observed_at = "cleared", self.time
                    agent.event(
                        self.time,
                        "clearance",
                        "Four fresh negative camera observations; incident cleared",
                        incident.id,
                    )

    def step(self, steps=1, actions=None, *, capture=False):
        for step in range(steps):
            self.time = round(self.time + self.c.dt, 6)
            for fire in self.fires:
                if fire.remaining > 0.2:
                    growth = self.c.dt * (0.008 + fire.severity * 0.018)
                    fire.remaining += growth
                    self.metrics["burned_proxy"] += growth
            inboxes = self.mesh.deliver(self.time, self.states)
            for key, agent in self.agents.items():
                agent.receive(inboxes[key], self.time)
            if self.time - self._last_sense >= 1.5:
                self._last_sense = self.time
                self._sense()
            chosen = actions
            if chosen is None and self.policy:
                chosen = self.policy.actions(self)
            commands = {}
            self._discharging = {}
            for key, agent in self.agents.items():
                state = self.states[key]
                state.stamp = self.time
                if state.servicing and dist(state.position, state.home) < 1:
                    state.water = min(self.c.max_water, state.water + self.c.dt * 2.0)
                    state.battery = min(1.0, state.battery + self.c.dt * 0.045)
                    if state.water >= self.c.max_water and state.battery >= 0.98:
                        state.servicing = False
                        self.metrics["replenishments"] += 1
                        agent.event(self.time, "service", "Replenished; resuming mission")
                command = agent.plan(state, self.time, None if chosen is None else chosen.get(key))
                check = self.safety.check(state, command, self.time)
                if not check.allowed:
                    self.metrics["safety_interventions"] += 1
                    if state.reason != check.reason:
                        agent.event(self.time, "safety", check.reason)
                    if check.command.task == Task.RETURN:
                        state.servicing = True
                commands[key] = check.command
            # Ideal local proximity sensor; fixed lane heights plus one-step lookahead.
            keys = sorted(self.states)

            def projected(key, planned=commands):
                origin, target = self.states[key].position, planned[key].target
                distance = dist(origin, target)
                ratio = min(1.0, self.c.speed * self.c.dt / distance) if distance else 0
                return tuple(a + (b - a) * ratio for a, b in zip(origin, target))

            for a_index, a in enumerate(keys):
                for b in keys[a_index + 1 :]:
                    if (
                        min(self.states[a].position[2], self.states[b].position[2]) > 4
                        and dist(projected(a), projected(b)) < 3
                    ):
                        command = commands[b]
                        hover = (*self.states[b].position[:2], self.agents[b].altitude)
                        commands[b] = replace(
                            command,
                            task=Task.HOLD,
                            target=hover,
                            release=False,
                            reason="Local proximity hold; preserving assigned altitude lane",
                        )
            for key, command in commands.items():
                state = self.flight.execute(self.states[key], command, self.c.dt)
                if command.release:
                    nearby = [
                        f
                        for f in self.fires
                        if f.remaining > 0.2 and dist((f.x, f.y), state.position[:2]) < 10
                    ]
                    if nearby:
                        fire = min(nearby, key=lambda f: dist((f.x, f.y), state.position[:2]))
                        amount = min(state.water, self.c.suppress_rate * self.c.dt, fire.remaining)
                        fire.remaining -= amount
                        state.water -= amount
                        self.metrics["water_used"] += amount
                        if amount > 0:
                            self._discharging[key] = {
                                "target": [fire.x, fire.y, 0.0],
                                "litres_per_second": amount / self.c.dt,
                            }
                        if fire.remaining <= 0.2 and fire.contained_at is None:
                            fire.contained_at = self.time
                            self.metrics["contained"] += 1
                            self.agents[key].event(
                                self.time,
                                "containment",
                                "Synthetic fire contained; checking clearance",
                                command.incident_id,
                            )
                arrived = command.task == Task.RESPOND and dist(state.position, command.target) <= 4
                if arrived:
                    for subject in self.subjects:
                        if (
                            dist((subject.x, subject.y), state.position[:2]) < 15
                            and subject.responded_at is None
                        ):
                            subject.responded_at = self.time
                            self.metrics["survivor_responses"] += int(subject.kind == "person")
                            self.agents[key].event(
                                self.time,
                                "escalation",
                                "Subject reached; ground rescue required, no physical rescue simulated",
                                command.incident_id,
                            )
                    incident = self.agents[key].memory.incidents.get(command.incident_id)
                    if incident and incident.kind != "fire":
                        incident.status = "escalated"
                self.trails[key].append(list(state.position))
                self.trails[key] = self.trails[key][-140:]
            contacts = {
                (a, b)
                for n, a in enumerate(keys)
                for b in keys[n + 1 :]
                if min(self.states[a].position[2], self.states[b].position[2]) > 4
                and dist(self.states[a].position, self.states[b].position) < 1.5
            }
            self.metrics["collisions"] += len(contacts - self._contacts)
            for a, b in contacts - self._contacts:
                self.events.append(
                    Event(self.time, "contact", "WORLD", f"Simulated proximity violation: {a} / {b}")
                )
            self._contacts = contacts
            for key, agent in self.agents.items():
                for message in agent.outbox:
                    self.mesh.send(key, message, self.time, self.states)
                agent.outbox = []
                self.events.extend(agent.events)
                agent.events = []
            self.events = self.events[-400:]
            if capture and step == steps - 1:
                self.history.append(self.snapshot())
        return self.metrics

    def central_state(self):
        fires = [f for f in self.fires if f.remaining > 0.2]
        return np.asarray(
            [
                len(fires) / 10,
                sum(f.remaining for f in fires) / 200,
                np.mean([s.battery for s in self.states.values()]),
                np.mean([s.water for s in self.states.values()]) / self.c.max_water,
                self.time / self.c.horizon,
                self.metrics["contained"] / 10,
                self.metrics["survivor_responses"] / 5,
                self.mesh.loss,
                float(self.mesh.enabled),
                len(self.subjects) / 10,
                self.metrics["water_used"] / 200,
                self.metrics["safety_interventions"] / 100,
            ],
            dtype=np.float32,
        )

    def snapshot(self):
        return {
            "time": round(self.time, 2),
            "seed": self.c.seed,
            "config": asdict(self.c),
            "sensor_mode": self.sensor_mode,
            "policy_mode": self.policy_mode,
            "drones": [
                {
                    **asdict(state),
                    "discharge": self._discharging.get(key),
                    "trails": self.trails[key],
                    "incidents": self.agents[key].memory.records(),
                    "commitments": [
                        asdict(c)
                        for c in self.agents[key].memory.commitments.values()
                        if c.expires_at > self.time
                    ],
                    "peer_count": sum(
                        self.time - p.stamp < self.c.peer_ttl for p in self.agents[key].memory.peers.values()
                    ),
                }
                for key, state in self.states.items()
            ],
            "truth": {
                "fires": [{**asdict(f), "radius": f.radius} for f in self.fires],
                "subjects": [asdict(s) for s in self.subjects],
            },
            "mesh": {
                "enabled": self.mesh.enabled,
                "loss": self.mesh.loss,
                "isolated": sorted(self.mesh.isolated),
                "links": self.mesh.links(self.states),
                "stats": asdict(self.mesh.stats),
                "traffic": self.mesh.traffic[-12:],
            },
            "metrics": {key: round(value, 3) for key, value in self.metrics.items()},
            "events": [e.to_dict() for e in self.events[-50:]],
        }

"""One observable mission: world truth -> sensors -> ledgers -> mesh -> flight -> virtual work."""

import json
from dataclasses import asdict, replace
from math import dist

from .contracts import Command, Config, Task
from .isaac.bridge import PhysicsMission
from .mission_world import SENSOR_LABEL, ScenarioWorld, SimulatedSensor
from .routing import ARRIVAL_RADIUS, CITY_OBSTACLES, clearance, route, standoff

FIRE_POSITION = (150.0, 134.0, 104.4)
SMALL_FIRE_POSITION = (162.0, 106.0, 1.0)
SURVIVOR_POSITION = (172.0, 132.0, 98.0)
DRONE_COLORS = ("#ff7a2f", "#27d3ff", "#ffe14d", "#7dff6b", "#ff5fd2", "#b79bff", "#ffffff", "#ffb3a7")
TICK_SECONDS = 0.5
SURVIVOR_AT_FRACTION = 0.42
PARTITION_DELAY = 3.0
PARTITION_SECONDS = 24.0
RECONCILE_SECONDS = 4.0
CLEARANCE_REACH = 70.0
CLEARANCE_MISSES = 4
PROXIMITY_HOLD = 7.0


def fleet_config(drones):
    # Capacity units and rates are scenario parameters, not payload physics.
    return Config(
        drones=drones,
        size=240,
        altitude=66,
        ceiling=140,
        speed=8,
        radio_range=190,
        max_water=10,
        suppress_rate=0.25,
        report_ttl=35,
    )


def fleet_homes(drones):
    return {f"E{i + 1:02}": (45.0 + 15.0 * (i % 6), 30.0 - 15.0 * (i // 6), 0.45) for i in range(drones)}


def large_fire_extent(drones, capacity):
    """Sized so all but one responder cannot cover the first report, whatever the fleet."""
    return (((drones - 0.42) * capacity / 1.1 - 3.6) / 0.38) ** 0.5


class DecisionLog:
    def __init__(self, sink=None):
        self.sink, self.rows = sink, []

    def write(self, time, kind, drone, text, incident=None, **details):
        row = {
            "time": round(float(time), 2),
            "kind": kind,
            "drone": drone,
            "text": text,
            "incident": incident,
            **details,
        }
        self.rows.append(row)
        if self.sink:
            self.sink.write(json.dumps(row) + "\n")
            self.sink.flush()
        return row


class SwarmMission:
    def __init__(
        self, drones=6, *, policy=None, sink=None, seed=41, script=True, obstacles=CITY_OBSTACLES,
        fire_position=FIRE_POSITION, small_fire_position=SMALL_FIRE_POSITION,
        survivor_position=SURVIVOR_POSITION, speed=None,
    ):
        base = fleet_config(drones)
        self.c = replace(base, seed=seed, speed=speed or base.speed)
        self.homes = fleet_homes(drones)
        self.ids = sorted(self.homes)
        self.bridge = PhysicsMission(self.c, self.homes, policy)
        self.policy_name = "learned" if policy else "rule-based baseline"
        self.world = ScenarioWorld(obstacles)
        self.sensor = SimulatedSensor(self.world, seed)
        self.log = DecisionLog(sink)
        self.obstacles = obstacles
        self.survivor_position = survivor_position
        self.script = script
        self.time = 0.0
        self.flight_targets = {key: (*self.homes[key][:2], self.bridge.agents[key].altitude) for key in self.ids}
        self.goals = dict(self.flight_targets)
        self.launched = dict.fromkeys(self.ids, False)
        self.seen = {key: {} for key in self.ids}
        self.known = {key: set() for key in self.ids}
        self.misses = {}
        self.working = {}
        self.minimum_separation = 1e9
        self.minimum_clearance = 1e9
        self.partition = None
        self.partition_done = False
        self.diverted_at = None
        self.capacity_dropped = False
        self.reconciling = None
        self.completed_at = None
        self.large_fire = self.small_fire = self.subject = None
        self.last_sense = -10.0
        self.used_capacity = dict.fromkeys(self.ids, 0.0)
        if script:
            extent = large_fire_extent(drones, self.c.max_water)
            self.large_fire = self.world.add_fire(fire_position, extent, 0.9).id
            self.small_fire = self.world.add_fire(small_fire_position, 2.0, 0.3).id
            self.log.write(
                0, "scenario", "WORLD", "Fires placed in world truth; no aircraft knows of them", None,
                fires=[self.large_fire, self.small_fire],
            )

    # Scenario and operator controls edit world truth or the radio, never a ledger.
    def add_fire(self, position, extent, severity, now):
        fire = self.world.add_fire(position, extent, severity, now)
        self.log.write(now, "scenario", "OPERATOR", f"Scenario fire {fire.id} added to the world", None, fire=fire.id)
        return fire

    def add_subject(self, position, now):
        subject = self.world.add_subject(position, now)
        self.log.write(now, "scenario", "OPERATOR", f"Survivor evidence {subject.id} added to the world", None)
        return subject

    def manual_clear(self, fire_id, now):
        self.world.manual_clear(fire_id, now)
        self.log.write(now, "manual_clear", "OPERATOR", f"Operator cleared {fire_id}; not autonomous", None, fire=fire_id)

    def set_connection(self, key, connected, now, by="OPERATOR"):
        self.bridge.set_connection(key, connected)
        kind = "reconnect" if connected else "isolate"
        text = "radio restored" if connected else "radio isolated; local ledger retained"
        self.log.write(now, kind, key, f"{key} {text}", None, by=by)

    def _director(self, now):
        if not self.script:
            return
        fire = self.world.fires[self.large_fire]
        if self.subject is None and fire.fraction <= SURVIVOR_AT_FRACTION:
            self.subject = self.world.add_subject(self.survivor_position, now).id
            self.log.write(now, "scenario", "WORLD", "Survivor signal begins near the fire", None)
        if self.partition is None and not self.partition_done and self.diverted_at is not None:
            working = sorted(key for key, name in self.working.items() if name == self.large_fire)
            if now - self.diverted_at >= PARTITION_DELAY and working:
                self.partition = (working[-1], now)
                self.set_connection(working[-1], False, now, by="SCENARIO")
        if self.partition:
            self._watch_partition(now)

    def _watch_partition(self, now):
        drone, started = self.partition
        others = [agent for key, agent in self.bridge.agents.items() if key != drone]
        held = any(
            c.drone_id == drone and c.expires_at > now and c.acknowledged
            for agent in others
            for c in agent.memory.commitments.values()
        )
        if not held and not self.capacity_dropped:
            self.capacity_dropped = True
            self.log.write(now, "capacity_dropped", "SWARM", f"Team no longer counts {drone}; commitment expired", None)
        if now - started >= PARTITION_SECONDS:
            self.set_connection(drone, True, now, by="SCENARIO")
            self.partition, self.partition_done = None, True
            self.reconciling = (drone, started, now)

    def _watch_reconciliation(self, now):
        """Late delivery must merge evidence while keeping its original observation times."""
        drone, started, reconnected = self.reconciling
        if now - reconnected < RECONCILE_SECONDS:
            return
        self.reconciling = None
        own = [
            i
            for i in self.bridge.agents[drone].memory.incidents.values()
            if i.status != "merged" and i.source == drone and started <= i.observed_at <= reconnected
        ]
        peers = [agent for key, agent in self.bridge.agents.items() if key != drone]
        kept = all(
            agent.memory.incidents[i.id].observed_at >= i.observed_at
            for agent in peers
            for i in own
            if i.id in agent.memory.incidents
        )
        self.log.write(
            now, "reconciled", drone, "Ledgers merged after reconnection; evidence times preserved", None,
            incidents=[i.id for i in own], preserved=kept,
        )

    def _sense(self, now):
        self.last_sense = now
        states = self.bridge.states
        for key in self.ids:
            agent, position = self.bridge.agents[key], states[key].position
            detections, visible = self.sensor.scan(key, position, now)
            self.seen[key] = {name: now for name in visible}
            before = set(agent.memory.incidents)
            self.bridge.observe(key, detections)
            for incident_id in set(agent.memory.incidents) - before:
                incident = agent.memory.incidents[incident_id]
                agent.event(
                    now, "detection",
                    f"Sensor detected {incident.kind} at confidence {incident.confidence:.0%}",
                    incident_id, sensor=SENSOR_LABEL,
                )
                self.known[key].add(incident_id)
                self.log.write(now, "knowledge", key, "Learned by own sensor", incident_id, via="sensor")
            for incident in agent.memory.incidents.values():
                if incident.kind != "fire" or incident.status in ("cleared", "merged"):
                    continue
                token = (key, incident.id)
                viewed = self.sensor.can_view(position, incident.position, CLEARANCE_REACH)
                present = any(
                    d.kind == "fire" and dist(d.position, incident.position) < max(13.0, incident.extent)
                    for d in detections
                )
                self.misses[token] = self.misses.get(token, 0) + 1 if viewed and not present else 0
                if self.misses[token] >= CLEARANCE_MISSES:
                    incident.status, incident.observed_at, incident.source = "cleared", now, key
                    agent.event(now, "clearance", "Four fresh negative observations; cleared", incident.id)

    def _note_deliveries(self, now):
        interesting = {"AWARD", "RELEASE_REQUEST", "RELEASED", "RELEASE_REFUSED"}
        for key, packets in self.bridge.last_deliveries.items():
            for packet in packets:
                if packet["kind"] in interesting:
                    self.log.write(
                        now, "delivered", key, f"{packet['kind']} from {packet['origin']}", packet["incident"],
                        message=packet["id"], message_kind=packet["kind"], origin=packet["origin"],
                    )
            ledger = self.bridge.agents[key].memory.incidents
            for incident_id in set(ledger) - self.known[key]:
                self.known[key].add(incident_id)
                via = any(p["kind"] == "REPORT" and p["incident"] == incident_id for p in packets)
                self.log.write(
                    now, "knowledge", key, "Learned through delivered mesh report", incident_id,
                    via="mesh" if via else "unexplained", observed_at=ledger[incident_id].observed_at,
                )

    def _goal(self, key, command):
        """Translate a checked command into a hold using this drone's own ledger only."""
        agent, state = self.bridge.agents[key], self.bridge.states[key]
        home = self.homes[key]
        incident = agent.memory.incidents.get(command.incident_id)
        if command.task in (Task.RESPOND, Task.VERIFY) and incident is not None:
            return standoff(incident.position, agent.index, self.obstacles)
        if command.task == Task.RETURN:
            near = dist(state.position[:2], home[:2]) < 4
            return (home[0], home[1], 7.0 if near else agent.altitude)
        return tuple(command.target)

    def _route(self, key, goal):
        agent, position = self.bridge.agents[key], self.bridge.states[key].position
        # Cross at this aircraft's lane, then change altitude near the destination.
        if dist(position[:2], goal[:2]) > 25:
            goal = (*goal[:2], agent.altitude)
        waypoint = route(position, goal, self.obstacles)[0]
        return (
            min(232.0, max(8.0, waypoint[0])),
            min(232.0, max(8.0, waypoint[1])),
            min(self.c.ceiling, max(5.0, waypoint[2])),
        )

    def _virtual_work(self, key, command, goal, now):
        """Scenario effect only; PhysicsMission still forces every physical release off."""
        agent, state = self.bridge.agents[key], self.bridge.states[key]
        self.working.pop(key, None)
        commitment, incident = agent.assignment, agent.memory.incidents.get(command.incident_id)
        if (
            command.task != Task.RESPOND
            or incident is None
            or commitment is None
            or not commitment.acknowledged
            or commitment.expires_at <= now
            or commitment.incident_id != incident.id
            or dist(state.position, goal) > ARRIVAL_RADIUS
        ):
            return
        if incident.kind == "fire":
            nearby = [
                fire
                for fire in self.world.fires.values()
                if fire.active
                and fire.id in self.seen[key]
                and dist(fire.position, incident.position) < max(13.0, incident.extent)
            ]
            if not nearby or state.water <= 0:
                return
            check = self.bridge.safety.check(state, Command(Task.RESPOND, goal, incident.id, True), now)
            if not check.allowed:
                agent.event(now, "safety", check.reason, incident.id)
                return
            fire = nearby[0]
            used = self.world.apply_work(fire.id, min(state.water, self.c.suppress_rate * TICK_SECONDS), key, now)
            state.water -= used
            self.used_capacity[key] += used
            self.working[key] = fire.id
            if fire.contained_at == now:
                agent.event(now, "containment", "Virtual work contained the fire; awaiting clearance", incident.id, fire=fire.id)
            return
        for subject in self.world.subjects.values():
            if subject.id in self.seen[key] and subject.escalated_at is None:
                subject.escalated_at, subject.escalated_by = now, key
                incident.status, incident.observed_at = "escalated", now
                agent.event(
                    now, "escalation",
                    "Possible survivor verified at close range; ground rescue requested, none simulated",
                    incident.id, subject=subject.id,
                )

    def _service(self, key, now):
        state, agent = self.bridge.states[key], self.bridge.agents[key]
        home = self.homes[key]
        if not state.servicing or dist(state.position[:2], home[:2]) >= 6 or state.position[2] > 12:
            return
        state.water = min(self.c.max_water, state.water + TICK_SECONDS * 2.0)
        if state.water >= self.c.max_water:
            state.servicing = False
            agent.event(now, "service", "Scenario capacity replenished; resuming mission")

    def _complete(self, now):
        if self.completed_at is not None or not self.script or not self.partition_done or self.reconciling:
            return
        fires_done = all(not f.active for f in self.world.fires.values())
        subjects_done = all(s.escalated_at is not None for s in self.world.subjects.values())
        cleared = all(
            any(
                i.kind == "fire" and i.status == "cleared" and dist(i.position, fire.position) < 13
                for agent in self.bridge.agents.values()
                for i in agent.memory.incidents.values()
            )
            for fire in self.world.fires.values()
        )
        if fires_done and subjects_done and cleared:
            self.completed_at = now
            self.log.write(now, "mission_complete", "SWARM", "All fires cleared by fresh observations; survivor escalated")

    def tick(self, now, positions, armed):
        """Run at 2 Hz. Inputs are measured poses and PX4 armed states; returns flight targets."""
        for key in self.ids:
            state = self.bridge.states[key]
            self.bridge.telemetry(
                key, position=positions[key], stamp=now, battery=max(0.3, 1 - now / self.c.battery_seconds),
                water=state.water, healthy=bool(armed[key]),
            )
        self.time = self.bridge.time = float(now)
        self._director(now)
        if self.reconciling:
            self._watch_reconciliation(now)
        if now - self.last_sense >= 1.0:
            self._sense(now)
        commands = self.bridge.tick(now)
        self._note_deliveries(now)
        self._record_events()
        keys = self.ids
        for n, a in enumerate(keys):
            for b in keys[n + 1 :]:
                pa, pb = self.bridge.states[a].position, self.bridge.states[b].position
                if min(pa[2], pb[2]) > 4:
                    self.minimum_separation = min(self.minimum_separation, dist(pa, pb))
        for key in keys:
            position, state = self.bridge.states[key].position, self.bridge.states[key]
            if position[2] > 4:
                self.minimum_clearance = min(self.minimum_clearance, clearance(position, self.obstacles))
            agent = self.bridge.agents[key]
            if not self.launched[key]:
                self.launched[key] = position[2] >= agent.altitude - 5
                self.goals[key] = self.flight_targets[key] = (*self.homes[key][:2], agent.altitude)
                continue
            goal = self._goal(key, commands[key])
            self.goals[key] = goal
            target = self._route(key, goal)
            checked = self.bridge.safety.check(state, replace(commands[key], target=target, release=False), now)
            target = checked.command.target
            nearby = [
                other for other in keys
                if other < key and dist(self.bridge.states[other].position, position) < PROXIMITY_HOLD
            ]
            self.flight_targets[key] = tuple(position) if nearby else tuple(target)
            self._virtual_work(key, commands[key], goal, now)
            self._service(key, now)
        self._record_events()
        self._complete(now)
        return self.flight_targets

    def _record_events(self):
        for event in self.bridge.new_events:
            self.log.write(event.time, event.kind, event.drone, event.text, event.incident_id, **event.details)
            if event.kind == "divert" and self.diverted_at is None:
                self.diverted_at = event.time
        self.bridge.new_events = []
        for agent in self.bridge.agents.values():
            for event in agent.events:
                self.log.write(event.time, event.kind, event.drone, event.text, event.incident_id, **event.details)
            agent.events = []

    def incidents_view(self):
        """Observer's union of what aircraft believe; each row names who holds it."""
        rows = {}
        now = self.time
        for key, agent in self.bridge.agents.items():
            for incident in agent.memory.incidents.values():
                if incident.status == "merged":
                    continue
                row = rows.setdefault(incident.id, {**asdict(incident), "known_by": [], "committed": [], "capacity": 0.0})
                row["known_by"].append(key)
                if incident.observed_at > row["observed_at"]:
                    row.update(asdict(incident), known_by=row["known_by"], committed=row["committed"], capacity=row["capacity"])
            assignment = agent.assignment
            if assignment and assignment.acknowledged and assignment.expires_at > now:
                row = rows.get(assignment.incident_id)
                if row:
                    row["committed"].append(key)
                    row["capacity"] += self.bridge.states[key].water
        ordered = sorted(rows.values(), key=lambda r: (r["status"] in ("cleared", "escalated"), -r["observed_at"]))
        for row in ordered:
            row["priority"] = round(100 * row["survivor"] + 12 * row["severity"], 1)
        return ordered

    def drones_view(self):
        rows = []
        for index, key in enumerate(self.ids):
            state, agent = self.bridge.states[key], self.bridge.agents[key]
            rows.append(
                {
                    "id": key,
                    "color": DRONE_COLORS[index % len(DRONE_COLORS)],
                    "task": str(state.task),
                    "reason": state.reason,
                    "incident_id": state.incident_id,
                    "connected": state.connected,
                    "capacity": round(state.water, 2),
                    "capacity_max": self.c.max_water,
                    "working": self.working.get(key),
                    "goal": list(self.goals[key]),
                    "target": list(self.flight_targets[key]),
                    "known_incidents": sum(i.status != "merged" for i in agent.memory.incidents.values()),
                }
            )
        return rows

    def summary(self):
        return {
            "policy": self.policy_name,
            "sensor": SENSOR_LABEL,
            "seed": self.c.seed,
            "drones": len(self.ids),
            "completed_at": self.completed_at,
            "minimum_separation_m": self.minimum_separation,
            "minimum_obstacle_clearance_m": self.minimum_clearance,
            "capacity_used": self.used_capacity,
            "world": self.world.records(),
            "physical_release": False,
        }

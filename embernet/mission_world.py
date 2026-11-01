"""Scenario truth and a labeled sensor adapter. Truth reaches actors only as Detections."""

import random
from dataclasses import asdict, dataclass
from math import dist, sqrt

from .contracts import Detection
from .routing import segment_clear

SENSOR_LABEL = "simulated range/line-of-sight sensor; not neural perception"
FIRE_RANGE_BASE, FIRE_RANGE_PER_METRE, FIRE_RANGE_MAX = 72.0, 10.0, 150.0
PERSON_RANGE = 40.0
MINIMUM_SENSING_ALTITUDE = 8.0


@dataclass
class ScenarioFire:
    id: str
    position: tuple
    extent0: float
    severity0: float
    initial: float
    remaining: float
    created_at: float
    contained_at: float | None = None
    manual: bool = False
    contributors: tuple = ()

    @property
    def fraction(self):
        return max(0.0, self.remaining / self.initial)

    @property
    def extent(self):
        return max(0.5, self.extent0 * sqrt(self.fraction))

    @property
    def severity(self):
        return max(0.02, self.severity0 * self.fraction)

    @property
    def active(self):
        return self.contained_at is None


@dataclass
class ScenarioSubject:
    id: str
    position: tuple
    visible_from: float
    escalated_at: float | None = None
    escalated_by: str = ""


class ScenarioWorld:
    """Operator and script events edit this object; no ledger is ever written here."""

    def __init__(self, obstacles=()):
        self.fires: dict[str, ScenarioFire] = {}
        self.subjects: dict[str, ScenarioSubject] = {}
        self.obstacles = tuple(obstacles)

    def add_fire(self, position, extent, severity, now=0.0):
        if len(self.fires) >= 12:
            raise ValueError("Twelve-fire scenario limit reached")
        if extent <= 0 or not 0 < severity <= 1:
            raise ValueError("Invalid scenario fire")
        key = f"F{len(self.fires) + 1:02}"
        demand = max(2.0, extent * extent * 0.38 + severity * 4.0)
        self.fires[key] = ScenarioFire(key, tuple(position), extent, severity, demand, demand, now)
        return self.fires[key]

    def add_subject(self, position, now=0.0):
        if len(self.subjects) >= 12:
            raise ValueError("Twelve-subject scenario limit reached")
        key = f"S{len(self.subjects) + 1:02}"
        self.subjects[key] = ScenarioSubject(key, tuple(position), now)
        return self.subjects[key]

    def apply_work(self, fire_id, amount, drone, now):
        fire = self.fires[fire_id]
        if not fire.active or amount <= 0:
            return 0.0
        used = min(amount, fire.remaining)
        fire.remaining -= used
        if drone not in fire.contributors:
            fire.contributors = (*fire.contributors, drone)
        if fire.remaining <= 0.05:
            fire.remaining, fire.contained_at = 0.0, now
        return used

    def manual_clear(self, fire_id, now):
        fire = self.fires[fire_id]
        fire.remaining, fire.contained_at, fire.manual = 0.0, now, True

    def records(self):
        return {
            "fires": [
                dict(asdict(f), extent=f.extent, severity=f.severity, fraction=f.fraction)
                for f in self.fires.values()
            ],
            "subjects": [asdict(s) for s in self.subjects.values()],
        }


class SimulatedSensor:
    """Declared observation path: range, line of sight, noise, and the current time."""

    def __init__(self, world: ScenarioWorld, seed=41):
        self.world, self.rng = world, random.Random(seed + 2203)
        self.sensor = SENSOR_LABEL

    @staticmethod
    def fire_range(fire):
        return min(FIRE_RANGE_MAX, FIRE_RANGE_BASE + FIRE_RANGE_PER_METRE * fire.extent)

    def _sees(self, position, target, reach):
        separation = dist(position, target)
        if position[2] < MINIMUM_SENSING_ALTITUDE or separation > reach:
            return False
        # Facade targets sit on the obstacle face, so the final metres are not tested.
        trim = min(0.9, 4.0 / max(separation, 1e-6)) if separation > 4 else 0.0
        end = tuple(a + (b - a) * (1 - trim) for a, b in zip(position, target))
        return segment_clear(position, end, self.world.obstacles, 0.0)

    def can_view(self, position, target, reach):
        return self._sees(position, target, reach)

    def scan(self, drone, position, now):
        """Detections for one aircraft, plus the truth ids used only by world adapters."""
        detections, visible = [], []
        for fire in self.world.fires.values():
            reach = self.fire_range(fire)
            if not fire.active or not self._sees(position, fire.position, reach):
                continue
            separation = dist(position, fire.position)
            sigma = 0.002 * separation
            estimate = tuple(v + self.rng.gauss(0, sigma) for v in fire.position)
            confidence = max(0.55, min(0.98, 1.02 - 0.4 * separation / reach))
            extent = fire.extent * (1 + self.rng.uniform(-0.02, 0.02))
            severity = min(1.0, fire.severity * (1 + self.rng.uniform(-0.02, 0.02)))
            detections.append(Detection("fire", estimate, extent, severity, confidence, now, drone))
            visible.append(fire.id)
        for subject in self.world.subjects.values():
            if subject.visible_from > now or not self._sees(position, subject.position, PERSON_RANGE):
                continue
            separation = dist(position, subject.position)
            confidence = max(0.5, min(0.9, 0.98 - 0.5 * separation / PERSON_RANGE))
            estimate = tuple(v + self.rng.gauss(0, 0.05) for v in subject.position)
            detections.append(Detection("person", estimate, 2.0, 0.2, confidence, now, drone))
            visible.append(subject.id)
        return detections, visible

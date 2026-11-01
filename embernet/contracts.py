"""Serializable contracts shared by simulation and autonomy, never motor commands."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from math import dist
from typing import Protocol

Vec3 = tuple[float, float, float]


class Task(StrEnum):
    SEARCH = "search"
    VERIFY = "verify"
    RESPOND = "respond"
    RELAY = "relay"
    RETURN = "return"
    HOLD = "hold"


@dataclass(frozen=True)
class Config:
    seed: int = 41
    drones: int = 6
    size: float = 320.0
    altitude: float = 28.0
    ceiling: float = 100.0
    speed: float = 11.0
    sensor_radius: float = 51.0
    radio_range: float = 155.0
    packet_loss: float = 0.08
    radio_delay: float = 0.45
    report_ttl: float = 35.0
    peer_ttl: float = 12.0
    commitment_ttl: float = 12.0
    max_water: float = 18.0
    battery_seconds: float = 850.0
    suppress_rate: float = 1.3
    dt: float = 0.5
    horizon: float = 360.0

    def __post_init__(self):
        if not 2 <= self.drones <= 16:
            raise ValueError("Fleet size must be between 2 and 16")
        if not 0 <= self.packet_loss <= 1:
            raise ValueError("Packet loss must be between 0 and 1")
        positive = (
            self.size,
            self.ceiling,
            self.speed,
            self.sensor_radius,
            self.radio_range,
            self.report_ttl,
            self.peer_ttl,
            self.commitment_ttl,
            self.max_water,
            self.battery_seconds,
            self.suppress_rate,
            self.dt,
            self.horizon,
        )
        if any(v <= 0 for v in positive) or not 5 <= self.altitude <= self.ceiling or self.radio_delay < 0:
            raise ValueError("Invalid mission dimensions, timing or resource settings")
        if self.altitude + (self.drones - 1) * 4 > self.ceiling:
            raise ValueError("Fleet altitude lanes exceed the mission ceiling")


@dataclass
class VehicleState:
    id: str
    position: Vec3
    home: Vec3
    battery: float = 1.0
    water: float = 18.0
    healthy: bool = True
    connected: bool = True
    stamp: float = 0.0
    task: Task = Task.SEARCH
    target: Vec3 | None = None
    incident_id: str | None = None
    reason: str = "Ready to launch"
    servicing: bool = False


@dataclass(frozen=True)
class Command:
    task: Task
    target: Vec3
    incident_id: str | None = None
    release: bool = False
    reason: str = ""


@dataclass(frozen=True)
class Detection:
    kind: str
    position: Vec3
    extent: float
    severity: float
    confidence: float
    observed_at: float
    source: str


@dataclass
class Incident:
    id: str
    position: Vec3
    extent: float
    severity: float
    confidence: float
    observed_at: float
    source: str
    kind: str = "fire"
    survivor: float = 0.0
    animal: float = 0.0
    status: str = "confirmed"
    deferred_reason: str = ""
    review_at: float = 0.0
    last_progress: float = 0.0
    owner: str = ""

    def demand(self) -> float:
        # Synthetic capacity proxy, not a physical fire-engineering formula.
        if self.kind != "fire":
            return 0.0
        return max(2.0, self.extent * self.extent * 0.38 + self.severity * 4.0)

    def priority(self, now: float, eta: float = 0.0) -> float:
        age = max(0.0, now - self.observed_at)
        vulnerability = 100.0 * self.survivor + 30.0 * self.animal
        urgency = 12.0 * self.severity + min(25.0, self.demand() * 0.45)
        review = min(12.0, max(0.0, now - self.review_at) * 0.3) if self.status == "deferred" else 0.0
        return vulnerability + urgency + review + min(age * 0.08, 4.0) - eta * 0.12

    def fresh(self, now: float, ttl: float) -> bool:
        return 0 <= now - self.observed_at <= ttl and self.status not in ("cleared", "merged")


@dataclass
class Peer:
    id: str
    position: Vec3
    battery: float
    water: float
    task: str
    incident_id: str | None
    stamp: float
    servicing: bool = False


@dataclass
class Commitment:
    incident_id: str
    drone_id: str
    version: str
    water: float
    eta: float
    expires_at: float
    acknowledged: bool = False
    owner: str = ""


@dataclass
class Message:
    id: str
    origin: str
    kind: str
    payload: dict
    created_at: float
    recipient: str | None = None
    hops: int = 3


@dataclass
class Event:
    time: float
    kind: str
    drone: str
    text: str
    incident_id: str | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


class FlightAdapter(Protocol):
    """Autopilots implement this boundary; AI never receives a motor API."""

    simulated: bool

    def execute(self, state: VehicleState, command: Command, dt: float) -> VehicleState: ...


def eta(position: Vec3, target: Vec3, speed: float) -> float:
    return dist(position, target) / speed

"""Local replaceable memory: observation provenance survives forwarding."""

from dataclasses import asdict
from math import dist
from typing import Protocol

from .contracts import Commitment, Detection, Incident, Peer


class Memory(Protocol):
    incidents: dict[str, Incident]
    peers: dict[str, Peer]
    commitments: dict[str, Commitment]

    def observe(self, detection: Detection, drone_id: str) -> Incident: ...
    def merge(self, record: dict) -> Incident: ...
    def defer(self, incident_id: str, now: float, reason: str): ...


class IncidentLedger:
    def __init__(self):
        self.incidents: dict[str, Incident] = {}
        self.peers: dict[str, Peer] = {}
        self.commitments: dict[str, Commitment] = {}
        self._counter = 0

    def observe(self, detection: Detection, drone_id: str) -> Incident:
        candidates = [
            i
            for i in self.incidents.values()
            if i.status != "merged" and dist(i.position, detection.position) < max(13.0, i.extent)
        ]
        incident = min(candidates, key=lambda i: dist(i.position, detection.position)) if candidates else None
        if incident is None:
            self._counter += 1
            incident = Incident(
                f"{drone_id}-{self._counter:03}",
                detection.position,
                max(1.0, detection.extent),
                detection.severity,
                detection.confidence,
                detection.observed_at,
                detection.source,
                kind=detection.kind,
                owner=drone_id,
            )
            self.incidents[incident.id] = incident
        if detection.observed_at >= incident.observed_at:
            if detection.kind == "fire":
                incident.position = detection.position
                incident.extent, incident.severity = detection.extent, detection.severity
                incident.kind = "fire"
            incident.confidence = detection.confidence
            incident.observed_at, incident.source = detection.observed_at, detection.source
            if incident.status == "suspected" or (incident.status == "cleared" and detection.kind == "fire"):
                incident.status = "confirmed"
        if detection.kind == "person":
            incident.survivor = max(incident.survivor, detection.confidence)
        if detection.kind == "animal":
            incident.animal = max(incident.animal, detection.confidence)
        return incident

    def merge(self, record: dict) -> Incident:
        incoming = Incident(**record)
        incoming.position = tuple(incoming.position)
        nearby = [
            i
            for i in self.incidents.values()
            if i.id != incoming.id and i.status != "merged" and dist(i.position, incoming.position) < 13.0
        ]
        local = self.incidents.get(incoming.id)
        if local is None:
            self.incidents[incoming.id] = incoming
            local = incoming
        elif incoming.observed_at > local.observed_at:
            deferred, reason, review = local.status, local.deferred_reason, local.review_at
            for key, value in asdict(incoming).items():
                setattr(local, key, value)
            if deferred == "escalated":
                local.status = "escalated"
            if deferred == "deferred" and incoming.status not in ("cleared", "merged"):
                local.status, local.deferred_reason, local.review_at = deferred, reason, review
        elif incoming.observed_at == local.observed_at and incoming.status == "cleared":
            local.status = "cleared"
        if incoming.status == "escalated":
            # Escalation is terminal: later sightings of the same person cannot reopen it.
            local.status = "escalated"
        local.survivor = max(local.survivor, incoming.survivor)
        local.animal = max(local.animal, incoming.animal)
        # Deterministic identity reconciliation, not global incident knowledge.
        for other in nearby:
            canonical, duplicate = sorted([local, other], key=lambda i: i.id)
            canonical.survivor = max(canonical.survivor, duplicate.survivor)
            canonical.animal = max(canonical.animal, duplicate.animal)
            if duplicate.observed_at > canonical.observed_at:
                canonical.position, canonical.extent = duplicate.position, duplicate.extent
                canonical.severity, canonical.observed_at = duplicate.severity, duplicate.observed_at
            duplicate.status = "merged"
            local = canonical
        return local

    def defer(self, incident_id: str, now: float, reason: str):
        incident = self.incidents[incident_id]
        incident.status = "deferred"
        incident.deferred_reason = reason
        if incident.review_at <= now:
            incident.review_at = now + 6.0

    def active_commitments(self, incident_id: str, now: float, *, acknowledged=True):
        return [
            c
            for c in self.commitments.values()
            if c.incident_id == incident_id and c.expires_at > now and (c.acknowledged or not acknowledged)
        ]

    def records(self):
        return [asdict(i) for i in self.incidents.values() if i.status != "merged"]

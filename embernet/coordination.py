"""Per-drone negotiation. Only own state, local memory, and delivered packets enter here."""

from dataclasses import asdict
from math import dist

from .contracts import Command, Commitment, Config, Event, Message, Peer, Task, VehicleState, eta
from .memory import IncidentLedger


class Agent:
    def __init__(self, drone_id: str, index: int, config: Config, memory=None):
        self.id, self.index, self.c = drone_id, index, config
        self.altitude = config.altitude + index * 4.0
        self.memory = memory if memory is not None else IncidentLedger()
        self.assignment: Commitment | None = None
        self.outbox: list[Message] = []
        self.events: list[Event] = []
        self.bids: dict[str, dict[str, dict]] = {}
        self.counter = 0
        self.last_broadcast = -100.0
        self.last_auction = -100.0
        self.last_ack = -100.0
        self.last_release_request = -100.0
        self.patrol_index = 0
        self.last_action = 0
        self.requested_release: str | None = None
        self.refused_until: dict[str, float] = {}
        self.diversion_target: str | None = None
        self.diversion_until = 0.0
        self.released_until: dict[str, float] = {}
        self.owner_claims: dict[str, dict[str, float]] = {}
        self.verification_id: str | None = None
        self.verification_until = 0.0
        self.last_reason = "Ready"

    def emit(self, kind, payload, now, recipient=None):
        self.counter += 1
        message = Message(f"{self.id}:{self.counter}", self.id, kind, payload, now, recipient)
        if recipient == self.id:
            self.receive([message], now)
        else:
            self.outbox.append(message)

    def event(self, now, kind, text, incident_id=None, **details):
        self.events.append(Event(now, kind, self.id, text, incident_id, details))

    def receive(self, messages, now):
        for msg in messages:
            if now - msg.created_at > 20 or msg.created_at > now:
                continue
            p = msg.payload
            if msg.kind == "STATE":
                peer = Peer(**p)
                peer.position = tuple(peer.position)
                previous = self.memory.peers.get(peer.id)
                if previous is None or peer.stamp > previous.stamp:
                    self.memory.peers[peer.id] = peer
            elif msg.kind == "REPORT":
                self.memory.merge(p)
            elif msg.kind == "CLAIM":
                incident = self.memory.incidents.get(p["incident_id"])
                if incident and 0 <= now - p["observed_at"] <= self.c.report_ttl:
                    claims = self.owner_claims.setdefault(incident.id, {})
                    claims[msg.origin] = msg.created_at
                    live = [owner for owner, stamp in claims.items() if now - stamp < self.c.peer_ttl]
                    if live:
                        incident.owner = min(live)
            elif msg.kind == "BID":
                if p["drone_id"] == msg.origin:
                    self.bids.setdefault(p["incident_id"], {})[msg.origin] = {**p, "stamp": msg.created_at}
            elif msg.kind == "AWARD":
                commitment = Commitment(**p)
                if (
                    msg.origin != commitment.owner
                    or commitment.drone_id != self.id
                    or commitment.expires_at <= now
                ):
                    continue
                if (
                    self.assignment
                    and self.assignment.expires_at > now
                    and self.assignment.incident_id != commitment.incident_id
                ):
                    continue
                is_new = self.assignment is None or self.assignment.version != commitment.version
                commitment.acknowledged = True
                self.assignment = commitment
                self.memory.commitments[self.id] = commitment
                incident = self.memory.incidents.get(commitment.incident_id)
                if incident and incident.status not in ("cleared", "merged", "escalated"):
                    incident.status, incident.deferred_reason = "assigned", ""
                if is_new:
                    self.event(
                        now,
                        "commitment",
                        "Accepted response assignment",
                        commitment.incident_id,
                        owner=commitment.owner,
                        version=commitment.version,
                        message=msg.id,
                    )
                self.emit("ACK", asdict(commitment), now, recipient=commitment.owner)
            elif msg.kind == "ACK":
                incoming = Commitment(**p)
                existing = self.memory.commitments.get(msg.origin)
                if existing and incoming.version == existing.version and incoming.owner == self.id:
                    existing.acknowledged = True
                    existing.water, existing.eta = incoming.water, incoming.eta
                    existing.expires_at = max(
                        existing.expires_at, min(now + self.c.commitment_ttl, incoming.expires_at)
                    )
                    # Share only acknowledged commitments, preserving version and expiry.
                    self.emit("COMMITMENT", asdict(existing), now)
            elif msg.kind == "COMMITMENT":
                incoming = Commitment(**p)
                existing = self.memory.commitments.get(incoming.drone_id)
                if msg.origin == incoming.owner and (
                    existing is None or incoming.expires_at > existing.expires_at
                ):
                    self.memory.commitments[incoming.drone_id] = incoming
            elif msg.kind == "RELEASE_REQUEST":
                current = self.memory.commitments.get(msg.origin)
                incident = self.memory.incidents.get(p["incident_id"])
                if current is None or incident is None or current.version != p["version"]:
                    continue
                others = [
                    c
                    for c in self.memory.active_commitments(incident.id, now)
                    if c.drone_id != msg.origin and c.eta <= max(25.0, current.eta + 8.0)
                ]
                # One release at a time, so each decision sees the capacity of the last one.
                pending = any(until > now for until in self.released_until.values())
                if others and not pending and (
                    incident.kind != "fire" or sum(c.water for c in others) >= incident.demand() * 1.1
                ):
                    current.expires_at = now
                    self.released_until[msg.origin] = now + 12.0
                    self.emit(
                        "RELEASED",
                        {"version": current.version, "incident_id": incident.id},
                        now,
                        recipient=msg.origin,
                    )
                    self.event(
                        now,
                        "release",
                        "Released responder; acknowledged team still covers demand",
                        incident.id,
                    )
                else:
                    covered = sum(c.water for c in others)
                    self.emit(
                        "RELEASE_REFUSED",
                        {"version": current.version, "incident_id": incident.id, "covered": covered},
                        now,
                        recipient=msg.origin,
                    )
                    self.event(
                        now,
                        "refusal",
                        f"Refused {msg.origin} release: another release is in progress"
                        if pending
                        else f"Refused {msg.origin} release: others cover {covered:.1f} of "
                        f"{incident.demand() * 1.1:.1f} required",
                        incident.id,
                    )
            elif msg.kind == "RELEASE_REFUSED":
                if self.assignment and self.assignment.version == p["version"]:
                    self.event(
                        now,
                        "defer",
                        "Release refused; keeping commitment and remembering the new incident",
                        self.requested_release,
                    )
                    if self.requested_release:
                        self.refused_until[self.requested_release] = now + 15.0
                    self.requested_release = None
            elif msg.kind == "RELEASED":
                if (
                    self.assignment
                    and self.assignment.version == p["version"]
                    and msg.origin == self.assignment.owner
                ):
                    self.event(
                        now, "divert", "Release acknowledged; may bid on the new incident", p["incident_id"]
                    )
                    self.memory.commitments.pop(self.id, None)
                    self.assignment = None
                    self.diversion_target = self.requested_release
                    self.diversion_until = now + 12.0
                    self.requested_release = None

    def candidates(self, state, now):
        return sorted(
            [
                i
                for i in self.memory.incidents.values()
                if i.fresh(now, self.c.report_ttl) and i.status != "escalated"
            ],
            key=lambda i: (-i.priority(now, eta(state.position, i.position, self.c.speed)), i.id),
        )[:6]

    def expert_action(self, state, now):
        incidents = self.candidates(state, now)
        if not state.servicing and state.battery >= 0.20 and incidents and incidents[0].kind != "fire":
            return 4
        if state.servicing or state.water < 1.0 or state.battery < 0.20:
            return 1
        if incidents:
            if self.assignment:
                matching = next(
                    (k for k, i in enumerate(incidents) if i.id == self.assignment.incident_id), None
                )
                if matching is not None and incidents[matching].priority(now) + 15 >= incidents[0].priority(
                    now
                ):
                    return 4 + matching
            return 4
        fresh = [p for p in self.memory.peers.values() if now - p.stamp <= self.c.peer_ttl]
        return 2 if not fresh and now > 12 else 0

    def _auction(self, now):
        for incident in self.memory.incidents.values():
            if (
                incident.owner != self.id
                or not incident.fresh(now, self.c.report_ttl)
                or incident.status == "escalated"
            ):
                continue
            bids = [
                b
                for b in self.bids.get(incident.id, {}).values()
                if now - b["stamp"] <= 6.0
                and (b["water"] > 0.5 or incident.kind != "fire")
                and b["battery"] > 0.20
                and not b["servicing"]
                and b["assigned"] in (None, incident.id)
                and self.released_until.get(b["drone_id"], 0) <= now
            ]
            bids.sort(key=lambda b: (b["eta"], b["drone_id"]))
            active = self.memory.active_commitments(incident.id, now, acknowledged=False)
            covered = sum(c.water for c in active) if incident.kind == "fire" else len(active)
            required = incident.demand() * 1.12 if incident.kind == "fire" else 1
            selected = {c.drone_id for c in active}
            for bid in bids:
                if bid["drone_id"] in selected:
                    continue
                if covered >= required:
                    break
                # One aircraft cannot receive simultaneous unexpired assignments.
                previous = self.memory.commitments.get(bid["drone_id"])
                if previous and previous.expires_at > now and previous.incident_id != incident.id:
                    continue
                commitment = Commitment(
                    incident.id,
                    bid["drone_id"],
                    f"{self.id}:{self.counter + 1}",
                    bid["water"],
                    bid["eta"],
                    now + self.c.commitment_ttl,
                    owner=self.id,
                )
                self.memory.commitments[bid["drone_id"]] = commitment
                selected.add(bid["drone_id"])
                covered += bid["water"] if incident.kind == "fire" else 1
                self.emit("AWARD", asdict(commitment), now, recipient=bid["drone_id"])
            # Renew only fresh responders; no stale heartbeat can extend a commitment.
            for commitment in self.memory.active_commitments(incident.id, now, acknowledged=False):
                bid = next((b for b in bids if b["drone_id"] == commitment.drone_id), None)
                # A previous owner's commitment is left to expire: its aircraft rejects our renewal.
                if bid is not None and commitment.owner == self.id:
                    commitment.expires_at = now + self.c.commitment_ttl
                    self.emit("AWARD", asdict(commitment), now, recipient=commitment.drone_id)
            ack = self.memory.active_commitments(incident.id, now)
            if sum(c.water for c in ack) < incident.demand():
                incident.status = "deferred" if not ack else "assigned"
                incident.deferred_reason = (
                    "Waiting for sufficient acknowledged resources; partial response allowed"
                )
                if incident.review_at <= now:
                    incident.review_at = now + 6
            elif incident.status != "cleared":
                incident.status = "assigned"
                incident.deferred_reason = ""

    def plan(self, state: VehicleState, now: float, action: int | None = None) -> Command:
        if self.assignment:
            incident = self.memory.incidents.get(self.assignment.incident_id)
            if (
                self.assignment.expires_at <= now
                or incident is None
                or incident.status in ("cleared", "merged", "escalated")
            ):
                self.assignment = None
        incidents = self.candidates(state, now)
        action = self.expert_action(state, now) if action is None else action
        self.last_action = action
        preferred = incidents[action - 4] if 4 <= action < 4 + len(incidents) else None
        if self.assignment is None and now < self.diversion_until:
            preferred = next((i for i in incidents if i.id == self.diversion_target), preferred)

        if now - self.last_broadcast >= 2.0:
            self.last_broadcast = now
            self.emit(
                "STATE",
                asdict(
                    Peer(
                        self.id,
                        state.position,
                        state.battery,
                        state.water,
                        state.task.value,
                        state.incident_id,
                        now,
                        state.servicing,
                    )
                ),
                now,
            )
            records = sorted(self.memory.incidents.values(), key=lambda i: -i.observed_at)
            for incident in [i for i in records if i.status != "merged"][:8]:
                owner_peer = self.memory.peers.get(incident.owner)
                owner_age = now - owner_peer.stamp if owner_peer else now
                if (
                    incident.owner != self.id
                    and owner_age > self.c.peer_ttl + 4
                    and incident.source == self.id
                ):
                    old_owner = incident.owner
                    incident.owner = self.id
                    self.event(
                        now,
                        "ownership",
                        f"Owner {old_owner} unreachable; local observer taking responsibility",
                        incident.id,
                    )
                if incident.owner == self.id and incident.fresh(now, self.c.report_ttl):
                    self.owner_claims.setdefault(incident.id, {})[self.id] = now
                    self.emit("CLAIM", {"incident_id": incident.id, "observed_at": incident.observed_at}, now)
                self.emit("REPORT", asdict(incident), now)
            targets = [preferred] if preferred else []
            if self.assignment:
                assigned = self.memory.incidents.get(self.assignment.incident_id)
                if assigned and assigned not in targets:
                    targets.append(assigned)
            for incident in targets:
                bid = {
                    "incident_id": incident.id,
                    "drone_id": self.id,
                    "water": state.water,
                    "battery": state.battery,
                    "eta": eta(state.position, (*incident.position[:2], self.altitude), self.c.speed),
                    "servicing": state.servicing,
                    "assigned": self.assignment.incident_id if self.assignment else None,
                }
                self.emit("BID", bid, now, recipient=incident.owner)

        if now - self.last_auction >= 3.0:
            self.last_auction = now
            self._auction(now)
        if self.assignment and now - self.last_ack >= 2.0:
            self.last_ack = now
            self.assignment.water = state.water
            incident = self.memory.incidents[self.assignment.incident_id]
            self.assignment.eta = eta(state.position, incident.position, self.c.speed)
            self.emit("ACK", asdict(self.assignment), now, recipient=self.assignment.owner)

        needs_service = state.water < self.c.max_water * 0.95 or state.battery < 0.95
        assigned = self.memory.incidents.get(self.assignment.incident_id) if self.assignment else None
        subject_response = (
            assigned.kind != "fire"
            if assigned is not None
            else (preferred is not None and preferred.kind != "fire")
        )
        if (
            state.servicing
            or (action == 1 and needs_service)
            or (state.water < 0.5 and not subject_response)
            or state.battery < 0.18
        ):
            state.servicing = True
            return_target = (
                (*state.home[:2], self.altitude)
                if dist(state.position[:2], state.home[:2]) > 3
                else state.home
            )
            return Command(Task.RETURN, return_target, reason="Return to individual pad for replenishment")
        if self.assignment:
            incident = self.memory.incidents[self.assignment.incident_id]
            target = (*incident.position[:2], self.altitude)
            alternatives = [i for i in incidents if i.id != incident.id]
            alternate = (
                preferred if preferred and preferred.id != incident.id else next(iter(alternatives), None)
            )
            quick_stop = (
                alternate
                and alternate.demand() <= state.water * 0.55
                and eta(state.position, alternate.position, self.c.speed) < 14
                and alternate.demand() / self.c.suppress_rate < 12
            )
            if alternate and (alternate.priority(now) > incident.priority(now) + 15 or quick_stop):
                self.memory.defer(
                    alternate.id, now, "Current response commitment; release not yet acknowledged"
                )
                # One request at a time: only the nearest aircraft this drone knows of asks.
                # Peer positions are seconds old, so near-ties fall to the lower aircraft id.
                mine = dist(state.position, alternate.position)
                nearest = not any(
                    dist(p.position, alternate.position) < mine - 25
                    or (dist(p.position, alternate.position) <= mine + 25 and p.id < self.id)
                    for p in self.memory.peers.values()
                    if now - p.stamp <= self.c.peer_ttl and p.id != self.id
                )
                held = self.memory.active_commitments(alternate.id, now, acknowledged=False)
                if (
                    nearest
                    and not (held and alternate.kind != "fire")
                    and now - self.last_release_request > 4
                    and self.refused_until.get(alternate.id, 0) <= now
                ):
                    self.last_release_request = now
                    self.requested_release = alternate.id
                    self.emit(
                        "RELEASE_REQUEST",
                        {"incident_id": incident.id, "version": self.assignment.version},
                        now,
                        recipient=self.assignment.owner,
                    )
            return Command(
                Task.RESPOND,
                target,
                incident.id,
                dist(state.position, target) <= 4.0 and incident.kind == "fire",
                "Responding under acknowledged commitment",
            )
        if preferred:
            self.memory.defer(preferred.id, now, "Bid sent; awaiting acknowledged assignment")
            if now < self.diversion_until and preferred.id == self.diversion_target:
                # A released aircraft closes on its incident instead of resuming search.
                return Command(
                    Task.VERIFY,
                    (*preferred.position[:2], self.altitude),
                    preferred.id,
                    reason="Released; moving to the new incident while awaiting assignment",
                )
        if preferred is None:
            revisit = self.memory.incidents.get(self.verification_id)
            if (
                revisit is None
                or revisit.status in ("cleared", "merged", "escalated")
                or now >= self.verification_until
            ):
                overdue = [
                    i
                    for i in self.memory.incidents.values()
                    if i.status not in ("cleared", "merged", "escalated")
                    and i.review_at <= now
                    and (now - i.observed_at > self.c.report_ttl or i.status == "deferred")
                ]
                revisit = max(overdue, key=lambda i: i.priority(now), default=None)
                if revisit:
                    self.verification_id = revisit.id
                    self.verification_until = now + eta(state.position, revisit.position, self.c.speed) + 9
                    revisit.review_at = self.verification_until
                    self.event(
                        now, "review", "Revisiting remembered incident for fresh sensor evidence", revisit.id
                    )
            if revisit and now < self.verification_until:
                return Command(
                    Task.VERIFY,
                    (*revisit.position[:2], self.altitude),
                    revisit.id,
                    reason="Rechecking deferred or stale incident; old evidence cannot authorize discharge",
                )
        if action == 3:
            return Command(Task.HOLD, state.position, reason="Mission policy selected hold")
        if action == 2:
            fresh = [p for p in self.memory.peers.values() if now - p.stamp <= self.c.peer_ttl]
            anchor = (
                min(fresh, key=lambda p: dist(state.position, p.position)).position
                if fresh
                else (self.c.size / 2, self.c.size / 2, self.c.altitude)
            )
            target = (
                *tuple(a * 0.65 + b * 0.35 for a, b in zip(state.position[:2], anchor[:2])),
                self.altitude,
            )
            return Command(Task.RELAY, target, reason="Repositioning to improve mesh contact")
        # Stable parallel lawnmower strips, each with its own home and search band.
        width = self.c.size / self.c.drones
        x = width * (self.index + 0.5)
        points = [(x, 35.0, self.altitude), (x, self.c.size - 30.0, self.altitude)]
        target = points[self.patrol_index % 2]
        if dist(state.position, target) < 6:
            self.patrol_index += 1
            target = points[self.patrol_index % 2]
        return Command(Task.SEARCH, target, reason="Searching assigned transect")

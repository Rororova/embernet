"""Bounded-hop store-and-forward radio. Position truth is used for propagation only."""

import random
from dataclasses import dataclass, replace
from heapq import heappop, heappush
from math import dist

from .contracts import Config, Message, VehicleState


@dataclass
class PacketStats:
    sent: int = 0
    delivered: int = 0
    lost: int = 0
    forwarded: int = 0


class Mesh:
    def __init__(self, config: Config):
        self.c = config
        self.rng = random.Random(config.seed + 912)
        self.loss = config.packet_loss
        self.enabled = True
        self.isolated: set[str] = set()
        self.stats = PacketStats()
        self.queue = []
        self.seen: dict[str, dict[str, float]] = {}
        self.serial = 0
        self.traffic: list[dict] = []

    def links(self, states: dict[str, VehicleState]):
        if not self.enabled:
            return []
        ids = sorted(states)
        return [
            (a, b)
            for n, a in enumerate(ids)
            for b in ids[n + 1 :]
            if a not in self.isolated
            and b not in self.isolated
            and dist(states[a].position, states[b].position) <= self.c.radio_range
        ]

    def send(
        self, sender: str, message: Message, now: float, states: dict[str, VehicleState], *, forwarding=False
    ):
        if not self.enabled or sender in self.isolated or message.hops <= 0:
            return
        self.seen.setdefault(sender, {})[message.id] = now
        for receiver, state in states.items():
            if receiver == sender or receiver in self.isolated:
                continue
            if dist(states[sender].position, state.position) > self.c.radio_range:
                continue
            if message.id in self.seen.get(receiver, {}):
                continue
            self.stats.sent += 1
            lost = self.rng.random() < self.loss
            self.traffic.append(
                {
                    "time": round(now, 2),
                    "sender": sender,
                    "receiver": receiver,
                    "kind": message.kind,
                    "status": "lost" if lost else "in transit",
                }
            )
            self.traffic = self.traffic[-80:]
            if lost:
                self.stats.lost += 1
                continue
            self.serial += 1
            heappush(
                self.queue,
                (
                    now + self.c.radio_delay + self.rng.random() * 0.2,
                    self.serial,
                    receiver,
                    replace(message, hops=message.hops - 1),
                    sender,
                ),
            )
            if forwarding:
                self.stats.forwarded += 1

    def deliver(self, now: float, states: dict[str, VehicleState]):
        inboxes: dict[str, list[Message]] = {key: [] for key in states}
        while self.queue and self.queue[0][0] <= now:
            _, _, receiver, message, sender = heappop(self.queue)
            # A link can fail during flight; queued packets do not bypass the partition.
            if not self.enabled or receiver in self.isolated or sender in self.isolated:
                self.stats.lost += 1
                continue
            if dist(states[sender].position, states[receiver].position) > self.c.radio_range:
                self.stats.lost += 1
                continue
            seen = self.seen.setdefault(receiver, {})
            if message.id in seen:
                continue
            seen[message.id] = now
            self.stats.delivered += 1
            if message.recipient in (None, receiver):
                inboxes[receiver].append(message)
            self.send(receiver, message, now, states, forwarding=True)
        for seen in self.seen.values():
            for key in [key for key, stamp in seen.items() if now - stamp > 90.0]:
                del seen[key]
        return inboxes

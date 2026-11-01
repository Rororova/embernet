"""Shared recurrent actor; critic-only global inputs are never used in live execution."""

from pathlib import Path

import numpy as np

from .contracts import Task, eta

SLOTS = 6
PEERS = 16
OWN = 10
INCIDENT = 12
PEER = 8
HIDDEN = 64
ACTIONS = 4 + SLOTS


def observation(agent, state, now):
    c = agent.c
    incidents = agent.candidates(state, now)
    own = np.asarray(
        [
            state.position[0] / c.size,
            state.position[1] / c.size,
            state.position[2] / 40,
            state.battery,
            state.water / c.max_water,
            (state.home[0] - state.position[0]) / c.size,
            (state.home[1] - state.position[1]) / c.size,
            float(state.task == Task.RESPOND),
            float(state.servicing),
            now / c.horizon,
        ],
        dtype=np.float32,
    )
    records = np.zeros((SLOTS, INCIDENT), np.float32)
    incident_mask = np.zeros(SLOTS, bool)
    for k, i in enumerate(incidents):
        covered = sum(v.water for v in agent.memory.active_commitments(i.id, now))
        records[k] = [
            (i.position[0] - state.position[0]) / c.size,
            (i.position[1] - state.position[1]) / c.size,
            i.extent / 15,
            i.severity,
            i.survivor,
            i.animal,
            i.demand() / 54,
            min(2, (now - i.observed_at) / c.report_ttl),
            i.priority(now, eta(state.position, i.position, c.speed)) / 150,
            min(2, covered / max(1, i.demand())),
            float(i.owner == agent.id),
            float(agent.assignment is not None and agent.assignment.incident_id == i.id),
        ]
        incident_mask[k] = True
    peers = np.zeros((PEERS, PEER), np.float32)
    peer_mask = np.zeros(PEERS, bool)
    fresh = sorted(
        [p for p in agent.memory.peers.values() if 0 <= now - p.stamp <= c.peer_ttl], key=lambda p: p.id
    )
    for k, p in enumerate(fresh[:PEERS]):
        peers[k] = [
            (p.position[0] - state.position[0]) / c.size,
            (p.position[1] - state.position[1]) / c.size,
            p.battery,
            p.water / c.max_water,
            (now - p.stamp) / c.peer_ttl,
            float(p.task == Task.RESPOND),
            float(p.incident_id is not None),
            float(p.servicing),
        ]
        peer_mask[k] = True
    mask = np.zeros(ACTIONS, bool)
    mask[0], mask[1], mask[2], mask[3] = (
        True,
        state.battery < 0.95 or state.water < c.max_water * 0.95 or state.servicing,
        not fresh and now > 10,
        True,
    )
    resource_eligible = np.asarray(
        [i.kind != "fire" or state.water > 0.5 for i in incidents] + [False] * (SLOTS - len(incidents))
    )
    mask[4:] = incident_mask & resource_eligible & (state.battery > 0.20) & (not state.servicing)
    return {
        "own": own,
        "incidents": records,
        "incident_mask": incident_mask,
        "peers": peers,
        "peer_mask": peer_mask,
        "mask": mask,
    }


def build_policy():
    import torch
    from torch import nn
    from torch.distributions import Categorical

    class RecurrentSwarmPolicy(nn.Module):
        def __init__(self):
            super().__init__()
            self.own_encoder = nn.Sequential(nn.Linear(OWN, 32), nn.Tanh())
            self.incident_encoder = nn.Sequential(nn.Linear(INCIDENT, 48), nn.Tanh())
            self.peer_encoder = nn.Sequential(nn.Linear(PEER, 32), nn.Tanh())
            self.query = nn.Linear(32, 32)
            self.gru = nn.GRUCell(112, HIDDEN)
            self.base_actions = nn.Linear(HIDDEN, 4)
            self.incident_query = nn.Linear(HIDDEN, 48)
            self.incident_bias = nn.Linear(48, 1)
            self.critic = nn.Sequential(nn.Linear(HIDDEN + 12, 64), nn.Tanh(), nn.Linear(64, 1))

        def forward(self, obs, hidden, central=None):
            own = self.own_encoder(obs["own"])
            inc = self.incident_encoder(obs["incidents"])
            peer = self.peer_encoder(obs["peers"])
            weights = (peer * self.query(own).unsqueeze(1)).sum(-1) / 32**0.5
            weights = weights.masked_fill(~obs["peer_mask"], -1e9).softmax(-1) * obs["peer_mask"]
            weights = weights / weights.sum(-1, keepdim=True).clamp_min(1e-8)
            peer_summary = (peer * weights.unsqueeze(-1)).sum(1)
            mask = obs["incident_mask"].unsqueeze(-1)
            inc_summary = (inc * mask).sum(1) / mask.sum(1).clamp_min(1)
            hidden = self.gru(torch.cat([own, inc_summary, peer_summary], dim=-1), hidden)
            scores = (inc * self.incident_query(hidden).unsqueeze(1)).sum(-1) / 48**0.5 + self.incident_bias(
                inc
            ).squeeze(-1)
            logits = torch.cat([self.base_actions(hidden), scores], -1).masked_fill(~obs["mask"], -1e9)
            distribution = Categorical(logits=logits)
            if central is None:
                central = torch.zeros((*hidden.shape[:-1], 12), device=hidden.device)
            value = self.critic(torch.cat([hidden, central], -1)).squeeze(-1)
            return distribution, value, hidden

    return RecurrentSwarmPolicy()


def batch_observations(observations, device="cpu"):
    import torch

    return {
        k: torch.as_tensor(np.stack([o[k] for o in observations]), device=device) for k in observations[0]
    }


class PolicyRuntime:
    def __init__(self, path: str | Path):
        import torch

        torch.set_num_threads(2)
        saved = torch.load(path, map_location="cpu", weights_only=True)
        self.model = build_policy().eval()
        self.model.load_state_dict(saved["model"])
        self.metadata = saved.get("metadata", {})
        self.hidden = {}
        self.cached = {}
        self.last_time = -100.0

    def actions(self, sim):
        import torch

        if sim.time < self.last_time:
            self.hidden, self.cached = {}, {}
        if sim.time - self.last_time < 2:
            return self.cached
        ids = sorted(sim.agents)
        obs = batch_observations([observation(sim.agents[k], sim.states[k], sim.time) for k in ids])
        hidden = torch.stack([self.hidden.get(k, torch.zeros(HIDDEN)) for k in ids])
        with torch.inference_mode():
            distribution, _, next_hidden = self.model(obs, hidden)
        actions = distribution.probs.argmax(-1).tolist()
        self.hidden = {k: next_hidden[j] for j, k in enumerate(ids)}
        self.cached = dict(zip(ids, actions))
        self.last_time = sim.time
        return self.cached

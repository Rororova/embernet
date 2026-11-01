"""Supervised perception, behavior cloning, MAPPO-style PPO, and held-out reports."""

import json
import random
import time
from pathlib import Path

import numpy as np

from .contracts import Config


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2), encoding="utf-8")


def train_vision(output, *, samples=1536, epochs=10, seed=210, device=None):
    import torch
    from torch.nn import functional as F

    from .perception import build_network, synthetic_example

    torch.manual_seed(seed)
    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(2)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    training = [synthetic_example(seed + k) for k in range(samples)]
    validation = [synthetic_example(500_000 + k) for k in range(256)]

    def tensors(dataset):
        return [torch.from_numpy(np.stack([item[k] for item in dataset])).to(device) for k in range(3)]

    x, y, severity = tensors(training)
    vx, vy, vs = tensors(validation)
    model = build_network().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=0.002)
    weights = torch.tensor([10.0, 30.0, 30.0], device=device).reshape(1, 3, 1, 1)
    history = []
    for epoch in range(epochs):
        model.train()
        order = torch.randperm(samples, device=device)
        losses = []
        for batch in order.split(48):
            logits, predicted = model(x[batch])
            bce = F.binary_cross_entropy_with_logits(logits, y[batch], pos_weight=weights)
            probs = logits.sigmoid()
            dice = (
                1
                - (
                    (2 * (probs * y[batch]).sum((0, 2, 3)) + 1)
                    / (probs.sum((0, 2, 3)) + y[batch].sum((0, 2, 3)) + 1)
                ).mean()
            )
            fire_mask = y[batch, :1]
            severity_loss = (
                (predicted - severity[batch]).abs() * fire_mask
            ).sum() / fire_mask.sum().clamp_min(1)
            loss = bce + dice + severity_loss * 0.7
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        model.eval()
        with torch.inference_mode():
            logits, predicted = model(vx)
            masks = logits.sigmoid() > 0.55
            truth = vy > 0.5
            intersection = (masks & truth).sum((0, 2, 3)).float()
            union = (masks | truth).sum((0, 2, 3)).float().clamp_min(1)
            iou = (intersection / union).tolist()
            mae = (((predicted - vs).abs() * vy[:, :1]).sum() / vy[:, :1].sum().clamp_min(1)).item()
        row = {
            "epoch": epoch + 1,
            "loss": float(np.mean(losses)),
            "iou": dict(zip(("fire", "person", "animal"), iou)),
            "severity_mae": mae,
        }
        history.append(row)
        print(f"vision epoch {epoch + 1}/{epochs}: {row}", flush=True)
    metadata = {
        "kind": "synthetic RGB/thermal segmentation and severity",
        "seed": seed,
        "samples": samples,
        "validation_samples": 256,
        "epochs": epochs,
        "device": device,
        "seconds": round(time.monotonic() - started, 2),
        "metrics": history[-1],
        "limitations": "Procedural paired images only. No field validation or calibrated thermal physics.",
    }
    torch.save(
        {"model": {k: v.cpu() for k, v in model.state_dict().items()}, "metadata": metadata},
        output / "vision.pt",
    )
    write_json(output / "vision-report.json", {"metadata": metadata, "history": history})
    return metadata


def scenario(seed, stage=4):
    from .simulation import Simulation

    c = Config(seed=seed, packet_loss=[0, 0.03, 0.05, 0.08, 0.2][min(stage, 4)], horizon=180)
    sim = Simulation(c, scenario="empty")
    rng = random.Random(seed)
    for _ in range(1 if stage == 0 else rng.randint(2, 4)):
        sim.add_fire(rng.uniform(35, 285), rng.uniform(45, 270), rng.uniform(0.3, 0.95), rng.uniform(3, 8))
    if stage >= 2:
        fire = sim.fires[-1]
        sim.add_subject(fire.x + 3, fire.y + 2, "person")
        sim.add_subject(rng.uniform(40, 280), rng.uniform(80, 270), "animal")
    if stage >= 3:
        for state in sim.states.values():
            state.water *= rng.uniform(0.35, 1)
            state.battery = rng.uniform(0.45, 1)
    return sim


def score(sim):
    m = sim.metrics
    return (
        m["contained"] * 9
        + m["survivor_responses"] * 18
        - m["water_used"] * 0.025
        - m["safety_interventions"] * 0.08
        - m["burned_proxy"] * 0.25
        - m["collisions"] * 4
    )


def evaluate_policy(model, seeds, *, steps=75, device="cpu"):
    import torch

    from .learning import HIDDEN, batch_observations, observation

    results = []
    for seed in seeds:
        pair = {}
        for mode in ("baseline", "learned"):
            sim = scenario(seed)
            hidden = torch.zeros(sim.c.drones, HIDDEN, device=device)
            model.eval()
            for k in range(steps):
                actions = None
                if mode == "learned":
                    ids = sorted(sim.agents)
                    obs = batch_observations(
                        [observation(sim.agents[i], sim.states[i], sim.time) for i in ids], device
                    )
                    with torch.inference_mode():
                        distribution, _, hidden = model(obs, hidden)
                    actions = dict(zip(ids, distribution.probs.argmax(-1).tolist()))
                if 20 <= k < 30:
                    sim.mesh.isolated = {"E03"}
                else:
                    sim.mesh.isolated = set()
                sim.step(4, actions)
            pair[mode] = dict(seed=seed, score=round(score(sim), 3), **sim.metrics)
        results.append(pair)
    return results


def train_mission(
    output, *, demonstrations=12, bc_epochs=10, updates=12, rollout_steps=56, seed=310, device=None
):
    import torch
    from torch.nn import functional as F

    from .learning import HIDDEN, batch_observations, build_policy, observation

    device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    torch.set_num_threads(2)
    torch.manual_seed(seed)
    np.random.seed(seed)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    model = build_policy().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-4)
    demonstrations_data = []
    for episode in range(demonstrations):
        sim = scenario(seed + episode, episode % 5)
        for _ in range(60):
            for key, agent in sim.agents.items():
                obs = observation(agent, sim.states[key], sim.time)
                action = agent.expert_action(sim.states[key], sim.time)
                if obs["mask"][action]:
                    demonstrations_data.append((obs, action))
            sim.step(4)
    observations = batch_observations([item[0] for item in demonstrations_data], device)
    labels = torch.tensor([item[1] for item in demonstrations_data], device=device)
    bc_history = []
    for epoch in range(bc_epochs):
        losses = []
        for indices in torch.randperm(len(labels), device=device).split(256):
            batch = {key: value[indices] for key, value in observations.items()}
            distribution, _, _ = model(batch, torch.zeros(len(indices), HIDDEN, device=device))
            loss = F.nll_loss(distribution.logits, labels[indices])
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
            optimizer.step()
            losses.append(loss.item())
        bc_history.append(float(np.mean(losses)))
    print(f"mission behavior cloning: {len(labels)} decisions, final loss {bc_history[-1]:.4f}", flush=True)
    torch.save(
        {
            "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
            "metadata": {"phase": "demonstration warm-start", "seed": seed},
        },
        output / "mission-bc.pt",
    )
    history = []
    best_score = -float("inf")
    for update in range(updates):
        stage = min(4, update * 5 // max(updates, 1))
        sim = scenario(seed + 1000 + update, stage)
        n = sim.c.drones
        hidden = torch.zeros(n, HIDDEN, device=device)
        rollout = []
        model.eval()
        for tick in range(rollout_steps):
            ids = sorted(sim.agents)
            obs = batch_observations(
                [observation(sim.agents[key], sim.states[key], sim.time) for key in ids], device
            )
            central = torch.from_numpy(np.repeat(sim.central_state()[None], n, axis=0)).to(device)
            with torch.no_grad():
                distribution, values, next_hidden = model(obs, hidden, central)
                actions = distribution.sample()
                logs = distribution.log_prob(actions)
            before = score(sim)
            if stage == 4:
                sim.mesh.isolated = {"E03"} if 18 <= tick < 28 else set()
            sim.step(4, dict(zip(ids, actions.tolist())))
            reward = score(sim) - before - 0.008
            rollout.append(
                {
                    "obs": obs,
                    "central": central,
                    "hidden": hidden.detach(),
                    "action": actions,
                    "log": logs,
                    "value": values,
                    "reward": torch.full((n,), reward, device=device),
                }
            )
            hidden = next_hidden.detach()
        with torch.no_grad():
            obs = batch_observations(
                [observation(sim.agents[key], sim.states[key], sim.time) for key in ids], device
            )
            central = torch.from_numpy(np.repeat(sim.central_state()[None], n, axis=0)).to(device)
            _, next_value, _ = model(obs, hidden, central)
        advantage = torch.zeros(n, device=device)
        advantages, returns = [], []
        for transition in reversed(rollout):
            delta = transition["reward"] + 0.99 * next_value - transition["value"]
            advantage = delta + 0.99 * 0.95 * advantage
            advantages.insert(0, advantage)
            returns.insert(0, advantage + transition["value"])
            next_value = transition["value"]
        flat_obs = {key: torch.cat([t["obs"][key] for t in rollout]) for key in rollout[0]["obs"]}
        flat = {
            key: torch.cat([t[key] for t in rollout])
            for key in ("central", "hidden", "action", "log", "value")
        }
        adv, target = torch.cat(advantages), torch.cat(returns)
        adv = (adv - adv.mean()) / adv.std().clamp_min(1e-6)
        model.train()
        for _ in range(3):
            for ix in torch.randperm(len(adv), device=device).split(192):
                distribution, value, _ = model(
                    {key: v[ix] for key, v in flat_obs.items()}, flat["hidden"][ix], flat["central"][ix]
                )
                ratio = (distribution.log_prob(flat["action"][ix]) - flat["log"][ix]).exp()
                actor = -torch.minimum(ratio * adv[ix], ratio.clamp(0.8, 1.2) * adv[ix]).mean()
                critic = F.mse_loss(value, target[ix])
                # Keep a small demonstration anchor during the short initial RL run.
                expert_ix = torch.randint(len(labels), (64,), device=device)
                expert, _, _ = model(
                    {key: value[expert_ix] for key, value in observations.items()},
                    torch.zeros(64, HIDDEN, device=device),
                )
                imitation = F.nll_loss(expert.logits, labels[expert_ix])
                loss = actor + 0.25 * critic - 0.015 * distribution.entropy().mean() + 0.12 * imitation
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.parameters(), 0.5)
                optimizer.step()
        row = {"update": update + 1, "curriculum_stage": stage, "rollout_score": round(score(sim), 3)}
        history.append(row)
        print(f"mission {row}", flush=True)
        # Select on validation scenarios only. Held-out evaluation uses different seeds below.
        if (update + 1) % 4 == 0 or update == updates - 1:
            validation = evaluate_policy(model, [61_001, 61_002], steps=60, device=device)
            value = float(np.mean([r["learned"]["score"] for r in validation]))
            if value > best_score:
                best_score = value
                torch.save(
                    {
                        "model": {k: v.detach().cpu() for k, v in model.state_dict().items()},
                        "metadata": {
                            "seed": seed,
                            "phase": "BC then clipped PPO",
                            "update": update + 1,
                            "validation_score": best_score,
                            "sensor_mode": "reference sensor (oracle)",
                        },
                    },
                    output / "mission.pt",
                )
    selected = torch.load(output / "mission.pt", map_location=device, weights_only=True)
    model.load_state_dict(selected["model"])
    evaluation = evaluate_policy(model, [91_001, 91_002, 91_003, 91_004], device=device)
    report = {
        "seed": seed,
        "device": device,
        "demonstrations": len(labels),
        "bc_loss": bc_history,
        "updates": history,
        "selected": selected["metadata"],
        "held_out": evaluation,
        "baseline_mean": float(np.mean([r["baseline"]["score"] for r in evaluation])),
        "learned_mean": float(np.mean([r["learned"]["score"] for r in evaluation])),
        "limitations": "Initial small synthetic experiment; recurrent actor uses stored hidden states with one-step truncated gradients. Mission training uses reference detections; learned-vision deployment must be evaluated separately.",
    }
    report["outperforms_baseline"] = report["learned_mean"] > report["baseline_mean"]
    write_json(output / "mission-report.json", report)
    return report

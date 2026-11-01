"""Isaac-free rehearsal: a rate-limited point mass stands in for PX4/PhysX in tests only."""

from .swarm_mission import TICK_SECONDS, SwarmMission

XY_SPEED, UP_SPEED, DOWN_SPEED = 8.0, 4.0, 3.0


def fly(position, target, dt):
    dx, dy = target[0] - position[0], target[1] - position[1]
    horizontal = (dx * dx + dy * dy) ** 0.5
    step = min(horizontal, XY_SPEED * dt)
    ratio = step / horizontal if horizontal else 0.0
    dz = target[2] - position[2]
    climb = min(dz, UP_SPEED * dt) if dz > 0 else max(dz, -DOWN_SPEED * dt)
    return (position[0] + dx * ratio, position[1] + dy * ratio, position[2] + climb)


def rehearse(drones=6, *, policy=None, seed=41, limit=400.0, arm_time=12.0, sink=None, script=True):
    mission = SwarmMission(drones, policy=policy, seed=seed, sink=sink, script=script)
    positions = {key: tuple(home) for key, home in mission.homes.items()}
    time = 0.0
    while time < limit and mission.completed_at is None:
        armed = dict.fromkeys(positions, time >= arm_time)
        targets = mission.tick(time, positions, armed)
        if time >= arm_time:
            positions = {key: fly(value, targets[key], TICK_SECONDS) for key, value in positions.items()}
        time = round(time + TICK_SECONDS, 3)
    return mission

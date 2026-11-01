"""Wildland scenario inputs for the live loop, in mission coordinates with the pad at z=0."""

from .wildland_terrain import IGNITION, MISSION_ORIGIN, mission_ground

# Ten times the city cruise. A 240 m box cannot fit the run-up, so measured peaks are lower.
CRUISE_SPEED = 80.0
PX4_LIMITS = {
    "MPC_XY_VEL_MAX": CRUISE_SPEED,
    "MPC_XY_CRUISE": CRUISE_SPEED,
    "MPC_Z_VEL_MAX_UP": 12,
    "MPC_Z_VEL_MAX_DN": 6,
    "MPC_TILTMAX_AIR": 55,
    "MPC_ACC_HOR": 12,
    "MPC_ACC_HOR_MAX": 12,
    "MPC_JERK_AUTO": 30,
    "MPC_XY_P": 0.5,
    "FD_FAIL_P": 80,
    "FD_FAIL_R": 80,
}

FIRE_XY = (IGNITION[0] - MISSION_ORIGIN[0], IGNITION[1] - MISSION_ORIGIN[1])
SMALL_FIRE_XY = (162.0, 106.0)
SURVIVOR_XY = (172.0, 132.0)


def _on_ground(x, y, lift):
    return (float(x), float(y), mission_ground(x, y) + lift)


def scenario():
    """Same map layout as the city mission; every incident sits on the local ground."""
    return {
        "obstacles": (),
        "speed": CRUISE_SPEED,
        "fire_position": _on_ground(*FIRE_XY, 1.0),
        "small_fire_position": _on_ground(*SMALL_FIRE_XY, 1.0),
        "survivor_position": _on_ground(*SURVIVOR_XY, 1.0),
    }


fire_ground = _on_ground(*FIRE_XY, 2.0)
WILDLAND_VIEWS = {
    "bird": ((120.0, 110.0, 290.0), (120.0, 111.0, 0.0)),
    "overview": ((250.0, -70.0, 120.0), (120.0, 120.0, 10.0)),
    "fire": ((FIRE_XY[0] + 42.0, FIRE_XY[1] - 62.0, fire_ground[2] + 30.0), fire_ground),
}


def prepare_render():
    """Ambient occlusion and bounced light keep the canopy from reading as black shapes."""
    import carb

    settings = carb.settings.get_settings()
    settings.set_bool("/rtx/ambientOcclusion/enabled", True)
    settings.set_bool("/rtx/indirectDiffuse/enabled", True)
    # Fractional cutout is what lets the soft sprite materials in effects.py blend.
    settings.set_bool("/rtx/raytracing/fractionalCutoutOpacity", True)
    settings.set_bool("/rtx/translucency/enabled", True)

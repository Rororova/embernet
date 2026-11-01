import numpy as np
import pytest

from embernet.isaac.effects import FLOW_TUNING, billboard, flow_fuel, flow_spheres


@pytest.mark.parametrize("eye", [(40, -60, 12), (-30, 25, 3), (0, 0, 90), (0.0, 0.0, -50)])
def test_billboard_faces_the_camera_from_any_side_without_mirroring(eye):
    matrix = billboard((0, 0, 0), eye, (2.0, 1.0, 3.0))
    right, away, up = matrix[0, :3], matrix[1, :3], matrix[2, :3]
    toward = np.asarray(eye, float) / np.linalg.norm(eye)
    assert -away == pytest.approx(toward)
    assert np.linalg.norm(right) == pytest.approx(2.0) and np.linalg.norm(up) == pytest.approx(3.0)
    assert right @ toward == pytest.approx(0.0, abs=1e-9)
    assert np.linalg.det(matrix[:3, :3]) > 0


def test_billboard_keeps_sprite_position():
    assert billboard((3, -4, 5), (9, 9, 9))[3, :3] == pytest.approx((3, -4, 5))


def test_flow_emitters_span_the_fire_along_the_facade():
    spheres, radius = flow_spheres((150, 134, 104.4), 11.0, (0, -2, 0))
    xs = [s[0] for s in spheres]
    assert len(spheres) == 4 and 0.8 <= radius <= 2.4
    assert sum(xs) / len(xs) == pytest.approx(150)
    assert all(s[1:] == pytest.approx((132, 104.4)) for s in spheres)
    assert max(xs) + radius - (min(xs) - radius) == pytest.approx(11.0)


def test_small_fire_is_one_emitter_and_oversize_extent_is_bounded():
    assert len(flow_spheres((0, 0, 1), 2.0)[0]) == 1
    spheres, radius = flow_spheres((0, 0, 1), 500.0)
    assert len(spheres) == 5 and radius <= 2.4


def test_flow_fuel_follows_remaining_fire():
    assert 0 < flow_fuel(0.0) < flow_fuel(0.5) < flow_fuel(1.0) <= 1


def test_flow_tuning_replaces_the_centimetre_preset_scale():
    assert FLOW_TUNING["flowSimulate"]["densityCellSize"] >= 0.2
    gravity = FLOW_TUNING["flowSimulate/advection"]["gravity"]
    assert gravity[2] == pytest.approx(-1.0) and np.hypot(*gravity[:2]) < 0.2

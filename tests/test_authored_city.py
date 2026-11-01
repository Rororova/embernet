from pathlib import Path

import pytest


def test_nvidia_tower_is_composed_in_metres_with_independent_collision_proxy():
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdPhysics

    from embernet.isaac.authored_city import build_authored_city

    root = Path("artifacts/embernet/isaac/nvidia-tower/pack")
    if not root.is_dir():
        pytest.skip("Vendor pack is fetched separately, not redistributed in the project")
    stage = Usd.Stage.CreateInMemory()
    report = build_authored_city(stage, root)
    assert not stage.GetCompositionErrors()
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    bounds = (
        UsdGeom.BBoxCache(0, ["default", "render"])
        .ComputeWorldBound(stage.GetPrimAtPath("/World/Architecture/BaseBuilding"))
        .ComputeAlignedRange()
    )
    assert bounds.GetMax()[2] == pytest.approx(108, abs=0.01)
    assert stage.GetPrimAtPath("/World/TowerCollision").HasAPI(UsdPhysics.CollisionAPI)
    assert report["fire_position"] == [150, 134, 104.4]

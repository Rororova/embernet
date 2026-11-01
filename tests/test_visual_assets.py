import json
import struct

from embernet.simulation import Simulation
from embernet.visual_assets import ASSETS


def test_shared_drone_is_valid_triangle_geometry_with_physical_extent():
    payload = (ASSETS / "drone.glb").read_bytes()
    magic, version, length = struct.unpack("<4sII", payload[:12])
    assert magic == b"glTF" and version == 2 and length == len(payload)
    json_size, kind = struct.unpack("<I4s", payload[12:20])
    document = json.loads(payload[20 : 20 + json_size])
    assert kind == b"JSON" and document["asset"]["version"] == "2.0"
    positions = document["accessors"][0]
    assert positions["count"] > 1000 and positions["count"] % 3 == 0
    assert positions["max"][0] - positions["min"][0] > 4
    assert len(document["meshes"][0]["primitives"]) > 0
    indices = document["accessors"][document["meshes"][0]["primitives"][0]["indices"]]
    assert indices["count"] == positions["count"] and indices["componentType"] == 5125


def test_discharge_visuals_come_from_executed_payload_and_track_water_use():
    sim = Simulation()
    found = False
    for _ in range(100):
        before = sim.metrics["water_used"]
        sim.step()
        discharge = [d["discharge"] for d in sim.snapshot()["drones"] if d["discharge"]]
        if discharge:
            assert sim.metrics["water_used"] > before
            assert all(item["litres_per_second"] > 0 for item in discharge)
            found = True
            break
    assert found

import hashlib
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from embernet.cloud_gateway import create_gateway
from embernet.live_api import LiveHub, create_live_app

CODE = "test-control-code"
HEADERS = {"Authorization": "Bearer " + CODE}


def test_spectator_cannot_mutate_and_operator_commands_are_bounded(tmp_path):
    hub = LiveHub(hashlib.sha256(CODE.encode()).hexdigest(), tmp_path)
    client = TestClient(create_live_app(hub))
    assert client.get("/api/state").status_code == 200
    assert client.post("/api/control", json={"action": "stop"}).status_code == 403
    assert (
        client.post("/api/control", headers=HEADERS, json={"action": "incident", "x": 500}).status_code == 422
    )
    assert hub.queue.empty()
    assert (
        client.post(
            "/api/control", headers=HEADERS, json={"action": "mesh", "drone": "E02", "enabled": False}
        ).status_code
        == 200
    )
    assert hub.queue.get_nowait()["enabled"] is False
    assert client.post("/api/control", headers=HEADERS, json={"action": "stop"}).status_code == 429
    assert client.get("/ui/../../cloud_live.py").status_code == 404
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["phase"] == "Starting Isaac and PX4"
        ws.send_json({"type": "ping", "nonce": 123})
        for _ in range(5):
            message = ws.receive_json()
            if message.get("type") == "pong":
                break
        assert message == {"type": "pong", "nonce": 123}
    assert hub.viewers == 0


def test_one_voucher_allows_one_launch_across_concurrent_requests():
    registry = {
        "config": {"control_hash": hashlib.sha256(CODE.encode()).hexdigest()},
        "ticket": {"valid_until": time.time() + 60, "duration": 60},
    }
    launches = []

    def launch(config, ticket):
        launches.append(ticket)
        time.sleep(0.05)
        return {"url": "https://example.invalid", "expires_at": time.time() + 60, "sandbox_id": "sb-test"}

    client = TestClient(create_gateway(registry, launch, lambda _: True))
    assert client.post("/api/start").status_code == 403
    assert "ticket" in registry
    with ThreadPoolExecutor(4) as pool:
        responses = list(pool.map(lambda _: client.post("/api/start", headers=HEADERS), range(4)))
    assert len(launches) == 1

    assert all(r.status_code in (200, 409) for r in responses)
    assert client.get("/api/session").json()["active"]
    assert client.post("/api/start", headers=HEADERS).status_code == 200
    assert len(launches) == 1


def test_mouse_camera_socket_requires_code_and_rejects_invalid_pose(tmp_path):
    hub = LiveHub(hashlib.sha256(CODE.encode()).hexdigest(), tmp_path)
    client = TestClient(create_live_app(hub))
    with client.websocket_connect("/ws/camera") as ws:
        ws.send_json({"code": CODE})
        ws.send_json(
            {"camera": "fire", "interactive": True, "yaw": 25, "pitch": 40, "distance": 200, "pan_x": 3}
        )
        command = hub.queue.get(timeout=2)
        assert command["action"] == "camera" and command["distance"] == 200
        assert command["interactive"] and command["pan_x"] == 3
        ws.send_json({"distance": -1})
    assert hub.queue.empty()
    with client.websocket_connect("/ws/camera") as ws:
        ws.send_json({"code": "invalid"})
        assert ws.receive()["code"] == 1008


def test_retried_control_is_queued_only_once(tmp_path):
    hub = LiveHub(hashlib.sha256(CODE.encode()).hexdigest(), tmp_path)
    client = TestClient(create_live_app(hub))
    body = {"action": "mesh", "drone": "E02", "enabled": False, "request_id": "same-request"}
    first = client.post("/api/control", headers=HEADERS, json=body)
    second = client.post("/api/control", headers=HEADERS, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert hub.queue.qsize() == 1


def test_persistent_control_acknowledges_auth_and_retries(tmp_path):
    hub = LiveHub(hashlib.sha256(CODE.encode()).hexdigest(), tmp_path)
    client = TestClient(create_live_app(hub))
    with client.websocket_connect("/ws/control") as ws:
        ws.send_json({"code": CODE})
        assert ws.receive_json() == {"type": "authenticated"}
        value = {"action": "mesh", "enabled": False, "request_id": "retry-me"}
        ws.send_json(value)
        first = ws.receive_json()
        ws.send_json(value)
        assert ws.receive_json() == first
        assert first["type"] == "control_ack" and hub.queue.qsize() == 1
        ws.send_json({"type": "ping", "nonce": 123})
        assert ws.receive_json() == {"type": "pong", "nonce": 123}
    assert hub.control_viewers == 0


def test_clicked_fire_is_authenticated_bounded_and_queued_only_once(tmp_path):
    hub = LiveHub(hashlib.sha256(CODE.encode()).hexdigest(), tmp_path)
    client = TestClient(create_live_app(hub))
    body = {"action": "ignite", "u": 0.25, "v": 0.75, "radius": 4, "severity": 0.6, "request_id": "click-1"}
    assert client.post("/api/control", json=body).status_code == 403
    for invalid in ({"u": -0.1}, {"v": 1.01}, {"radius": 11}, {"severity": 0}):
        assert client.post("/api/control", headers=HEADERS, json={**body, **invalid}).status_code == 422
    assert hub.queue.empty()
    first = client.post("/api/control", headers=HEADERS, json=body)
    assert first.status_code == 200
    assert client.post("/api/control", headers=HEADERS, json=body).json() == first.json()
    assert hub.queue.qsize() == 1
    queued = hub.queue.get_nowait()
    assert (queued["action"], queued["u"], queued["v"], queued["radius"]) == ("ignite", 0.25, 0.75, 4)

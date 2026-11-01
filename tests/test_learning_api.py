import torch
from fastapi.testclient import TestClient

from embernet.learning import HIDDEN, batch_observations, build_policy, observation
from embernet.perception import build_network, synthetic_example
from embernet.server import create_app
from embernet.simulation import Simulation


def test_recurrent_actor_handles_empty_mesh_and_masks_without_nan():
    sim = Simulation(scenario="empty")
    observations = [observation(a, sim.states[key], 0) for key, a in sim.agents.items()]
    batch = batch_observations(observations)
    model = build_policy()
    distribution, value, hidden = model(batch, torch.zeros(6, HIDDEN))
    assert torch.isfinite(distribution.probs).all()
    assert torch.isfinite(value).all()
    assert hidden.shape == (6, HIDDEN)
    assert (distribution.probs[:, 4:] == 0).all()


def test_vision_gradients_and_real_image_inputs():
    image, masks, severity = synthetic_example(44)
    model = build_network()
    logits, predicted = model(torch.from_numpy(image[None]))
    loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, torch.from_numpy(masks[None]))
    loss = loss + (predicted - torch.from_numpy(severity[None])).square().mean()
    loss.backward()
    assert model.rgb[0].weight.grad.abs().sum() > 0
    assert model.thermal[0].weight.grad.abs().sum() > 0


def test_mission_api_validation_and_recording(tmp_path):
    with TestClient(create_app(run_dir=str(tmp_path))) as client:
        state = client.get("/api/state").json()
        assert state["paused"] and len(state["drones"]) == 6
        assert client.post("/api/incidents", json={"x": -1, "y": 10}).status_code == 422
        assert client.post("/api/incidents", json={"x": 150, "y": 120}).status_code == 200
        assert client.post("/api/reset", json={"sensor": "learned"}).status_code == 409
        assert client.post("/api/reset", json={"drones": 0}).status_code == 422
        assert client.post("/api/control", json={"action": "loss", "value": 5}).status_code == 422
        assert (
            client.post(
                "/api/control", json={"action": "pause"}, headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert client.get("/api/camera/E01/rgb").headers["content-type"] == "image/png"
        assert client.get("/api/export/rrd").content
        assert client.get("/").status_code == 200
        assert list(tmp_path.glob("*.rrd"))

"""Loopback mission control. Mutations are validated and recorded as operator actions."""

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field
from starlette.middleware.gzip import GZipMiddleware

from .contracts import Config
from .real_perception import CANDIDATE_MODEL
from .simulation import Simulation
from .telemetry import Telemetry


class Control(BaseModel):
    action: str
    value: float | bool | str | None = None


class AddIncident(BaseModel):
    kind: str = "fire"
    x: float = Field(ge=0, le=320)
    y: float = Field(ge=0, le=320)
    severity: float = Field(default=0.6, ge=0.1, le=1)
    radius: float = Field(default=5, ge=1, le=15)


class Reset(BaseModel):
    seed: int = Field(default=41, ge=0, le=1_000_000)
    drones: int = Field(default=6, ge=2, le=16)
    sensor: str = "reference"
    policy: str = "baseline"


def create_app(*, run_dir="artifacts/embernet/demo", models=None, spawn_rerun=False):
    output = Path(run_dir)
    output.mkdir(parents=True, exist_ok=True)
    model_dir = Path(models) if models else None
    state = {"sim": None, "telemetry": None, "paused": True, "speed": 2.0, "recording": None, "error": None}

    def reset(settings):
        from .learning import PolicyRuntime
        from .perception import VisionRuntime

        if settings.sensor not in ("reference", "learned") or settings.policy not in ("baseline", "learned"):
            raise HTTPException(422, "Unknown sensor or policy mode")
        vision = policy = None
        if settings.sensor == "learned":
            if not model_dir or not (model_dir / "vision.pt").exists():
                raise HTTPException(409, "No vision checkpoint. Train or select a model directory first.")
            vision = VisionRuntime(model_dir / "vision.pt")
        if settings.policy == "learned":
            if not model_dir or not (model_dir / "mission.pt").exists():
                raise HTTPException(409, "No mission checkpoint. Train or select a model directory first.")
            policy = PolicyRuntime(model_dir / "mission.pt")
        if state["telemetry"]:
            state["telemetry"].close()
        sim = Simulation(Config(seed=settings.seed, drones=settings.drones), vision=vision, policy=policy)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        recording = output / f"mission-{stamp}.rrd"
        state.update(sim=sim, paused=True, recording=recording, error=None)
        state["telemetry"] = Telemetry(recording, sim, spawn=spawn_rerun)
        state["replay"] = output / f"mission-{stamp}.jsonl"
        state["replay"].write_text(
            json.dumps(
                {
                    "type": "header",
                    "config": asdict(sim.c),
                    "sensor": sim.sensor_mode,
                    "policy": sim.policy_mode,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    async def loop():
        while True:
            if not state["paused"]:
                try:
                    sim = state["sim"]
                    sim.step(1)
                    if round(sim.time / sim.c.dt) % 2 == 0:
                        state["telemetry"].log(sim)
                        with state["replay"].open("a", encoding="utf-8") as stream:
                            stream.write(json.dumps(sim.snapshot()) + "\n")
                except Exception as exc:  # noqa: BLE001 -- Surface runtime failures and stop the mission safely.
                    state["error"], state["paused"] = str(exc), True
            await asyncio.sleep(0.5 / max(0.25, state["speed"]))

    @asynccontextmanager
    async def lifespan(app):
        reset(Reset())
        task = asyncio.create_task(loop())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        state["telemetry"].close()

    app = FastAPI(title="EMBERNET Mission Control", lifespan=lifespan)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.state.mission = state

    @app.middleware("http")
    async def local_mutations(request, call_next):
        # No cross-origin command endpoints; serve only on loopback by default.
        origin = request.headers.get("origin")
        allowed = {f"http://{request.headers.get('host')}", f"https://{request.headers.get('host')}"}
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin not in allowed:
            return Response("Cross-origin mission commands are disabled", status_code=403)
        return await call_next(request)

    @app.get("/api/state")
    async def snapshot():
        return {
            **state["sim"].snapshot(),
            "paused": state["paused"],
            "speed": state["speed"],
            "recording": state["recording"].name,
            "error": state["error"],
            "viewer_error": state["telemetry"].viewer_error,
            "models": {
                "vision": bool(model_dir and (model_dir / "vision.pt").exists()),
                "mission": bool(model_dir and (model_dir / "mission.pt").exists()),
            },
        }

    @app.post("/api/control")
    async def control(command: Control):
        sim = state["sim"]
        if command.action == "pause":
            state["paused"] = True
        elif command.action == "launch":
            if state["error"]:
                raise HTTPException(409, "Reset the mission after an execution error")
            state["paused"] = False
        elif command.action == "speed" and command.value in (1, 2, 4, 8):
            state["speed"] = float(command.value)
        elif command.action == "mesh" and isinstance(command.value, bool):
            sim.mesh.enabled = command.value
        elif command.action == "loss" and isinstance(command.value, (float, int)) and 0 <= command.value <= 1:
            sim.mesh.loss = float(command.value)
        elif command.action == "isolate" and command.value in sim.states:
            if command.value in sim.mesh.isolated:
                sim.mesh.isolated.remove(command.value)
            else:
                sim.mesh.isolated.add(command.value)
        else:
            raise HTTPException(422, "Unknown command or invalid value")
        return {"ok": True}

    @app.post("/api/incidents")
    async def incident(command: AddIncident):
        sim = state["sim"]
        try:
            if command.kind == "fire":
                obj = sim.add_fire(command.x, command.y, command.severity, command.radius)
            else:
                obj = sim.add_subject(command.x, command.y, command.kind)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"id": obj.id}

    @app.post("/api/reset")
    async def new_mission(command: Reset):
        reset(command)
        return {"ok": True}

    @app.get("/api/camera/{drone_id}/{channel}")
    async def camera(drone_id: str, channel: str):
        if drone_id not in state["sim"].states or channel not in ("rgb", "thermal"):
            raise HTTPException(404, "Unknown camera")
        frame = state["sim"].cameras.get(drone_id)
        if frame is None:
            image = Image.new("RGB", (64, 64), (25, 38, 42))
        else:
            pixels = frame[:3].transpose(1, 2, 0) if channel == "rgb" else frame[3]
            image = Image.fromarray((pixels * 255).astype("uint8"))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return Response(buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/api/export/{kind}")
    async def export(kind: str):
        if kind == "rrd":
            state["telemetry"].recording.flush()
            return FileResponse(state["recording"], filename="EMBERNET-mission.rrd")
        if kind == "replay":
            return FileResponse(state["replay"], filename="EMBERNET-replay.jsonl")
        raise HTTPException(404, "Export must be rrd or replay")

    @app.get("/")
    async def index():
        return FileResponse(Path(__file__).parent / "ui" / "index.html")

    evidence = Path("artifacts/embernet/real-perception")
    evidence.mkdir(parents=True, exist_ok=True)
    candidate_evidence = CANDIDATE_MODEL.parent / "flame3"

    @app.get("/perception")
    async def perception_review():
        return FileResponse(Path(__file__).parent / "ui" / "perception.html")

    @app.get("/api/perception")
    async def perception_report():
        use_candidate = (candidate_evidence / "report.json").is_file()
        report = candidate_evidence / "report.json" if use_candidate else evidence / "report.json"
        if not report.exists():
            return {"ready": False, "frames": []}
        payload = json.loads(report.read_text(encoding="utf-8"))
        if use_candidate:
            for frame in payload["frames"]:
                frame["overlay"] = f"candidate/{frame['overlay']}"
                frame["thermal_preview"] = f"candidate/{frame['thermal_preview']}"
        return {"ready": True, **payload}

    if candidate_evidence.is_dir():
        app.mount("/evidence/candidate", StaticFiles(directory=candidate_evidence), name="candidate-evidence")
    app.mount("/evidence", StaticFiles(directory=evidence), name="evidence")

    app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "ui"), name="ui")
    app.mount("/assets", StaticFiles(directory=Path(__file__).parent / "assets"), name="assets")
    return app

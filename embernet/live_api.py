"""Shared-session transport; commands are validated before entering the physics thread."""

import asyncio
import hashlib
import json
import re
import secrets
import threading
import time
from collections import deque
from pathlib import Path
from queue import Full, Queue
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

UI = Path(__file__).parent / "ui"
FRAME_RGB, FRAME_IR = 0, 1


def pack_frame(channel, payload):
    """Prefix one byte so dual-sensor JPEG messages never get confused."""
    if channel not in (FRAME_RGB, FRAME_IR) or not bytes(payload).startswith(b"\xff\xd8"):
        raise ValueError("Invalid sensor frame")
    return bytes([channel]) + bytes(payload)


class PipeCommands:
    def __init__(self, connection):
        self.connection = connection

    def get_nowait(self):
        from queue import Empty

        if not self.connection.poll():
            raise Empty
        return self.connection.recv()


class PhysicsHub:
    """Native-process endpoint; the HTTP process stays responsive during shader work."""

    def __init__(self, connection, output, duration):
        self.connection, self.output = connection, Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.queue, self.deadline = PipeCommands(connection), time.time() + duration
        self.state, self.frame_id = {}, 0

    def snapshot(self):
        return dict(self.state)

    def publish(self, state, jpeg=None, ir_jpeg=None):
        if jpeg is not None:
            self.frame_id += 1
        self.state = dict(state)
        self.connection.send((state, jpeg, ir_jpeg, self.deadline))


def serve_transport(connection, control_hash, output, duration):
    """A separate process, not a Python thread contending with Kit's native GIL holds."""
    import uvicorn

    hub = LiveHub(control_hash, output, duration)

    def receive():
        try:
            while True:
                state, jpeg, ir_jpeg, deadline = connection.recv()
                hub.deadline = deadline
                hub.publish(state, jpeg, ir_jpeg)
        except (EOFError, OSError):
            hub.deadline = time.time()

    def send():
        try:
            while True:
                connection.send(hub.queue.get())
        except (EOFError, OSError):
            return

    def thermal_preview():
        import io

        import numpy as np
        from PIL import Image

        from .isaac.cameras import thermal_frame

        last = -1
        while time.time() < hub.deadline:
            with hub.lock:
                frame, jpeg = hub.frame_id, hub.jpeg
            if jpeg and frame != last:
                with Image.open(io.BytesIO(jpeg)) as image:
                    thermal, _ = thermal_frame(np.asarray(image.convert("RGB")), frame)
                output = io.BytesIO()
                thermal.save(output, format="JPEG", quality=78)
                with hub.lock:
                    hub.ir_jpeg = output.getvalue()
                    hub.ir_frame_id = frame
                thermal.save(hub.output / "latest-ir.jpg")
                last = frame
            time.sleep(0.1)

    from .video_stream import start_encoder

    start_encoder(hub)
    threading.Thread(target=receive, daemon=True).start()
    threading.Thread(target=send, daemon=True).start()
    threading.Thread(target=thermal_preview, daemon=True).start()
    uvicorn.run(
        create_live_app(hub),
        host="0.0.0.0",
        port=8000,
        log_level="warning",
        access_log=False,
        ws_ping_interval=None,
    )


class LiveCommand(BaseModel):
    action: str
    request_id: str = Field(default="", max_length=64)
    kind: str = "fire"
    x: float = Field(default=150, ge=8, le=232, allow_inf_nan=False)
    y: float = Field(default=134, ge=8, le=232, allow_inf_nan=False)
    z: float = Field(default=0, ge=0, le=140, allow_inf_nan=False)
    severity: float = Field(default=0.6, ge=0.1, le=1, allow_inf_nan=False)
    radius: float = Field(default=3, ge=1, le=10, allow_inf_nan=False)
    drone: str = "E02"
    enabled: bool = True
    incident_id: str = ""
    yaw: float = Field(default=0, ge=-360, le=360, allow_inf_nan=False)
    pitch: float = Field(default=24, ge=5, le=80, allow_inf_nan=False)
    distance: float = Field(default=5, ge=2, le=600, allow_inf_nan=False)
    interactive: bool = False
    pan_x: float = Field(default=0, ge=-200, le=200, allow_inf_nan=False)
    pan_y: float = Field(default=0, ge=-200, le=200, allow_inf_nan=False)
    u: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    v: float = Field(default=0.5, ge=0, le=1, allow_inf_nan=False)
    camera: Literal["mission", "follow", "onboard", "bird", "overview", "fire"] = "mission"


class LiveHub:
    def __init__(self, control_hash, output, duration=600):
        self.control_hash, self.output = control_hash, Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.queue = Queue(maxsize=64)
        self.lock = threading.Lock()
        self.deadline = time.time() + duration
        self.state = {
            "phase": "Starting Isaac and PX4",
            "time": 0,
            "remaining_seconds": duration,
            "drones": [],
            "incidents": [],
            "events": [],
            "frame": 0,
            "paused": False,
        }
        self.jpeg, self.ir_jpeg = b"", b""
        self.ir_frame_id = 0
        self.frame_id, self.viewers, self.sequence = 0, 0, 0
        self.last_command = 0.0
        self.last_camera = 0.0
        self.requests = {}
        self.control_viewers = 0
        self.video_packets = deque(maxlen=60)
        self.video_sequence = 0
        self.video_codec = "avc1.42c01f"
        self.video_error = ""
        self.command_lock = threading.Lock()

    def authorized(self, authorization):
        candidate = (authorization or "").removeprefix("Bearer ")
        digest = hashlib.sha256(candidate.encode()).hexdigest()
        return bool(candidate) and secrets.compare_digest(digest, self.control_hash)

    def publish(self, state, jpeg=None, ir_jpeg=None):
        with self.lock:
            if jpeg is not None:
                self.jpeg = jpeg
                if ir_jpeg is not None:
                    self.ir_jpeg = ir_jpeg
                    self.ir_frame_id += 1
                self.frame_id += 1
            self.state = dict(
                state, frame=self.frame_id, remaining_seconds=max(0, self.deadline - time.time())
            )

    def snapshot(self):
        with self.lock:
            return dict(self.state, remaining_seconds=max(0, self.deadline - time.time()))

    def submit(self, command):
        with self.command_lock:
            return self._submit(command)

    def _submit(self, command):
        if command.request_id and command.request_id in self.requests:
            return self.requests[command.request_id]
        now = time.monotonic()
        previous = self.last_camera if command.action == "camera" else self.last_command
        if now - previous < (0.04 if command.action == "camera" else 0.12):
            raise HTTPException(429, "Please wait a moment before the next action")
        if time.time() >= self.deadline:
            raise HTTPException(410, "This shared session has ended")
        actions = {"pause", "resume", "incident", "ignite", "resolve", "mesh", "camera", "stop"}
        if command.action not in actions or command.kind not in ("fire", "person"):
            raise HTTPException(422, "Unknown control")
        if not re.fullmatch(r"E0[1-8]", command.drone) or command.camera not in (
            "mission",
            "follow",
            "onboard",
            "bird",
            "overview",
            "fire",
        ):
            raise HTTPException(422, "Unknown aircraft or camera")
        self.sequence += 1
        value = dict(command.model_dump(), sequence=self.sequence, wall_time=time.time())
        try:
            self.queue.put_nowait(value)
        except Full as exc:
            raise HTTPException(429, "The simulation is catching up; try again") from exc
        if command.action == "camera":
            self.last_camera = now
        else:
            self.last_command = now
        result = {"sequence": self.sequence, "status": "queued"}
        if command.request_id:
            self.requests[command.request_id] = result
            if len(self.requests) > 256:
                self.requests.pop(next(iter(self.requests)))
        return result


def create_live_app(hub):
    app = FastAPI(title="EMBERNET shared physics session")

    async def control_stream(ws, camera_only):
        await ws.accept()
        with hub.lock:
            full = hub.control_viewers >= 4
            if not full:
                hub.control_viewers += 1
        if full:
            await ws.close(code=1013, reason="Four control connections are already open")
            return
        try:
            auth = await asyncio.wait_for(ws.receive_json(), timeout=30)
            if not hub.authorized("Bearer " + str(auth.get("code", ""))):
                await ws.close(code=1008)
                return
            await ws.send_json({"type": "authenticated"})
            while True:
                value = await ws.receive_json()
                if value.get("type") == "ping":
                    await ws.send_json({"type": "pong", "nonce": value.get("nonce")})
                    continue
                if camera_only:
                    value["action"] = "camera"
                try:
                    result = hub.submit(LiveCommand(**value))
                    await ws.send_json(
                        dict(result, type="control_ack", request_id=value.get("request_id", ""))
                    )
                except (ValueError, HTTPException) as error:
                    await ws.send_json(
                        {
                            "type": "control_error",
                            "request_id": value.get("request_id", ""),
                            "detail": error.detail
                            if isinstance(error, HTTPException)
                            else "Check command values",
                        }
                    )
        except WebSocketDisconnect:
            pass
        except TimeoutError:
            await ws.close(code=1008, reason="Control authentication timed out")
        finally:
            with hub.lock:
                hub.control_viewers -= 1

    @app.websocket("/ws/camera")
    async def camera_controls(ws: WebSocket):
        await control_stream(ws, True)

    @app.websocket("/ws/control")
    async def mission_controls(ws: WebSocket):
        await control_stream(ws, False)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.get("/")
    def index():
        return FileResponse(UI / "cloud.html", headers={"Cache-Control": "no-store"})

    @app.get("/ui/{name:path}")
    def static(name):
        target = (UI / name).resolve()
        if not target.is_relative_to(UI.resolve()) or not target.is_file():
            raise HTTPException(404)
        return FileResponse(target, headers={"Cache-Control": "no-store"})

    @app.get("/api/state")
    def state():
        return hub.snapshot()

    @app.get("/api/session")
    def session():
        return {"active": True, "url": "", "has_ticket": False, "expires_at": hub.deadline}

    @app.get("/api/auth")
    def auth(authorization: str | None = Header(default=None)):
        return {"control": hub.authorized(authorization)}

    @app.post("/api/control")
    def control(value: LiveCommand, authorization: str | None = Header(default=None)):
        if not hub.authorized(authorization):
            raise HTTPException(403, "A control invite is required")
        return hub.submit(value)

    @app.websocket("/ws")
    async def updates(ws: WebSocket):
        await ws.accept()
        with hub.lock:
            full = hub.viewers >= 8
            if not full:
                hub.viewers += 1
        if full:
            await ws.close(code=1013, reason="This shared session has eight viewers")
            return
        try:

            async def heartbeats():
                try:
                    while True:
                        message = await ws.receive_json()
                        if message.get("type") == "ping":
                            await ws.send_json({"type": "pong", "nonce": message.get("nonce")})
                except WebSocketDisconnect:
                    return

            heartbeat_task = asyncio.create_task(heartbeats())
            last, last_ir, last_state = -1, -1, 0.0
            video = ws.query_params.get("video") == "h264"
            video_last = 0
            video_config = False
            last_ir_time = 0.0
            while time.time() < hub.deadline:
                if time.monotonic() - last_state >= 0.1:
                    await ws.send_text(json.dumps(hub.snapshot()))
                    last_state = time.monotonic()
                with hub.lock:
                    frame, jpeg, ir_jpeg, ir_frame = hub.frame_id, hub.jpeg, hub.ir_jpeg, hub.ir_frame_id
                if video:
                    with hub.lock:
                        packets = [p for p in hub.video_packets if p[0] > video_last]
                        codec, error = hub.video_codec, hub.video_error
                    if error:
                        await ws.send_json({"type": "video_error", "detail": error})
                        return
                    if not video_config and packets:
                        await ws.send_json(
                            {"type": "video_config", "codec": codec, "width": 960, "height": 540}
                        )
                        video_config = True
                    if video_last == 0 or len(packets) > 8:
                        keys = [i for i, p in enumerate(packets) if p[1]]
                        packets = packets[keys[-1] :] if keys else []
                    for sequence, key, payload in packets:
                        await ws.send_bytes(payload)
                        video_last = sequence
                elif frame != last and jpeg:
                    await ws.send_bytes(pack_frame(FRAME_RGB, jpeg))
                    last = frame
                if ir_jpeg and ir_frame != last_ir and time.monotonic() - last_ir_time >= 0.5:
                    await ws.send_bytes(pack_frame(FRAME_IR, ir_jpeg))
                    last_ir = ir_frame
                    last_ir_time = time.monotonic()
                await asyncio.sleep(0.01)
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            with hub.lock:
                hub.viewers -= 1

    return app

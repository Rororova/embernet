"""Small persistent front door; one atomic voucher bounds shared GPU launches."""

import hashlib
import secrets
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse

from .live_api import UI


def create_gateway(registry, launch, alive):
    app = FastAPI(title="EMBERNET cloud")

    def config():
        value = registry.get("config")
        if value is None:
            raise HTTPException(503, "The host has not prepared a session yet")
        return value

    def auth(header):
        candidate = (header or "").removeprefix("Bearer ")
        return bool(candidate) and secrets.compare_digest(
            hashlib.sha256(candidate.encode()).hexdigest(), config()["control_hash"]
        )

    def current():
        active = registry.get("active")
        if active and time.time() < active["expires_at"] and alive(active):
            return active
        return None

    @app.get("/")
    def index():
        return FileResponse(UI / "cloud.html", headers={"Cache-Control": "no-store"})

    @app.get("/ui/{name:path}")
    def static(name):
        path = (UI / name).resolve()
        if not path.is_relative_to(UI.resolve()) or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, headers={"Cache-Control": "no-store"})

    @app.get("/api/auth")
    def authorization(authorization: str | None = Header(default=None)):
        return {"control": auth(authorization)}

    @app.get("/api/session")
    def status():
        value = current()
        return (
            dict(value, active=True, has_ticket=False)
            if value
            else {"active": False, "has_ticket": registry.get("ticket") is not None}
        )

    @app.post("/api/start")
    def start(world: str = "", authorization: str | None = Header(default=None)):
        if not auth(authorization):
            raise HTTPException(403, "A control invite is required to start the shared swarm")
        if world not in ("", "city", "wildland"):
            raise HTTPException(422, "Choose the city or wildland world")
        active = current()
        if active:
            return dict(active, active=True)
        ticket = registry.pop("ticket", None)
        if ticket is None:
            raise HTTPException(409, "The host must authorize another bounded session")
        if time.time() > ticket["valid_until"]:
            raise HTTPException(410, "This session authorization has expired")
        # The atomic pop occurs before allocation. Failure never grants an automatic retry.
        active = dict(launch(dict(config(), world=world or config().get("world", "city")), ticket))
        registry["active"] = active
        return dict(active, active=True)

    return app

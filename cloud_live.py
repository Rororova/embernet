"""Deploy the CPU front door; grant exactly one shared, bounded GPU session."""

import modal

from cloud_px4 import px4_base_image

app = modal.App("embernet-live")
registry = modal.Dict.from_name("embernet-shared-control", create_if_missing=True)
volume = modal.Volume.from_name("embernet-live-logs", create_if_missing=True)
live_image = (
    px4_base_image.apt_install("ffmpeg")
    .pip_install("fastapi==0.115.12", "uvicorn==0.34.2", "websockets==15.0.1")
    .add_local_dir("artifacts/embernet/isaac/assets", "/opt/embernet-assets", copy=True)
    .add_local_dir("artifacts/embernet/isaac/nvidia-tower/pack", "/opt/nvidia-tower", copy=True)
    .add_local_file("artifacts/embernet/embernet-v2/mission.pt", "/opt/mission.pt", copy=True)
    .add_local_dir("embernet", "/root/embernet", copy=True)
    .env(
        {
            "PYTHONPATH": "/root",
            "PYTHONUNBUFFERED": "1",
            "ACCEPT_EULA": "Y",
            "PRIVACY_CONSENT": "N",
            "EMBERNET_NVIDIA_LICENSE_ACKNOWLEDGED": "YES",
            "XDG_RUNTIME_DIR": "/tmp/embernet-xdg",
        }
    )
)
gateway_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("fastapi==0.115.12")
    .add_local_python_source("embernet")
    .add_local_dir("embernet/ui", "/root/embernet/ui")
)


@app.function(
    image=gateway_image,
    cpu=0.25,
    memory=512,
    timeout=120,
    max_containers=1,
    scaledown_window=2,
    serialized=True,
)
@modal.concurrent(max_inputs=32)
@modal.asgi_app()
def gateway():
    import time

    from embernet.cloud_gateway import create_gateway

    registry = modal.Dict.from_name("embernet-shared-control")

    def alive(active):
        try:
            return modal.Sandbox.from_id(active["sandbox_id"]).poll() is None
        except modal.exception.NotFoundError:
            return False

    def launch(config, ticket):
        import uuid

        from embernet.cloud_resources import rendering_resources

        resources = rendering_resources(config.get("gpu", "L40S"))

        volume = modal.Volume.from_name("embernet-live-logs", create_if_missing=True)

        # The name is also a provider-side single-world constraint across CPU restarts.
        run_id = "live-" + uuid.uuid4().hex[:12]
        duration = ticket["duration"]
        sandbox = modal.Sandbox.create(
            "python",
            "-m",
            "embernet.isaac.city_live",
            "--run-id",
            run_id,
            "--duration",
            str(duration),
            "--world",
            config.get("world", "city"),
            "--render-hz",
            # Capture and encoding cost starves physics at 15 Hz on this scene.
            "5" if config.get("world") == "wildland" else "15",
            app=modal.App.lookup("embernet-live"),
            name="shared-swarm",
            image=modal.Image.from_id(config["image_id"]),
            gpu=resources["gpu"],
            cpu=resources["cpu"],
            memory=resources["memory"],
            timeout=duration + 60,
            encrypted_ports=[8000],
            volumes={
                "/runs": volume,
                "/opt/nvidia-wildland": modal.Volume.from_name("embernet-wildland-assets"),
            },
            env={"EMBERNET_CONTROL_HASH": config["control_hash"]},
        )
        tunnel = sandbox.tunnels()[8000]
        return {
            "sandbox_id": sandbox.object_id,
            "run_id": run_id,
            "url": tunnel.url.rstrip("/"),
            "expires_at": time.time() + duration + 60,
        }

    return create_gateway(registry, launch, alive)


@app.local_entrypoint()
def main(duration: int = 600, rotate: bool = False, gpu: str = "RTX-PRO-6000", world: str = "city"):
    import os

    profile = os.environ.get("MODAL_PROFILE")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Set MODAL_PROFILE to the account whose free credit should be checked")
    import hashlib
    import json
    import secrets
    import subprocess
    import sys
    import time
    from pathlib import Path

    from embernet.cloud_resources import credit_reserve, rendering_resources, require_free_credits

    if world not in ("city", "wildland"):
        raise ValueError("Choose the city or wildland world")
    resources = rendering_resources(gpu)
    reserve = credit_reserve(gpu, duration)

    if not 30 <= duration <= 1200:
        raise ValueError("Session duration must be 30–1200 seconds")
    active = registry.get("active")
    if active and modal.Sandbox.from_id(active["sandbox_id"]).poll() is None:
        raise RuntimeError("Finish the active shared session before issuing another voucher")
    summary = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--profile", profile, "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=45,
        ).stdout
    )
    require_free_credits(summary, reserve)
    root = Path("artifacts/embernet/cloud")
    root.mkdir(parents=True, exist_ok=True)
    private = root / "control-invite.private.json"
    previous = json.loads(private.read_text()) if private.exists() and not rotate else None
    code = previous["control_code"] if previous else secrets.token_urlsafe(24)
    built = live_image.build(app)
    url = modal.Function.from_name("embernet-live", "gateway").get_web_url()
    registry["config"] = {
        "image_id": built.object_id,
        "control_hash": hashlib.sha256(code.encode()).hexdigest(),
        "gpu": gpu,
        "world": world,
    }
    registry["ticket"] = {"duration": duration, "valid_until": time.time() + 86400}
    private.write_text(
        json.dumps(
            {"watch_url": url, "control_url": url + "/#control=" + code, "control_code": code}, indent=2
        )
    )
    (root / "deployment.json").write_text(
        json.dumps(
            {
                "watch_url": url,
                "profile": profile,
                "image_id": built.object_id,
                "session_seconds": duration,
                "single_use_ticket": True,
                "voucher_expires_at": time.time() + 86400,
                "billing": summary,
                "rendering_resources": resources,
                "credit_reserve_usd": reserve,
            },
            indent=2,
        )
    )
    print(
        json.dumps(
            {
                "watch_url": url,
                "private_invite": str(private),
                "session_seconds": duration,
                "gpu_running": False,
            },
            indent=2,
        )
    )

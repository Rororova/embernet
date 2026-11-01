"""Bounded CPU-only isolation of actual encrypted-tunnel control and image transport."""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

import modal
import websockets

from embernet.cloud_resources import require_free_credits

SERVER = r"""
import hashlib,os,threading,time,uvicorn
from pathlib import Path
from embernet.live_api import LiveHub,create_live_app
hub=LiveHub(os.environ['PROBE_HASH'],'/tmp/probe',120)
jpeg=Path('/tmp/probe.jpg').read_bytes()
def produce():
    while time.time()<hub.deadline:
        while not hub.queue.empty():
            value=hub.queue.get_nowait()
            hub.state['camera']=value
        hub.publish(dict(hub.state),jpeg)
        time.sleep(1/30)
if os.environ.get('PROBE_VIDEO')=='1':
    from embernet.video_stream import start_encoder
    start_encoder(hub)
threading.Thread(target=produce,daemon=True).start()
uvicorn.run(create_live_app(hub),host='0.0.0.0',port=8000,log_level='warning',ws_ping_interval=None,timeout_keep_alive=60)
"""


async def check(url, code, video=False):
    started = time.monotonic()
    async with websockets.connect(
        url.replace("https://", "wss://") + "/ws/control", compression=None, open_timeout=40
    ) as ws:
        handshake = time.monotonic() - started
        await ws.send(json.dumps({"code": code}))
        auth = await asyncio.wait_for(ws.recv(), 40)
        assert json.loads(auth)["type"] == "authenticated"
        auth_seconds = time.monotonic() - started
        acks = []
        for i in range(5):
            sent = time.monotonic()
            await ws.send(
                json.dumps({"action": "camera", "camera": "overview", "request_id": str(i), "yaw": i})
            )
            reply = json.loads(await asyncio.wait_for(ws.recv(), 20))
            assert reply["type"] == "control_ack", reply
            acks.append((time.monotonic() - sent) * 1000)
            await asyncio.sleep(0.15)
    frame_times = []
    rtts = []
    async with websockets.connect(
        url.replace("https://", "wss://") + "/ws" + ("?video=h264" if video else ""),
        compression=None,
        max_size=3 * 1024 * 1024,
        open_timeout=40,
    ) as ws:

        async def ping():
            while True:
                await ws.send(json.dumps({"type": "ping", "nonce": time.monotonic()}))
                await asyncio.sleep(2)

        task = asyncio.create_task(ping())
        deadline = time.monotonic() + 20
        try:
            while time.monotonic() < deadline:
                msg = await asyncio.wait_for(ws.recv(), 20)
                if isinstance(msg, bytes):
                    frame_times.append(time.monotonic())
                else:
                    value = json.loads(msg)
                    if value.get("type") == "pong":
                        rtts.append((time.monotonic() - value["nonce"]) * 1000)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return {
        "control_handshake_seconds": handshake,
        "control_authenticated_seconds": auth_seconds,
        "control_ack_ms": acks,
        "received_fps": (len(frame_times) - 1) / (frame_times[-1] - frame_times[0]),
        "stream_heartbeat_rtt_ms": rtts,
        "frames": len(frame_times),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", action="store_true")
    args = parser.parse_args()
    profile = os.environ["MODAL_PROFILE"]
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Unauthorized profile")
    summary = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--profile", profile, "--json"],
            capture_output=True,
            text=True,
            check=True,
            timeout=45,
        ).stdout
    )
    require_free_credits(summary, 0.5 if args.video else 0.05)
    code = secrets.token_urlsafe(24)
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install("fastapi==0.115.12", "uvicorn==0.34.2", "websockets==15.0.1")
        .add_local_dir("embernet", "/root/embernet", copy=True)
        .add_local_file(
            "artifacts/embernet/cloud/live-8d2660e0f6de/live-frame.jpg", "/tmp/probe.jpg", copy=True
        )
    )
    if args.video:
        from cloud_isaac_runtime import runtime_base_image

        image = (
            runtime_base_image.apt_install("ffmpeg")
            .pip_install("fastapi==0.115.12", "uvicorn==0.34.2", "websockets==15.0.1")
            .add_local_dir("embernet", "/root/embernet", copy=True)
            .add_local_file(
                "artifacts/embernet/cloud/live-8d2660e0f6de/live-frame.jpg", "/tmp/probe.jpg", copy=True
            )
        )
    app = modal.App("embernet-control-probe")
    with app.run():
        sb = modal.Sandbox.create(
            "python",
            "-c",
            SERVER,
            image=image,
            app=app,
            cpu=2 if args.video else 1,
            gpu="RTX-PRO-6000" if args.video else None,
            memory=1024,
            timeout=120,
            encrypted_ports=[8000],
            env={
                "PROBE_HASH": hashlib.sha256(code.encode()).hexdigest(),
                "PYTHONPATH": "/root",
                "PROBE_VIDEO": "1" if args.video else "0",
            },
        )
        try:
            url = sb.tunnels()[8000].url
            result = asyncio.run(check(url, code, args.video))
        finally:
            sb.terminate()
    root = Path("artifacts/embernet/cloud")
    (root / ("h264-transport-probe.json" if args.video else "cpu-transport-probe.json")).write_text(
        json.dumps(result, indent=2)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

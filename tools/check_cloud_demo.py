"""End-to-end test of the deployed shared physics world; never logs the control code."""

import asyncio
import json
import time
import uuid
from itertools import pairwise
from pathlib import Path

import httpx
import websockets


async def main():
    root = Path("artifacts/embernet/cloud")
    private = json.loads((root / "control-invite.private.json").read_text())
    headers = {"Authorization": "Bearer " + private["control_code"]}
    async with httpx.AsyncClient(timeout=110, limits=httpx.Limits(max_keepalive_connections=0)) as client:
        forbidden = await client.post(private["watch_url"] + "/api/start")
        assert forbidden.status_code == 403
        response = await client.post(private["watch_url"] + "/api/start", headers=headers)
        response.raise_for_status()
        session = response.json()
        target = root / session["run_id"]
        target.mkdir(exist_ok=True)
        (target / "session.json").write_text(json.dumps(session, indent=2))
        print(json.dumps({"started": session["run_id"], "url": session["url"]}), flush=True)
        health = None
        for _ in range(30):
            try:
                health = await client.get(session["url"] + "/api/state", timeout=5)
                if health.status_code == 200:
                    break
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
        if health is None:
            raise RuntimeError("Sandbox HTTP endpoint did not start; inspect sandbox-output.log")
        health.raise_for_status()
        denied = await client.post(session["url"] + "/api/control", json={"action": "stop"})
        assert denied.status_code == 403

        control_socket = None

        async def control(value):
            nonlocal control_socket
            value = dict(value, request_id=uuid.uuid4().hex)
            for attempt in range(3):
                try:
                    if control_socket is None:
                        control_socket = await websockets.connect(
                            session["url"].replace("https://", "wss://") + "/ws/control",
                            compression=None,
                            open_timeout=30,
                        )
                        await control_socket.send(json.dumps({"code": private["control_code"]}))
                        auth = json.loads(await asyncio.wait_for(control_socket.recv(), 30))
                        assert auth["type"] == "authenticated", auth
                    await control_socket.send(json.dumps(value))
                    reply = json.loads(await asyncio.wait_for(control_socket.recv(), 8))
                    assert reply["type"] == "control_ack", reply
                    await asyncio.sleep(0.25)
                    return reply
                except (websockets.ConnectionClosed, TimeoutError):
                    if control_socket is not None:
                        await control_socket.close()
                    control_socket = None
                    if attempt == 2:
                        raise

        states = []
        frames = 0
        ir_frames = 0
        last_print = 0
        async with websockets.connect(
            session["url"].replace("https://", "wss://") + "/ws?video=h264",
            max_size=3 * 1024 * 1024,
            open_timeout=20,
            ping_interval=None,
            compression=None,
        ) as socket:
            changed = asyncio.Event()
            latest = None
            frame_times = []
            heartbeat_rtts = []
            latest_images = {}
            video_sample = []
            write_seconds = []
            last_pong = time.monotonic()

            async def reader():
                nonlocal frames, ir_frames, last_print, latest, last_pong
                async for data in socket:
                    if isinstance(data, bytes):
                        channel, payload = data[0], data[1:]
                        if channel == 0:
                            frames += 1
                            frame_times.append(time.monotonic())
                            latest_images[0] = payload
                        elif channel == 2:
                            frames += 1
                            frame_times.append(time.monotonic())
                            if len(video_sample) < 60:
                                video_sample.append(data[10:])
                        elif channel == 1:
                            ir_frames += 1
                            latest_images[1] = payload
                    else:
                        message = json.loads(data)
                        if message.get("type") == "pong":
                            last_pong = time.monotonic()
                            heartbeat_rtts.append((last_pong - message["nonce"]) * 1000)
                            continue
                        if message.get("type") == "video_config":
                            continue
                        if message.get("type") == "video_error":
                            raise RuntimeError(message)
                        latest = message
                        states.append(latest)
                        changed.set()
                        if time.monotonic() - last_print > 10:
                            print(
                                json.dumps(
                                    {
                                        "phase": latest["phase"],
                                        "time": latest["time"],
                                        "frames": frames,
                                        "aircraft": [
                                            (d["id"], d["armed"], round(d["position"][2], 1))
                                            for d in latest["drones"]
                                        ],
                                    }
                                ),
                                flush=True,
                            )
                            last_print = time.monotonic()

            async def record_latest():
                while True:
                    await asyncio.sleep(0.5)
                    for channel, payload in list(latest_images.items()):
                        started = time.monotonic()
                        await asyncio.to_thread(
                            (target / ("live-frame.jpg" if channel == 0 else "live-ir.jpg")).write_bytes,
                            payload,
                        )
                        write_seconds.append(time.monotonic() - started)

            image_task = asyncio.create_task(record_latest())
            reader_task = asyncio.create_task(reader())

            async def heartbeat():
                while True:
                    await socket.send(json.dumps({"type": "ping", "nonce": time.monotonic()}))
                    await asyncio.sleep(5)
                    if time.monotonic() - last_pong > 15:
                        raise TimeoutError("Application heartbeat expired")

            heartbeat_task = asyncio.create_task(heartbeat())

            async def until(predicate, limit=120):
                end = time.monotonic() + limit
                while time.monotonic() < end:
                    if heartbeat_task.done():
                        heartbeat_task.result()
                    if reader_task.done():
                        reader_task.result()
                        raise RuntimeError("Stream closed before acceptance")
                    if latest is not None and predicate(latest):
                        return latest
                    changed.clear()
                    try:
                        await asyncio.wait_for(changed.wait(), timeout=min(5, end - time.monotonic()))
                    except TimeoutError:
                        continue
                raise TimeoutError("Shared world did not reach expected state")

            try:
                await until(
                    lambda s: (
                        s["time"] >= 26
                        and len(s["drones"]) == 3
                        and all(d["armed"] and d["offboard"] for d in s["drones"])
                    ),
                    360,
                )
                await control({"action": "incident", "x": 150, "y": 134, "z": 104.4, "severity": 0.9})
                await until(lambda s: any(i["source"] == "operator" for i in s["incidents"]))
                await control({"action": "incident", "x": 195, "y": 190, "severity": 0.25})
                await until(lambda s: len(s["incidents"]) >= 2)
                await control({"action": "incident", "kind": "person", "x": 150, "y": 134, "z": 104.4})
                await until(lambda s: any(i["survivor"] > 0 for i in s["incidents"]))
                await control({"action": "mesh", "drone": "E02", "enabled": False})
                isolated = await until(
                    lambda s: any(d["id"] == "E02" and not d["connected"] for d in s["drones"])
                )
                await control({"action": "pause"})
                paused = await until(lambda s: s["paused"])
                await asyncio.sleep(1)
                same = (await client.get(session["url"] + "/api/state")).json()
                assert same["time"] == paused["time"]
                await control({"action": "resume"})
                await control({"action": "camera", "camera": "overview", "drone": "E02"})
                await until(lambda s: s["camera"]["camera"] == "overview" and not s["paused"])
                await control({"action": "mesh", "drone": "E02", "enabled": True})
                final = await until(
                    lambda s: s["time"] >= isolated["time"] + 10 and all(d["connected"] for d in s["drones"])
                )
                async with websockets.connect(
                    session["url"].replace("https://", "wss://") + "/ws/camera"
                ) as camera:
                    await camera.send(json.dumps({"code": private["control_code"]}))
                    assert json.loads(await asyncio.wait_for(camera.recv(), 30))["type"] == "authenticated"
                    started = time.monotonic()
                    await camera.send(
                        json.dumps(
                            {"camera": "fire", "interactive": True, "yaw": -45, "pitch": 24, "distance": 65}
                        )
                    )
                    await until(lambda s: s["camera"]["interactive"] and s["camera"]["yaw"] == -45)
                    camera_ack_ms = (time.monotonic() - started) * 1000
                await until(lambda s: s["time"] > final["time"] + 2)
                assert frames >= 10 and ir_frames >= 10
                deltas = [b - a for a, b in pairwise(frame_times)]
                stream_metrics = {
                    "received_fps": (len(frame_times) - 1) / (frame_times[-1] - frame_times[0]),
                    "frame_gap_max_seconds": max(deltas),
                    "camera_state_ack_ms": camera_ack_ms,
                    "application_heartbeat_max_rtt_ms": max(heartbeat_rtts),
                    "application_heartbeats": len(heartbeat_rtts),
                }
                (target / "stream-metrics.json").write_text(json.dumps(stream_metrics, indent=2))
                (target / "test-report.json").write_text(
                    json.dumps(
                        {
                            "passed": True,
                            "frames_received": frames,
                            "ir_frames_received": ir_frames,
                            "spectator_controls_denied": True,
                            "pause_verified": True,
                            "report_and_survivor_received": True,
                            "mesh_isolation_and_reconnect": True,
                            "final_state": final,
                        },
                        indent=2,
                    )
                )
                review = target / "review-hold.json"
                if review.exists():
                    seconds = max(0, min(60, float(json.loads(review.read_text()).get("seconds", 0))))
                    print(json.dumps({"review_seconds": seconds, "run_id": session["run_id"]}), flush=True)
                    await asyncio.sleep(seconds)
            finally:
                (target / "transport-diagnostics.json").write_text(
                    json.dumps(
                        {
                            "frame_times": frame_times,
                            "heartbeat_rtts_ms": heartbeat_rtts,
                            "image_write_seconds": write_seconds,
                        }
                    )
                )
                (target / "received-video.h264").write_bytes(b"".join(video_sample))
                image_task.cancel()
                reader_task.cancel()
                heartbeat_task.cancel()
                await asyncio.gather(reader_task, heartbeat_task, image_task, return_exceptions=True)
                (target / "client-state.jsonl").write_text("\n".join(json.dumps(s) for s in states))
                try:
                    await control({"action": "stop"})
                except httpx.HTTPError as error:
                    (target / "stop-request-error.txt").write_text(str(error))
                if control_socket is not None:
                    await control_socket.close()
        print(
            json.dumps({"evidence": str(target), "frames_received": frames, "ir_frames": ir_frames}),
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())

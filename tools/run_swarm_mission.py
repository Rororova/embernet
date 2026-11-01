"""Start one session, watch the mission without operator input, stop, and fetch evidence."""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path("artifacts/embernet/cloud")


async def run(limit, world):
    private = json.loads((ROOT / "control-invite.private.json").read_text())
    headers = {"Authorization": "Bearer " + private["control_code"]}
    async with httpx.AsyncClient(timeout=110, limits=httpx.Limits(max_keepalive_connections=0)) as client:
        response = await client.post(private["watch_url"] + "/api/start", params={"world": world}, headers=headers)
        response.raise_for_status()
        session = response.json()
    target = ROOT / session["run_id"]
    target.mkdir(parents=True, exist_ok=True)
    (target / "session.json").write_text(json.dumps(session, indent=2))
    print(json.dumps({"started": session["run_id"]}), flush=True)
    socket_url = session["url"].replace("https://", "wss://")
    states, started, last_print = [], time.monotonic(), 0.0
    completed = False
    while time.monotonic() - started < limit and not completed:
        try:
            async with websockets.connect(
                socket_url + "/ws", max_size=4 * 1024 * 1024, open_timeout=20, ping_interval=None, compression=None
            ) as socket:
                while time.monotonic() - started < limit:
                    message = await asyncio.wait_for(socket.recv(), 30)
                    if isinstance(message, bytes):
                        continue
                    state = json.loads(message)
                    if "drones" not in state:
                        continue
                    if not states or state["time"] - states[-1]["time"] >= 1:
                        states.append(state)
                    if time.monotonic() - last_print > 15:
                        last_print = time.monotonic()
                        print(
                            json.dumps(
                                {
                                    "wall": round(time.monotonic() - started),
                                    "time": round(state["time"], 1),
                                    "phase": state["phase"],
                                    "tasks": [d["task"] for d in state["drones"]],
                                    "z": [round(d["position"][2]) for d in state["drones"]],
                                    "fires": [round(f["fraction"], 2) for f in state.get("world", {}).get("fires", [])],
                                    "last": (state.get("decisions") or [{}])[-1].get("text", ""),
                                }
                            ),
                            flush=True,
                        )
                    if (state.get("mission") or {}).get("completed_at") is not None:
                        completed = True
                        print(json.dumps({"completed_at": state["mission"]["completed_at"]}), flush=True)
                        break
        except (websockets.WebSocketException, OSError, TimeoutError) as error:
            print(json.dumps({"reconnecting": repr(error)[:120]}), flush=True)
            await asyncio.sleep(4)
            async with httpx.AsyncClient(timeout=20) as client:
                status = (await client.get(private["watch_url"] + "/api/session")).json()
            if not status.get("active"):
                print(json.dumps({"session_ended": True}), flush=True)
                break
    (target / "client-state.jsonl").write_text("\n".join(json.dumps(s) for s in states))
    if completed:
        # Exercise click-to-ignite on the live world, then hold so the recording shows it.
        fires = len(state["world"]["fires"])
        async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=0)) as client:
            reply = await client.post(
                session["url"] + "/api/control",
                json={"action": "ignite", "u": 0.5, "v": 0.62, "radius": 4, "severity": 0.6},
                headers=headers,
            )
            await asyncio.sleep(10)
            after = (await client.get(session["url"] + "/api/state")).json()
        print(
            json.dumps(
                {
                    "ignite_status": reply.status_code,
                    "fires_before": fires,
                    "fires_after": len(after["world"]["fires"]),
                    "events": after.get("events", [])[-2:],
                }
            ),
            flush=True,
        )
    try:
        async with httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_keepalive_connections=0)) as client:
            reply = await client.post(session["url"] + "/api/control", json={"action": "stop"}, headers=headers)
            print(json.dumps({"stop": reply.status_code}), flush=True)
    except httpx.HTTPError as error:
        (target / "stop-request-error.txt").write_text(str(error))
    await asyncio.sleep(20)
    return session["run_id"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=1180)
    parser.add_argument("--world", choices=("city", "wildland"), default="city")
    args = parser.parse_args()
    run_id = asyncio.run(run(args.limit, args.world))
    subprocess.run([sys.executable, "tools/download_live_logs.py", run_id], check=False)
    from embernet.mission_acceptance import evaluate_run

    print(json.dumps(evaluate_run(ROOT / run_id), indent=2))


if __name__ == "__main__":
    main()

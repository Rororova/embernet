"""Single supported CLI for mission control, training, evaluation, and replays."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        prog="embernet", description="EMBERNET · decentralized wildfire response"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Start local mission control and Rerun recording")
    serve.add_argument("--port", type=int, default=8780)
    serve.add_argument("--models", default="artifacts/embernet/embernet-v2")
    serve.add_argument("--rerun", action="store_true", help="Open the native Rerun 3D viewer")
    demo = commands.add_parser("demo", help="Record a repeatable headless mission")
    demo.add_argument("--seed", type=int, default=41)
    demo.add_argument("--seconds", type=int, default=180)
    demo.add_argument("--output", default="artifacts/embernet/headless")
    demo.add_argument("--models")
    demo.add_argument("--learned-vision", action="store_true")
    demo.add_argument("--learned-policy", action="store_true")
    train = commands.add_parser("train", help="Run a local training experiment")
    train.add_argument("target", choices=["vision", "mission"])
    train.add_argument("--output", default="artifacts/embernet/local")
    train.add_argument("--small", action="store_true")
    replay = commands.add_parser("replay", help="Rebuild a Rerun recording from snapshot JSONL")
    replay.add_argument("path")
    replay.add_argument("--output", default="artifacts/embernet/replay.rrd")
    perceive = commands.add_parser("perceive", help="Run pretrained fire/smoke detection on real RGB images")
    perceive.add_argument("source", help="Image file or folder")
    perceive.add_argument("--output", default="artifacts/embernet/image-inspection")
    perceive.add_argument("--model", default="artifacts/embernet/pretrained/fire-smoke-yolov8n/model.onnx")
    perceive.add_argument("--confidence", type=float, default=0.25)
    control = commands.add_parser("control", help="Send an operator command without a browser")
    control.add_argument(
        "action",
        choices=["launch", "pause", "fire", "person", "animal", "mesh-off", "mesh-on", "isolate", "reset"],
    )
    control.add_argument("--x", type=float, default=160)
    control.add_argument("--y", type=float, default=160)
    control.add_argument("--severity", type=float, default=0.6)
    control.add_argument("--drone", default="E03")
    control.add_argument("--seed", type=int, default=41)
    control.add_argument("--learned", action="store_true")
    control.add_argument("--port", type=int, default=8780)
    args = parser.parse_args()
    if args.command == "serve":
        import uvicorn

        from .server import create_app

        uvicorn.run(
            create_app(models=args.models, spawn_rerun=args.rerun),
            host="127.0.0.1",
            port=args.port,
            access_log=False,
        )
    elif args.command == "train":
        from .training import train_mission, train_vision

        if args.target == "vision":
            report = train_vision(
                args.output, samples=128 if args.small else 1536, epochs=2 if args.small else 10
            )
        else:
            report = train_mission(
                args.output,
                demonstrations=2 if args.small else 12,
                bc_epochs=2 if args.small else 10,
                updates=1 if args.small else 12,
                rollout_steps=12 if args.small else 56,
            )
        print(json.dumps(report, indent=2))
    elif args.command == "demo":
        from .contracts import Config
        from .learning import PolicyRuntime
        from .perception import VisionRuntime
        from .simulation import Simulation
        from .telemetry import Telemetry

        directory = Path(args.models) if args.models else None
        if (args.learned_vision or args.learned_policy) and directory is None:
            parser.error("Specify --models when selecting a learned component")
        vision = VisionRuntime(directory / "vision.pt") if args.learned_vision else None
        policy = PolicyRuntime(directory / "mission.pt") if args.learned_policy else None
        output = Path(args.output)
        output.mkdir(parents=True, exist_ok=True)
        sim = Simulation(Config(seed=args.seed), vision=vision, policy=policy)
        telemetry = Telemetry(output / "mission.rrd", sim)
        with (output / "replay.jsonl").open("w", encoding="utf-8") as stream:
            stream.write(json.dumps({"type": "header", "config": sim.snapshot()["config"]}) + "\n")
            for _ in range(args.seconds):
                sim.step(2)
                telemetry.log(sim)
                stream.write(json.dumps(sim.snapshot()) + "\n")
        telemetry.close()
        report = {
            "seed": args.seed,
            "seconds": args.seconds,
            "sensor": sim.sensor_mode,
            "policy": sim.policy_mode,
            "metrics": sim.metrics,
        }
        (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
    elif args.command == "control":
        from urllib.error import HTTPError, URLError
        from urllib.request import Request, urlopen

        action = args.action
        if action in ("fire", "person", "animal"):
            endpoint, payload = (
                "incidents",
                {"kind": action, "x": args.x, "y": args.y, "severity": args.severity},
            )
        elif action == "reset":
            mode = "learned" if args.learned else "reference"
            endpoint, payload = (
                "reset",
                {"seed": args.seed, "sensor": mode, "policy": "learned" if args.learned else "baseline"},
            )
        else:
            endpoint = "control"
            payload = {"action": "mesh" if action.startswith("mesh-") else action}
            if action.startswith("mesh-"):
                payload["value"] = action == "mesh-on"
            elif action == "isolate":
                payload["value"] = args.drone
        request = Request(
            f"http://127.0.0.1:{args.port}/api/{endpoint}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                print(response.read().decode())
        except HTTPError as exc:
            parser.exit(1, f"Mission command rejected: {exc.read().decode()}\n")
        except URLError:
            parser.exit(1, "Mission server unavailable. Run embernet serve --rerun first.\n")
    elif args.command == "perceive":
        from .real_perception import run_images

        report = run_images(args.source, args.output, args.model, args.confidence)
        print(json.dumps({"frames": len(report["frames"]), "output": args.output}, indent=2))
    elif args.command == "replay":
        from .replay import replay_to_rerun

        print(replay_to_rerun(args.path, args.output))


if __name__ == "__main__":
    main()

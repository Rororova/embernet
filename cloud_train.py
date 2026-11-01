"""One bounded Modal experiment; run with an explicitly selected authorized profile."""

import json
from pathlib import Path

import modal

app = modal.App("embernet-training")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("torch==2.15.0", "numpy==2.5.4", "pillow==12.3.0")
    .add_local_python_source("embernet")
)
volume = modal.Volume.from_name("embernet-experiments", create_if_missing=True)


@app.function(
    image=image,
    gpu=["L4", "A10", "T4"],
    cpu=2,
    memory=8192,
    timeout=900,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume},
)
def train(run_id: str, vision_epochs: int = 10, mission_updates: int = 12):
    import torch

    print(f"Training container started: CUDA={torch.cuda.is_available()}", flush=True)
    from embernet.training import train_mission, train_vision, write_json

    if not run_id or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in run_id
    ):
        raise ValueError("Use a simple unique run ID")
    if not 1 <= vision_epochs <= 12 or not 1 <= mission_updates <= 20:
        raise ValueError("Initial experiment is capped at 12 vision epochs and 20 mission updates")
    output = Path("/runs") / run_id
    if output.exists():
        raise ValueError("Run already exists; use a new run ID")
    output.mkdir(parents=True)
    vision = train_vision(output, epochs=vision_epochs)
    volume.commit()
    mission = train_mission(output, updates=mission_updates)
    summary = {
        "run_id": run_id,
        "vision": vision,
        "mission": mission,
        "compute": "L4/A10/T4 fallback; single container; 900-second timeout",
    }
    write_json(output / "summary.json", summary)
    volume.commit()
    return json.dumps(summary)


@app.local_entrypoint()
def main(run_id: str, vision_epochs: int = 10, mission_updates: int = 12):
    result = json.loads(train.remote(run_id, vision_epochs, mission_updates))
    output = Path("artifacts") / "embernet" / run_id
    output.mkdir(parents=True, exist_ok=True)
    for name in (
        "vision.pt",
        "vision-report.json",
        "mission.pt",
        "mission-bc.pt",
        "mission-report.json",
        "summary.json",
    ):
        with (output / name).open("wb") as stream:
            for chunk in volume.read_file(f"{run_id}/{name}"):
                stream.write(chunk)
    print(
        json.dumps(
            {
                "output": str(output.resolve()),
                "vision": result["vision"]["metrics"],
                "baseline": result["mission"]["baseline_mean"],
                "learned": result["mission"]["learned_mean"],
            },
            indent=2,
        )
    )


@app.function(
    image=image,
    gpu=["L4", "A10", "T4"],
    cpu=2,
    memory=8192,
    timeout=900,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    volumes={"/runs": volume},
)
def refine_vision(run_id: str = "embernet-v2"):
    import shutil

    import torch

    from embernet.training import train_vision, write_json

    if not run_id or any(
        ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in run_id
    ):
        raise ValueError("Use a simple unique run ID")
    output = Path("/runs") / run_id
    if output.exists():
        raise ValueError("Run already exists")
    output.mkdir(parents=True)
    print(f"Small-fire perception refinement on {torch.cuda.get_device_name()}", flush=True)
    report = train_vision(output, samples=2048, epochs=12, seed=211)
    for name in ("mission.pt", "mission-bc.pt", "mission-report.json"):
        shutil.copyfile(Path("/runs/embernet-v1") / name, output / name)
    write_json(
        output / "summary.json",
        {
            "run_id": run_id,
            "vision": report,
            "mission_source": "embernet-v1; policy unchanged",
            "reason": "Add 1.5–4m fires to training distribution",
        },
    )
    volume.commit()
    return report

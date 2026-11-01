"""Bounded follow-up for the small-fire distribution gap discovered in integrated evaluation."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modal

from cloud_train import app, refine_vision

with modal.enable_output(), app.run():
    call = refine_vision.spawn("embernet-v2")
    print(f"Perception refinement call: {call.object_id}", flush=True)
    print(call.get(), flush=True)

"""Direct Modal dispatch with progress and a bounded diagnostic traceback on client stalls."""

import faulthandler
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modal

from cloud_train import app, train

faulthandler.dump_traceback_later(45, repeat=False)
print("Opening Modal application context", flush=True)
with modal.enable_output(), app.run():
    print("Dispatching bounded GPU training", flush=True)
    call = train.spawn("embernet-v1", 10, 12)
    print(f"Training call: {call.object_id}", flush=True)
    faulthandler.cancel_dump_traceback_later()
    result = call.get()
    print(result, flush=True)

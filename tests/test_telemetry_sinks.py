import rerun as rr

from embernet.simulation import Simulation
from embernet.telemetry import Telemetry


def test_live_viewer_does_not_replace_complete_disk_recording(tmp_path, monkeypatch):
    saved, viewer = tmp_path / "saved.rrd", tmp_path / "viewer.rrd"

    def spawn(stream, *, connect=True, **_):
        # The SDK replaces existing sinks when spawn's default connect=True.
        if connect:
            stream.set_sinks(rr.FileSink(viewer))

    monkeypatch.setattr(rr.RecordingStream, "spawn", spawn)
    monkeypatch.setattr(rr, "GrpcSink", lambda: rr.FileSink(viewer))
    telemetry = Telemetry(saved, Simulation(), spawn=True)
    telemetry.close()
    # A header-only file was ~5 KB. Both destinations must contain the assets.
    assert saved.stat().st_size > 1_000_000
    assert viewer.stat().st_size > 1_000_000

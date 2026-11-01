"""Explicit recording stream: world truth and each drone's reported knowledge are separate."""

import os
import sys
from pathlib import Path

import numpy as np

from .telemetry_scene import SceneLogger


class Telemetry:
    def __init__(self, output, sim, *, spawn=False):
        import rerun as rr
        import rerun.blueprint as rrb

        self.rr = rr
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        self.recording = rr.RecordingStream(
            "EMBERNET", recording_id=f"embernet-{sim.c.seed}-{Path(output).stem}"
        )
        sinks = [rr.FileSink(output)]
        self.viewer_error = None
        if spawn:
            try:
                # Direct invocation of the venv Python does not activate its Scripts directory.
                os.environ["PATH"] = (
                    str(Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
                )
                self.recording.spawn(connect=False, memory_limit="1GB", hide_welcome_screen=True)
                sinks.append(rr.GrpcSink())
            except Exception as exc:  # noqa: BLE001 -- Recording must survive an unavailable external viewer.
                self.viewer_error = str(exc)
        # spawn(connect=True) replaces a prior save sink. Explicit fan-out keeps
        # live viewing and a complete disk recording active at the same time.
        self.recording.set_sinks(*sinks)
        self.recording.send_blueprint(
            rrb.Blueprint(
                rrb.Horizontal(
                    rrb.Vertical(
                        rrb.Tabs(
                            rrb.Spatial3DView(
                                origin="world",
                                name="Forest sector · live geometry",
                                line_grid=False,
                                background=[32, 46, 51],
                                eye_controls=rrb.EyeControls3D(
                                    position=[380, -230, 260], look_target=[160, 150, 5], eye_up=[0, 0, 1]
                                ),
                            ),
                            rrb.Spatial3DView(
                                origin="world",
                                name="Follow E02 · aircraft inspection",
                                line_grid=False,
                                background=[32, 46, 51],
                                eye_controls=rrb.EyeControls3D(
                                    tracking_entity="world/aircraft/E02",
                                    position=(sim.states["E02"].position + np.array([20, -36, 16])).tolist(),
                                    look_target=(sim.states["E02"].position + np.array([0, 0, -12])).tolist(),
                                    eye_up=[0, 0, 1],
                                ),
                            ),
                        ),
                        rrb.TextLogView(origin="events", name="Decisions and negotiation"),
                        row_shares=[3, 1],
                    ),
                    rrb.Vertical(
                        rrb.Spatial2DView(origin="cameras/E02/rgb", name="E02 · neural RGB input"),
                        rrb.Spatial2DView(origin="cameras/E02/thermal", name="E02 · neural thermal input"),
                        rrb.TimeSeriesView(origin="metrics", name="Mission resources"),
                    ),
                    column_shares=[3, 1],
                ),
                collapse_panels=True,
            )
        )
        self.recording.log("world", rr.ViewCoordinates.RIGHT_HAND_Z_UP, static=True)
        self.recording.log(
            "events/mode",
            rr.TextLog(f"EMBERNET | {sim.sensor_mode} | {sim.policy_mode} | Kinematic research simulation"),
            static=True,
        )
        self.scene_logger = SceneLogger(rr, self.recording, sim)
        self.last_events = set()
        self.closed = False
        self.log(sim)

    def log(self, sim):
        rr, rec = self.rr, self.recording
        rec.set_time("mission", duration=sim.time)
        ids = sorted(sim.states)
        self.scene_logger.log(sim)
        for key in ids:
            trail = sim.trails[key]
            if len(trail) > 1:
                rec.log(
                    f"world/trails/{key}", rr.LineStrips3D([trail], colors=[[117, 168, 174, 130]], radii=0.2)
                )
            positions = [
                i.position
                for i in sim.agents[key].memory.incidents.values()
                if i.status not in ("cleared", "merged")
            ]
            if positions:
                rec.log(
                    f"knowledge/{key}/incidents", rr.Points3D(positions, radii=2.5, colors=[[220, 182, 127]])
                )
            else:
                rec.log(f"knowledge/{key}/incidents", rr.Clear(recursive=True))
            camera = sim.cameras.get(key)
            if camera is not None:
                rec.log(
                    f"cameras/{key}/rgb", rr.Image((camera[:3].transpose(1, 2, 0) * 255).astype(np.uint8))
                )
                rec.log(f"cameras/{key}/thermal", rr.Image((camera[3] * 255).astype(np.uint8)))
        links = [[sim.states[a].position, sim.states[b].position] for a, b in sim.mesh.links(sim.states)]
        if links:
            rec.log("world/mesh", rr.LineStrips3D(links, colors=[[105, 160, 173, 90]], radii=0.15))
        else:
            rec.log("world/mesh", rr.Clear(recursive=True))
        for name in ("water_used", "contained", "survivor_responses", "safety_interventions"):
            rec.log(f"metrics/{name}", rr.Scalars(sim.metrics[name]))
        for event in sim.events:
            token = (event.time, event.kind, event.drone, event.text, event.incident_id)
            if token not in self.last_events:
                rec.log(
                    "events/decisions",
                    rr.TextLog(
                        f"{event.drone} · {event.kind}: {event.text} ({event.incident_id or 'mission'})"
                    ),
                )
                self.last_events.add(token)
        if len(self.last_events) > 1000:
            self.last_events = {(e.time, e.kind, e.drone, e.text, e.incident_id) for e in sim.events}

    def close(self):
        if not self.closed:
            self.recording.flush()
            self.recording.disconnect()
            self.closed = True

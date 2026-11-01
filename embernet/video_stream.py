"""Low-delay NVENC elementary stream; bounded access units and GOP recovery."""

import io
import re
import struct
import subprocess
import threading
import time
from itertools import pairwise

START = re.compile(b"\x00\x00\x00?\x01")


def nals(payload):
    return [(m.end(), payload[m.end()] & 31) for m in START.finditer(payload) if m.end() < len(payload)]


class AccessUnits:
    def __init__(self):
        self.buffer = b""

    def feed(self, data):
        self.buffer += data
        result = []
        starts = [
            m.start()
            for m in START.finditer(self.buffer)
            if m.end() < len(self.buffer) and self.buffer[m.end()] & 31 == 9
        ]
        for a, b in pairwise(starts):
            result.append(self.buffer[a:b])
        if len(starts) > 1:
            self.buffer = self.buffer[starts[-1] :]
        if len(self.buffer) > 2 * 1024 * 1024:
            raise ValueError("Encoder access-unit framing failed")
        return result


def packet(sequence, payload):
    return struct.pack(">BBQ", 2, int(any(t == 5 for _, t in nals(payload))), sequence * 33333) + payload


def start_encoder(hub):
    def encode():
        from PIL import Image

        process = None
        try:
            with (hub.output / "encoder.log").open("wb") as log:
                args = [
                    "ffmpeg",
                    "-hide_banner",
                    "-loglevel",
                    "warning",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "rgb24",
                    "-s",
                    "960x540",
                    "-r",
                    "30",
                    "-i",
                    "pipe:0",
                    "-an",
                    "-c:v",
                    "h264_nvenc",
                    "-preset",
                    "p4",
                    "-tune",
                    "ull",
                    "-bf",
                    "0",
                    "-rc",
                    "cbr",
                    "-b:v",
                    "1200k",
                    "-maxrate",
                    "1200k",
                    "-bufsize",
                    "120k",
                    "-g",
                    "30",
                    "-profile:v",
                    "baseline",
                    "-level:v",
                    "3.1",
                    "-pix_fmt",
                    "yuv420p",
                    "-bsf:v",
                    "h264_metadata=aud=insert",
                    "-flush_packets",
                    "1",
                    "-f",
                    "h264",
                    "pipe:1",
                ]
                process = subprocess.Popen(
                    args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, bufsize=0
                )

                def receive():
                    parser = AccessUnits()
                    while True:
                        data = process.stdout.read(65536)
                        if not data:
                            break
                        for payload in parser.feed(data):
                            key = any(t == 5 for _, t in nals(payload))
                            with hub.lock:
                                for offset, kind in nals(payload):
                                    if kind == 7:
                                        hub.video_codec = "avc1." + payload[offset + 1 : offset + 4].hex()
                                hub.video_sequence += 1
                                hub.video_packets.append(
                                    (hub.video_sequence, key, packet(hub.video_sequence, payload))
                                )

                reader = threading.Thread(target=receive, daemon=True)
                reader.start()
                last = -1
                while time.time() < hub.deadline:
                    if process.poll() is not None:
                        raise RuntimeError("NVENC exited; inspect encoder.log")
                    with hub.lock:
                        frame, jpeg = hub.frame_id, hub.jpeg
                    if jpeg and frame != last:
                        with Image.open(io.BytesIO(jpeg)) as image:
                            raw = memoryview(image.convert("RGB").resize((960, 540)).tobytes())
                        while raw:
                            count = process.stdin.write(raw)
                            if not count:
                                raise BrokenPipeError("Encoder input closed")
                            raw = raw[count:]
                        last = frame
                    else:
                        time.sleep(0.003)
        except (OSError, RuntimeError, ValueError) as error:
            with hub.lock:
                hub.video_error = str(error)
        finally:
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()

    threading.Thread(target=encode, daemon=True).start()

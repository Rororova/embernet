"""Short, free-credit-guarded GPU/graphics/encoder capability probe, not a render benchmark."""

import modal

from cloud_isaac_runtime import runtime_base_image

app = modal.App("embernet-render-preflight")


@app.function(
    image=runtime_base_image.apt_install("ffmpeg"),
    gpu="RTX-PRO-6000",
    cpu=2,
    memory=4096,
    timeout=90,
    retries=0,
    max_containers=1,
    scaledown_window=2,
    serialized=True,
)
def probe():
    import ctypes as c
    import subprocess

    gpu = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
        check=True,
        capture_output=True,
        text=True,
        timeout=15,
    ).stdout.strip()
    result = {
        "gpu": gpu,
        "nvenc_api": None,
        "vulkan_devices": [],
        "errors": [],
        "scope": "Capability probe; no measured scene FPS or latency",
    }
    try:
        encoder = c.CDLL("libnvidia-encode.so.1")
        version = c.c_uint32()
        code = encoder.NvEncodeAPIGetMaxSupportedVersion(c.byref(version))
        result["nvenc_api"] = {"status": code, "max_version": version.value}
    except OSError as error:
        result["errors"].append(str(error))

    try:
        import hashlib
        import time

        started = time.monotonic()
        encoded = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=960x540:rate=30",
                "-frames:v",
                "120",
                "-c:v",
                "h264_nvenc",
                "-preset",
                "p1",
                "-tune",
                "ull",
                "-bf",
                "0",
                "-rc",
                "cbr",
                "-b:v",
                "2M",
                "-g",
                "30",
                "-profile:v",
                "baseline",
                "-level:v",
                "3.1",
                "-pix_fmt",
                "yuv420p",
                "-f",
                "h264",
                "pipe:1",
            ],
            check=False,
            capture_output=True,
            timeout=25,
        )
        result["encode_probe"] = {
            "returncode": encoded.returncode,
            "seconds": time.monotonic() - started,
            "frames": 120,
            "bytes": len(encoded.stdout),
            "sha256": hashlib.sha256(encoded.stdout).hexdigest(),
            "stderr": encoded.stderr.decode(errors="replace")[-2000:],
        }
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        result["errors"].append("encode: " + str(error))

    class CreateInfo(c.Structure):
        _fields_ = [
            ("type", c.c_uint32),
            ("next", c.c_void_p),
            ("flags", c.c_uint32),
            ("app", c.c_void_p),
            ("layers", c.c_uint32),
            ("layer_names", c.c_void_p),
            ("extensions", c.c_uint32),
            ("extension_names", c.c_void_p),
        ]

    instance = c.c_void_p()
    try:
        vk = c.CDLL("libvulkan.so.1")
        vk.vkCreateInstance.argtypes = [c.POINTER(CreateInfo), c.c_void_p, c.POINTER(c.c_void_p)]
        code = vk.vkCreateInstance(c.byref(CreateInfo(type=1)), None, c.byref(instance))
        if code:
            raise RuntimeError(f"vkCreateInstance status {code}")
        vk.vkEnumeratePhysicalDevices.argtypes = [c.c_void_p, c.POINTER(c.c_uint32), c.c_void_p]
        vk.vkGetPhysicalDeviceProperties.argtypes = [c.c_void_p, c.c_void_p]
        vk.vkDestroyInstance.argtypes = [c.c_void_p, c.c_void_p]
        count = c.c_uint32()
        vk.vkEnumeratePhysicalDevices(instance, c.byref(count), None)
        devices = (c.c_void_p * count.value)()
        vk.vkEnumeratePhysicalDevices(instance, c.byref(count), devices)
        for device in devices:
            properties = c.create_string_buffer(4096)
            vk.vkGetPhysicalDeviceProperties(device, properties)
            name = properties.raw[20:276].split(b"\0")[0].decode(errors="replace")
            result["vulkan_devices"].append(name)
    except (OSError, RuntimeError) as error:
        result["errors"].append(str(error))
    finally:
        if instance.value:
            vk.vkDestroyInstance(instance, None)
    return result


@app.local_entrypoint()
def main():
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path

    from embernet.cloud_resources import require_free_credits

    profile = os.environ.get("MODAL_PROFILE")
    if profile not in ("nikhilthakuraan", "ieirodov14"):
        raise ValueError("Set an authorized MODAL_PROFILE")
    billing = json.loads(
        subprocess.run(
            [sys.executable, "-m", "modal", "billing", "summary", "--json", "--profile", profile],
            check=True,
            capture_output=True,
            text=True,
            timeout=45,
        ).stdout
    )
    require_free_credits(billing, 0.5)
    result = probe.spawn().get(timeout=180)
    result["billing_before"] = billing
    target = Path("artifacts/embernet/cloud/rtx-pro-preflight.json")
    target.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

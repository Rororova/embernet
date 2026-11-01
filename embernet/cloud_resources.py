"""Bounded RTX rendering profiles; prices checked at modal.com/pricing 2026-11-01."""

import math

MAX_SESSION_SECONDS = 1200
RENDER_PROFILES = {
    "L40S": {"gpu": "L40S", "cpu": 8, "memory": 32768, "gpu_usd_second": 0.000542},
    "RTX-PRO-6000": {"gpu": "RTX-PRO-6000", "cpu": 12, "memory": 65536, "gpu_usd_second": 0.000842},
}


def rendering_resources(gpu):
    if gpu not in RENDER_PROFILES:
        raise ValueError("Choose L40S or RTX-PRO-6000 for RTX rendering")
    return dict(RENDER_PROFILES[gpu])


def credit_reserve(gpu, duration):
    if not 30 <= duration <= MAX_SESSION_SECONDS:
        raise ValueError(f"Session duration must be 30–{MAX_SESSION_SECONDS} seconds")
    resources = rendering_resources(gpu)
    rate = (
        resources["gpu_usd_second"] + resources["cpu"] * 0.0000131 + resources["memory"] / 1024 * 0.00000222
    )
    # Include the hard-timeout cleanup window, 25% compute margin and egress reserve.
    return max(1.5, math.ceil(((duration + 60) * rate * 1.25 + 0.25) * 100) / 100)


def require_free_credits(summary, reserve):
    billed = float(summary["billed_cost"])
    credits = abs(float(summary["adjustments"]["credits"]))
    if not all(math.isfinite(v) for v in (billed, credits, reserve)) or reserve < 0:
        raise ValueError("Invalid billing evidence")
    if billed > 0 or credits + reserve > 30:
        raise RuntimeError("Insufficient verified free-credit headroom; no GPU authorized")

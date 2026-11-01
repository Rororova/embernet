"""Calibrated image/depth projection; no incident/world-truth lookup."""

import numpy as np


def project_depth_pixel(pixel, depth_m, intrinsics, world_from_optical):
    k = np.asarray(intrinsics, float)
    pose = np.asarray(world_from_optical, float)
    if k.shape != (3, 3) or pose.shape != (4, 4) or not np.isfinite(k).all() or not np.isfinite(pose).all():
        raise ValueError("Invalid camera calibration")
    if not np.isfinite(depth_m) or not 0.05 < depth_m < 1000 or k[0, 0] <= 0 or k[1, 1] <= 0:
        raise ValueError("Invalid image-plane depth")
    u, v = pixel
    if not np.isfinite([u, v]).all():
        raise ValueError("Invalid image coordinate")
    optical = np.array([(u - k[0, 2]) * depth_m / k[0, 0], (v - k[1, 2]) * depth_m / k[1, 1], depth_m, 1.0])
    return (pose @ optical)[:3]


def optical_pose_from_usd(world_from_usd_camera):
    """USD camera: right/up/back; optical camera: right/down/forward."""
    return np.asarray(world_from_usd_camera, float) @ np.diag([1.0, -1.0, -1.0, 1.0])

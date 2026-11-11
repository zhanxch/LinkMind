"""Registration from public calibrated RGB landmarks; no task/object state access.

Camera matrices here are OpenCV camera-to-world. TRAIN stores USD camera axes,
so conversion is explicit at the data boundary, never guessed from the image.
"""
from __future__ import annotations

import numpy as np
from scipy.spatial.transform import Rotation, Slerp


def rigid_matrix(value):
    t = np.asarray(value, dtype=float)
    if (t.shape != (4, 4) or not np.isfinite(t).all()
            or not np.allclose(t[3], [0, 0, 0, 1], atol=1e-7)
            or not np.allclose(t[:3, :3].T @ t[:3, :3], np.eye(3), atol=1e-6)
            or not np.isclose(np.linalg.det(t[:3, :3]), 1, atol=1e-6)):
        raise ValueError("Expected a finite proper rigid 4x4 transform")
    return t


def pose_matrix(pose):
    pose = np.asarray(pose, dtype=float)
    if pose.shape != (7,) or not np.isfinite(pose).all() or np.linalg.norm(pose[3:]) < 1e-9:
        raise ValueError("Expected xyz plus nonzero quaternion wxyz")
    t = np.eye(4)
    t[:3, :3] = Rotation.from_quat(pose[[4, 5, 6, 3]]).as_matrix()
    t[:3, 3] = pose[:3]
    return t


def matrix_pose(t):
    t = rigid_matrix(t)
    q = Rotation.from_matrix(t[:3, :3]).as_quat()[[3, 0, 1, 2]]
    return np.r_[t[:3, 3], q].tolist()


def ray(camera, uv):
    k = np.asarray(camera["intrinsics"], float)
    t = rigid_matrix(camera["extrinsics_world"])
    uv = np.asarray(uv, float)
    if k.shape != (3, 3) or not np.isfinite(k).all() or min(k[0, 0], k[1, 1]) <= 0:
        raise ValueError("Invalid camera intrinsics")
    if uv.shape != (2,) or not np.isfinite(uv).all():
        raise ValueError("Image landmark needs finite [u,v]")
    width, height = camera["size"]
    if not (0 <= uv[0] < width and 0 <= uv[1] < height):
        raise ValueError("Landmark outside image")
    d = t[:3, :3] @ np.linalg.solve(k, np.r_[uv, 1.])
    return t[:3, 3], d / np.linalg.norm(d)


def project(camera, xyz):
    t = rigid_matrix(camera["extrinsics_world"])
    p = t[:3, :3].T @ (np.asarray(xyz) - t[:3, 3])
    if p[2] <= 1e-6:
        raise ValueError("Point behind camera")
    uv = np.asarray(camera["intrinsics"]) @ p
    return uv[:2] / uv[2]


def locate_landmark(cameras, pixels, plane_z=None):
    """Triangulate >=2 views, or intersect one ray with an explicit plane."""
    if not pixels or any(name not in cameras for name in pixels):
        raise ValueError("Select available cameras for each landmark")
    rays = [ray(cameras[name], uv) for name, uv in pixels.items()]
    if len(rays) == 1:
        if plane_z is None or not np.isfinite(plane_z):
            raise ValueError("Single-view landmark requires an explicit world plane_z")
        origin, d = rays[0]
        if abs(d[2]) < 1e-5 or (plane_z - origin[2]) / d[2] <= 0:
            raise ValueError("Ray does not intersect the plane in front of camera")
        point = origin + d * ((plane_z - origin[2]) / d[2])
        method = "ray_plane_assumption"
    else:
        a = sum(np.eye(3) - np.outer(d, d) for _, d in rays)
        if np.linalg.cond(a) > 1e5:
            raise ValueError("Triangulation has insufficient camera baseline")
        b = sum((np.eye(3) - np.outer(d, d)) @ o for o, d in rays)
        point = np.linalg.solve(a, b)
        method = "multi_view_triangulation"
    errors = [float(np.linalg.norm(project(cameras[name], point) - uv)) for name, uv in pixels.items()]
    if max(errors) > 4:
        raise ValueError(f"Inconsistent multi-view landmark: reprojection error {max(errors):.2f}px")
    return point, dict(method=method, reprojection_error_px=errors,
                       plane_z_assumption=plane_z if len(rays) == 1 else None)


def fit_rigid(reference, current, mode="planar", max_error_m=.02):
    """Fit SE(2)+height translation or SE(3). No scale or reflection fitting."""
    x, y = np.asarray(reference, float), np.asarray(current, float)
    if mode not in ("planar", "rigid"):
        raise ValueError("mode must be planar or rigid")
    minimum = 2 if mode == "planar" else 3
    if (x.ndim != 2 or x.shape[1:] != (3,) or x.shape != y.shape or len(x) < minimum
            or not np.isfinite(x).all() or not np.isfinite(y).all()):
        raise ValueError(f"Need >= {minimum} finite paired 3D landmarks")
    if not np.isfinite(max_error_m) or not 0 < max_error_m <= .05:
        raise ValueError("max_error_m must be in (0,0.05]")
    xc, yc = x.mean(0), y.mean(0)
    a, b = x - xc, y - yc
    dimensions = 2 if mode == "planar" else 3
    sa, sb = np.linalg.svd(a[:, :dimensions], compute_uv=False), np.linalg.svd(b[:, :dimensions], compute_uv=False)
    rank = 1 if mode == "planar" else 2
    if min(sa[rank - 1], sb[rank - 1]) < .005:
        raise ValueError("Landmarks too close or collinear to constrain this transform")
    u, _, vt = np.linalg.svd(a[:, :dimensions].T @ b[:, :dimensions])
    correction = np.eye(dimensions)
    correction[-1, -1] = np.linalg.det(vt.T @ u.T)
    r = np.eye(3)
    r[:dimensions, :dimensions] = vt.T @ correction @ u.T
    t = np.eye(4)
    t[:3, :3], t[:3, 3] = r, yc - r @ xc
    errors = np.linalg.norm(x @ r.T + t[:3, 3] - y, axis=1)
    if errors.max() > max_error_m:
        raise ValueError(f"Rigid fit inconsistent: max residual {errors.max():.4f}m; inspect correspondences/shape/height")
    return dict(matrix=t.tolist(), reference_center=xc.tolist(), current_center=yc.tolist(),
                mode=mode, residuals_m=errors.tolist(), rms_m=float(np.sqrt(np.mean(errors ** 2))),
                max_error_m=float(errors.max()), landmark_count=len(x),
                interpretation="Geometric correspondence under stated landmark assumptions, not grasp/collision proof")


def blend_transform(a, b, amount):
    """Explicit smooth SE(3) blend for a free-motion interval, not collision planning."""
    a, b = rigid_matrix(a), rigid_matrix(b)
    if not 0 <= amount <= 1:
        raise ValueError("Blend progress outside [0,1]")
    alpha = amount * amount * (3 - 2 * amount)
    t = np.eye(4)
    t[:3, :3] = Slerp([0, 1], Rotation.from_matrix(np.stack([a[:3, :3], b[:3, :3]])))(alpha).as_matrix()
    t[:3, 3] = (1 - alpha) * a[:3, 3] + alpha * b[:3, 3]
    return t

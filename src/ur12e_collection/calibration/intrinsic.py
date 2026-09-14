"""Fit RGB optics from independent training views, with no supplied K."""

import cv2
import numpy as np

from ur12e_collection.calibration import board, geometry, routes


def solve(
    detections: list, observations: list, profile: dict, role: str
) -> dict:
    """Fit K first, freeze it, then solve/validate metric hand-eye geometry."""
    training = [
        d for d, o in zip(detections, observations) if o["split"] == "training"
    ]
    if len(training) < 15 or len(observations) - len(training) < 5:
        raise ValueError(
            "at least 15 training and 5 held-out observations required"
        )
    optics = _intrinsics(training, profile)
    optics["training_pose_ids"] = [
        o["pose_id"] for o in observations if o["split"] == "training"
    ]
    solution = _extrinsics(
        detections,
        observations,
        np.asarray(optics["matrix"]),
        np.asarray(optics["coeffs"]),
        role,
    )
    return {
        "intrinsics": optics,
        "solution": solution,
        "metric_consistency_passed": True,
        "absolute_accuracy_verified": False,
        "production_profile_compatible": (profile["width"], profile["height"])
        == (640, 480),
        "active": False,
    }


def _extrinsics(detections, observations, matrix, distortion, role):
    splits = {"training": [], "validation": []}
    for detection, item in zip(detections, observations):
        transform, residual = board.estimate_pose(
            np.asarray(detection["object_points_m"], np.float32),
            np.asarray(detection["image_points"], np.float32),
            matrix,
            distortion,
            routes.DETECTION,
        )
        splits[item["split"]].append(
            geometry.Observation(
                item["pose_id"], item["T_base_flange"], transform, residual
            )
        )
    return geometry.solve(
        "wrist" if role == "wrist" else "fixed",
        splits["training"],
        splits["validation"],
        geometry.Thresholds(**routes.solver_limits()),
    )


def _validate_optics(matrix, distortion, uncertainty, size):
    """Check finite optics separately from fit residuals."""
    if not all(np.isfinite(v).all() for v in (matrix, distortion, uncertainty)):
        raise ValueError("intrinsic fit is nonfinite")
    if (
        matrix.shape != (3, 3)
        or matrix[0, 0] <= 0
        or matrix[1, 1] <= 0
        or not 0 < matrix[0, 2] < size[0]
        or not 0 < matrix[1, 2] < size[1]
    ):
        raise ValueError(
            "intrinsic fit failed finite/optical/reprojection gates"
        )


def _intrinsics(training, profile):
    """Fit training images and report uncertainty without prior optics."""
    objects = [np.asarray(d["object_points_m"], np.float32) for d in training]
    pixels = [np.asarray(d["image_points"], np.float32) for d in training]
    size = (profile["width"], profile["height"])
    rms, matrix, distortion, rotations, _, uncertainty, _, per_view = (
        cv2.calibrateCameraExtended(objects, pixels, size, None, None)
    )
    _validate_optics(matrix, distortion, uncertainty, size)
    if (
        rms > routes.DETECTION.reprojection_px
        or np.max(per_view) > routes.DETECTION.reprojection_px
    ):
        raise ValueError("intrinsic reprojection gate failed")
    # A planar intrinsic fit needs tilted views, independently of robot motion.
    normals = np.array([cv2.Rodrigues(r)[0][:, 2] for r in rotations])
    singular = np.linalg.svd(normals - normals.mean(axis=0), compute_uv=False)
    if singular[1] < 0.05:
        raise ValueError("intrinsic views lack two-axis board tilt")
    return {
        "profile": profile,
        "model": "brown_conrady",
        "matrix": matrix.tolist(),
        "coeffs": distortion.ravel().tolist(),
        "training_rms_px": rms,
        "standard_deviations": uncertainty.ravel().tolist(),
        "tilt_singular_values": singular.tolist(),
    }

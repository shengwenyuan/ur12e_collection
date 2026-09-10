"""Rigid-transform directions for fixed-camera and wrist calibration."""

import dataclasses

import cv2
import numpy as np


def transform(value) -> np.ndarray:
    """Validate T_A_B, mapping B coordinates to A, in meters and radians."""
    result = np.array(value, dtype=np.float64, copy=True)
    if result.shape != (4, 4) or not np.isfinite(result).all():
        raise ValueError("transform must be a finite 4x4 matrix")
    rotation = result[:3, :3]
    if (
        not np.allclose(result[3], (0, 0, 0, 1), atol=1e-9, rtol=0)
        or not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-6, rtol=0)
        or not np.isclose(np.linalg.det(rotation), 1, atol=1e-6, rtol=0)
    ):
        raise ValueError("transform must contain a proper rigid rotation")
    result.setflags(write=False)
    return result


def pose(values) -> np.ndarray:
    """Convert UR [x,y,z,rx,ry,rz]; rotation is a vector, never Euler angles."""
    values = np.asarray(values, dtype=float)
    if values.shape != (6,) or not np.isfinite(values).all():
        raise ValueError("pose requires six finite values")
    result = np.eye(4)
    result[:3, :3] = cv2.Rodrigues(values[3:])[0]
    result[:3, 3] = values[:3]
    return transform(result)


def inverse(value) -> np.ndarray:
    """Invert a verified rigid transform without a general matrix inverse."""
    value = transform(value)
    result = np.eye(4)
    result[:3, :3] = value[:3, :3].T
    result[:3, 3] = -result[:3, :3] @ value[:3, 3]
    return result


def error(reference, measured) -> dict:
    """Report metric translation and geodesic rotation residuals separately."""
    difference = inverse(reference) @ transform(measured)
    return {
        "translation_m": float(np.linalg.norm(difference[:3, 3])),
        "rotation_rad": float(
            np.linalg.norm(cv2.Rodrigues(difference[:3, :3])[0])
        ),
    }


@dataclasses.dataclass(frozen=True)
class Observation:
    """One independent stationary checkpoint, not many frames from one stop."""

    pose_id: str
    base_flange: np.ndarray
    camera_board: np.ndarray
    reprojection_px: float

    def __post_init__(self):
        if not isinstance(self.pose_id, str) or not self.pose_id:
            raise ValueError("pose identity is required")
        if not np.isfinite(self.reprojection_px) or self.reprojection_px < 0:
            raise ValueError(
                "reprojection residual must be finite and nonnegative"
            )
        for name in ("base_flange", "camera_board"):
            object.__setattr__(self, name, transform(getattr(self, name)))


@dataclasses.dataclass(frozen=True)
class Thresholds:
    """Required experiment choices; these are not physical accuracy claims."""

    translation_m: float
    rotation_rad: float
    reprojection_px: float
    rotation_span_rad: float = 0.1
    minimum_axis_ratio: float = 0.01

    def __post_init__(self):
        if any(
            not np.isfinite(v) or v <= 0
            for v in dataclasses.asdict(self).values()
        ):
            raise ValueError(
                "calibration thresholds must be positive and finite"
            )
        if self.minimum_axis_ratio >= 1:
            raise ValueError("minimum axis ratio must be smaller than one")


def _observable(values, thresholds):
    rotations = [inverse(values[0]) @ value for value in values[1:]]
    vectors = np.array(
        [cv2.Rodrigues(value[:3, :3])[0].ravel() for value in rotations]
    )
    singular = np.linalg.svd(vectors, compute_uv=False)
    if (
        singular[0] < thresholds.rotation_span_rad
        or singular[1] / singular[0] < thresholds.minimum_axis_ratio
    ):
        raise ValueError("calibration motion lacks independent rotation axes")
    # Translation in AX=XB also requires a well-conditioned stacked (R-I).
    translation_system = np.concatenate(
        [value[:3, :3] - np.eye(3) for value in rotations]
    )
    translation_singular = np.linalg.svd(translation_system, compute_uv=False)
    if (
        translation_singular[-1] / translation_singular[0]
        < thresholds.minimum_axis_ratio
    ):
        raise ValueError("calibration translation is poorly observable")
    return {
        "rotation_singular_values": singular.tolist(),
        "translation_singular_values": translation_singular.tolist(),
    }


def _mean(values):
    left, _, right = np.linalg.svd(sum(value[:3, :3] for value in values))
    correction = np.diag([1, 1, np.linalg.det(left @ right)])
    result = np.eye(4)
    result[:3, :3] = left @ correction @ right
    result[:3, 3] = np.mean([value[:3, 3] for value in values], axis=0)
    return transform(result)


def solve(
    round_name: str,
    training: list[Observation],
    validation: list[Observation],
    thresholds: Thresholds,
) -> dict:
    """Fit only training poses and require independent held-out consistency."""
    if round_name not in ("fixed", "wrist"):
        raise ValueError("calibration round must be fixed or wrist")
    if len(training) < 6 or len(validation) < 3:
        raise ValueError(
            "at least six training and three held-out poses required"
        )
    identities = [item.pose_id for item in training + validation]
    if len(set(identities)) != len(identities):
        raise ValueError(
            "checkpoint IDs must be unique across fit and validation"
        )
    robot = [
        item.base_flange if round_name == "wrist" else inverse(item.base_flange)
        for item in training
    ]
    board = [item.camera_board for item in training]
    observability = _observable(robot, thresholds)
    rotation, translation = cv2.calibrateHandEye(
        [v[:3, :3] for v in robot],
        [v[:3, 3] for v in robot],
        [v[:3, :3] for v in board],
        [v[:3, 3] for v in board],
        method=cv2.CALIB_HAND_EYE_PARK,
    )
    camera = np.eye(4)
    camera[:3, :3], camera[:3, 3] = rotation, translation.ravel()
    camera = transform(camera)
    constant = _mean([a @ camera @ b for a, b in zip(robot, board)])
    report = _residuals(
        round_name,
        {"training": training, "validation": validation},
        camera,
        constant,
        thresholds,
    )
    return {
        "round": round_name,
        "opencv_version": cv2.__version__,
        "method": "PARK",
        "thresholds": dataclasses.asdict(thresholds),
        "observability": observability,
        "residuals": report,
        (
            "T_flange_camera" if round_name == "wrist" else "T_base_camera"
        ): camera.tolist(),
        (
            "T_base_board" if round_name == "wrist" else "T_flange_board"
        ): constant.tolist(),
    }


def _residuals(round_name, splits, camera, constant, thresholds):
    report = []
    for split, observations in splits.items():
        for item in observations:
            robot = (
                item.base_flange
                if round_name == "wrist"
                else inverse(item.base_flange)
            )
            residual = error(constant, robot @ camera @ item.camera_board)
            residual["reprojection_px"] = item.reprojection_px
            if any(
                value > getattr(thresholds, key)
                for key, value in residual.items()
            ):
                raise ValueError(
                    f"{split} checkpoint {item.pose_id} exceeds accuracy "
                    f"thresholds: {residual}"
                )
            report.append({"pose_id": item.pose_id, "split": split, **residual})
    return report

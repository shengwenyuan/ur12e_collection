"""ChArUco detection with explicit scale, optics and planar-pose rejection."""

import dataclasses

import cv2
import numpy as np

from ur12e_collection.calibration import geometry


@dataclasses.dataclass(frozen=True)
class Board:
    """Measured print geometry; square and marker lengths are meters."""

    squares_x: int
    squares_y: int
    square_m: float
    marker_m: float
    dictionary: str

    def create(self):
        """Construct only named OpenCV predefined marker dictionaries."""
        if any(
            not isinstance(v, int) or isinstance(v, bool) or v < 3
            for v in (self.squares_x, self.squares_y)
        ):
            raise ValueError("board requires at least three squares per axis")
        if not (
            np.isfinite(self.square_m) and 0 < self.marker_m < self.square_m
        ):
            raise ValueError(
                "marker size must be positive and below square size"
            )
        if not self.dictionary.startswith("DICT_") or not hasattr(
            cv2.aruco, self.dictionary
        ):
            raise ValueError("unsupported ArUco dictionary")
        dictionary = cv2.aruco.getPredefinedDictionary(
            getattr(cv2.aruco, self.dictionary)
        )
        return cv2.aruco.CharucoBoard(
            (self.squares_x, self.squares_y),
            self.square_m,
            self.marker_m,
            dictionary,
        )


@dataclasses.dataclass(frozen=True)
class DetectionLimits:
    """Explicit image acceptance thresholds selected for this experiment."""

    sharpness: float
    coverage: float
    reprojection_px: float
    ambiguity_gap_px: float
    corners: int = 8

    def __post_init__(self):
        if (
            not isinstance(self.corners, int)
            or isinstance(self.corners, bool)
            or self.corners < 6
            or not 0 < self.coverage <= 1
            or any(
                not np.isfinite(v) or v <= 0
                for v in (
                    self.sharpness,
                    self.reprojection_px,
                    self.ambiguity_gap_px,
                )
            )
        ):
            raise ValueError("invalid board detection thresholds")


def optics(intrinsics: dict) -> tuple:
    """Use only distortion models with known OpenCV coefficient semantics."""
    model = intrinsics.get("model", "none").removeprefix("distortion.")
    if model not in ("none", "brown_conrady"):
        raise ValueError("unsupported calibration distortion model")
    matrix = np.array(
        [
            [intrinsics["fx"], 0, intrinsics["ppx"]],
            [0, intrinsics["fy"], intrinsics["ppy"]],
            [0, 0, 1],
        ],
        dtype=float,
    )
    coefficients = np.asarray(intrinsics.get("coeffs", []), dtype=float)
    if (
        not np.isfinite(matrix).all()
        or min(matrix[0, 0], matrix[1, 1]) <= 0
        or coefficients.shape not in ((0,), (4,), (5,), (8,))
        or not np.isfinite(coefficients).all()
    ):
        raise ValueError("invalid camera intrinsics")
    if model == "none" and coefficients.any():
        raise ValueError("undistorted model has nonzero coefficients")
    return matrix, coefficients


def detect(
    rgb: np.ndarray, board: Board, intrinsics: dict, limits: DetectionLimits
) -> dict:
    """Return observed corners and T_camera_board, or an explicit rejection."""
    if rgb.dtype != np.uint8 or rgb.shape != (
        intrinsics["height"],
        intrinsics["width"],
        3,
    ):
        raise ValueError("calibration RGB differs from the declared profile")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharpness < limits.sharpness:
        raise ValueError("calibration image is blurred")
    matrix, distortion = optics(intrinsics)
    matched = _corners(gray, board.create(), limits)
    camera_board, residual = _pose(
        matched["objects"], matched["images"], matrix, distortion, limits
    )
    return {
        "corner_ids": matched["ids"].ravel().tolist(),
        "image_points": matched["images"].reshape(-1, 2).tolist(),
        "object_points_m": matched["objects"].reshape(-1, 3).tolist(),
        "T_camera_board": camera_board.tolist(),
        "reprojection_px": residual,
        "sharpness": sharpness,
        "coverage": matched["coverage"],
    }


def _corners(gray, native, limits):
    # OpenCV's generated Python stub omits the documented tuple return type.
    # pylint: disable-next=unpacking-non-sequence
    corners, ids, _, _ = cv2.aruco.CharucoDetector(native).detectBoard(gray)
    if (
        ids is None
        or len(ids) < limits.corners
        or native.checkCharucoCornersCollinear(ids)
    ):
        raise ValueError("insufficient non-collinear ChArUco corners")
    coverage = cv2.contourArea(cv2.convexHull(corners)) / gray.size
    if coverage < limits.coverage:
        raise ValueError("board image coverage is insufficient")
    objects, images = native.matchImagePoints(corners, ids)
    return {
        "objects": objects,
        "images": images,
        "ids": ids,
        "coverage": coverage,
    }


def _pose(objects, images, matrix, distortion, limits):
    success, rotations, translations, _ = cv2.solvePnPGeneric(
        objects,
        images,
        matrix,
        distortion,
        flags=cv2.SOLVEPNP_IPPE,
    )
    candidates = []
    if success:
        for rotation, translation in zip(rotations, translations):
            candidate = _candidate(
                rotation, translation, objects, images, (matrix, distortion)
            )
            if candidate is not None:
                candidates.append(candidate)
    return _choose(candidates, limits)


def _candidate(rotation, translation, objects, images, optics_pair):
    candidate = geometry.pose(np.r_[translation.ravel(), rotation.ravel()])
    points = objects.reshape(-1, 3) @ candidate[:3, :3].T + candidate[:3, 3]
    if np.min(points[:, 2]) <= 0:
        return None
    projected = cv2.projectPoints(objects, rotation, translation, *optics_pair)[
        0
    ]
    residual = float(
        np.sqrt(
            np.mean(
                np.sum(
                    (projected.reshape(-1, 2) - images.reshape(-1, 2)) ** 2,
                    axis=1,
                )
            )
        )
    )
    return residual, candidate


def _choose(candidates, limits):
    candidates.sort(key=lambda value: value[0])
    if not candidates or candidates[0][0] > limits.reprojection_px:
        raise ValueError("board PnP failed positive-depth/reprojection checks")
    if len(candidates) > 1:
        residual, best = candidates[0]
        alternative_error, alternative = candidates[1]
        if (
            alternative_error - residual < limits.ambiguity_gap_px
            and geometry.error(best, alternative)["rotation_rad"] > 0.01
        ):
            raise ValueError("planar board pose is ambiguous")
    return candidates[0][1], candidates[0][0]

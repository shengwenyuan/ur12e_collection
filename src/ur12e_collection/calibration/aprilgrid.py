"""Metric AprilGrid corners matching the supplied actual-size PDF."""

import dataclasses

import cv2
import numpy as np

from ur12e_collection.calibration import board


@dataclasses.dataclass(frozen=True)
class Grid:
    """IDs increase rightward, then upward; origin is tag zero bottom-left."""

    tag_m: float = 0.028
    gap_m: float = 0.0084

    def __post_init__(self):
        if any(not np.isfinite(v) or v <= 0 for v in (self.tag_m, self.gap_m)):
            raise ValueError(
                "measured tag edge and gap must be positive meters"
            )

    def points(self, ids) -> np.ndarray:
        """Map decoded corners to the PDF tags, rotated 180 degrees."""
        ids = np.asarray(ids).reshape(-1)
        if (
            not np.issubdtype(ids.dtype, np.integer)
            or len(set(ids.tolist())) != len(ids)
            or np.any((ids < 0) | (ids >= 24))
        ):
            raise ValueError("AprilGrid requires distinct IDs in 0..23")
        origins = np.c_[ids % 4, ids // 4, np.zeros(len(ids))]
        corners = np.array([[1, 0, 0], [0, 0, 0], [0, 1, 0], [1, 1, 0]])
        return (
            (
                origins[:, None, :] * (self.tag_m + self.gap_m)
                + corners[None, :, :] * self.tag_m
            )
            .reshape(-1, 3)
            .astype(np.float32)
        )


def detect(rgb: np.ndarray, grid: Grid, limits: board.DetectionLimits) -> dict:
    """Detect without a camera matrix; reject blur and inadequate support."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("AprilGrid detection requires uint8 RGB")
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharpness < limits.sharpness:
        raise ValueError("calibration image is blurred")
    dictionary = cv2.aruco.getPredefinedDictionary(
        cv2.aruco.DICT_APRILTAG_36h11
    )
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    # OpenCV native return annotations omit the tuple result.
    # pylint: disable-next=unpacking-non-sequence
    corners, ids, _ = cv2.aruco.ArucoDetector(
        dictionary, parameters
    ).detectMarkers(gray)
    if ids is None or len(ids) < 4 or len(ids) * 4 < limits.corners:
        raise ValueError("at least four visible AprilGrid tags required")
    order = np.argsort(ids.ravel())
    ids = ids.ravel()[order]
    objects = grid.points(ids)
    images = np.asarray(corners, np.float32)[order].reshape(-1, 2)
    coverage = cv2.contourArea(cv2.convexHull(images)) / gray.size
    if coverage < limits.coverage:
        raise ValueError("board image coverage is insufficient")
    return {
        "tag_ids": ids.tolist(),
        "image_points": images.tolist(),
        "object_points_m": objects.tolist(),
        "coverage": coverage,
        "sharpness": sharpness,
    }

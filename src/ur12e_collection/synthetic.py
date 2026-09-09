"""Explicit synthetic RGB-D source for software-only pipeline validation."""

import numpy as np

from ur12e_collection import codecs, contracts, matching, station


def configuration() -> dict:
    """Return a complete synthetic camera station with no motion credentials."""
    config = station.example()
    config["station_id"] = "synthetic"
    for role, camera in config["cameras"].items():
        camera["serial"] = role
    return config


def observations(config: dict) -> dict:
    """Provide visibly synthetic optics; never substitute for SDK readback."""
    return {
        role: {
            "source_id": camera["serial"],
            "model": camera["model"],
            "depth_scale_m": 0.000123,
            "color_intrinsics": {
                "width": 640,
                "height": 480,
                "fx": 400,
                "fy": 400,
                "ppx": 320,
                "ppy": 240,
            },
        }
        for role, camera in config["cameras"].items()
    }


def frame(
    role: str, index: int, clock_id: str, receipt: int, timestamp: int
) -> matching.Frame:
    """Create owned arrays and truthful synthetic acquisition/receipt fields."""
    rgb = np.zeros((480, 640, 3), np.uint8)
    rgb[:, :, contracts.CAMERA_ROLES.index(role)] = 180
    left = index % 500
    rgb[120:280, left : left + 100] = [220, 80, 30]
    depth = (
        np.arange(480 * 640, dtype=np.uint32).reshape(480, 640) % 65536
    ).astype(np.uint16)
    color = contracts.Provenance(
        role, index, contracts.SampleTime(timestamp, "synthetic", receipt), True
    )
    raw_depth = contracts.Provenance(
        role,
        index,
        contracts.SampleTime(timestamp + 1000, "synthetic", receipt),
        True,
    )
    return matching.Frame(
        role,
        0,
        clock_id,
        timestamp,
        color,
        raw_depth,
        timestamp + 1000,
        codecs.Images(rgb, depth),
    )

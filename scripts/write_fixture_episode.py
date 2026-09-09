#!/usr/bin/env python3
"""Write an explicit synthetic M08/M11 episode without any hardware access."""

import argparse
import json
import pathlib
import time

import numpy as np

from ur12e_collection import codecs
from ur12e_collection import contracts
from ur12e_collection import matching
from ur12e_collection import storage

EPOCH_NS = 1_700_000_000_000_000_000


def snapshot() -> dict:
    """Use deliberately synthetic identities and explicit absent calibration."""
    return {
        "task": "offline-synthetic-fixture",
        "software_revision": "local-fixture",
        "clock_id": "fixture-unix",
        "clock_epoch": "unix",
        "calibration": None,
        "cameras": {
            role: {
                "source_id": "fixture-" + role,
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
            for role in contracts.CAMERA_ROLES
        },
    }


def frame(role: str, index: int) -> matching.Frame:
    """Generate changing RGB and exact raw depth with a deliberate time gap."""
    receipt = (index + (index >= 30)) * 33_333_333
    stamp = contracts.SampleTime(EPOCH_NS + receipt, "fixture-unix", receipt)
    provenance = contracts.Provenance("fixture-" + role, index, stamp, True)
    depth_provenance = contracts.Provenance(
        "fixture-" + role,
        index,
        contracts.SampleTime(stamp.source_ns + 1000, "fixture-unix", receipt),
        True,
    )
    rgb = np.zeros((480, 640, 3), np.uint8)
    rgb[:, :, contracts.CAMERA_ROLES.index(role)] = 180
    left = index % 500
    rgb[120:280, left : left + 100] = [220, 80, 30]
    depth = (
        np.arange(480 * 640, dtype=np.uint32).reshape(480, 640) % 65536
    ).astype(np.uint16)
    return matching.Frame(
        role,
        0,
        "fixture-unix",
        stamp.source_ns,
        provenance,
        depth_provenance,
        stamp.source_ns + 1000,
        codecs.Images(rgb, depth),
    )


def main() -> None:
    """Run offline pacing outside the recorder; never claim a real-time test."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=pathlib.Path)
    parser.add_argument("--frames", type=int, default=60)
    args = parser.parse_args()
    if not 1 <= args.frames <= 1200:
        parser.error("frames must be in [1, 1200]")
    matcher = matching.Matcher("fixture-unix")
    writer = storage.EpisodeWriter(args.output, snapshot(), simulated=True)
    deadline = time.monotonic() + 300
    try:
        for index in range(args.frames):
            # Only the offline producer waits; recorder submission never blocks.
            while writer.health()["queued"] and time.monotonic() < deadline:
                time.sleep(0.005)
            if time.monotonic() >= deadline:
                raise TimeoutError("offline fixture exceeded its time budget")
            for role in contracts.CAMERA_ROLES:
                item = frame(role, index)
                for result in matcher.push(
                    item, item.color.time.received_monotonic_ns
                ):
                    writer.submit(result)
        report = writer.finish()
    except BaseException:
        writer.abort()
        writer.wait_closed()
        raise
    print(
        json.dumps(
            {
                "simulated": True,
                "groups": report["verification"]["counts"]["camera/frame_set"],
                "mcap_bytes": report["verification"]["mcap_bytes"],
                "elapsed_s": report["elapsed_s"],
                "peak_queue": report["peak_queue"],
                "encode_total_ms": report["encode_total_ms"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

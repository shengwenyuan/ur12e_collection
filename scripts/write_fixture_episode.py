#!/usr/bin/env python3
"""Write an explicit synthetic M08/M11 episode without any hardware access."""

import argparse
import json
import pathlib
import time

from ur12e_collection import contracts
from ur12e_collection import matching
from ur12e_collection import storage, snapshots, synthetic

EPOCH_NS = 1_700_000_000_000_000_000


def snapshot() -> dict:
    """Use deliberately synthetic identities and explicit absent calibration."""
    config = synthetic.configuration()
    return snapshots.build(
        config,
        synthetic.observations(config),
        {
            "task": "offline-synthetic-fixture",
            "software_revision": "local-fixture",
            "clock_epoch": "unix",
            "clock_id": "fixture-unix",
            "clock_basis": "synthetic",
            "clock_validated": False,
            "simulated": True,
        },
    )


def frame(role: str, index: int) -> matching.Frame:
    """Generate changing RGB and exact raw depth with a deliberate time gap."""
    receipt = (index + (index >= 30)) * 33_333_333
    return synthetic.frame(
        role, index, "fixture-unix", receipt, EPOCH_NS + receipt
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

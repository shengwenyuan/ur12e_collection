"""Summarize recorded replay cost and timing without changing acceptance."""

import argparse
import json
import math
import pathlib

from ur12e_collection import mcap_read


def distribution(values):
    """Nearest-rank statistics; input and output use the same units."""
    if not values:
        return None
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean": sum(values) / len(values),
        "p95": ordered[math.ceil(len(values) * 0.95) - 1],
        "maximum": ordered[-1],
    }


def episode(root, item):
    """Read small MCAP records; decoding integrity has a separate verifier."""
    path = root / item["episode"] / "episode.mcap"
    ages, skews, delays, commands = [], [], [], []
    for topic, message in mcap_read.messages(
        path, ("leader/state", "control/command", "camera/frame_set")
    ):
        value = json.loads(message.data)
        if topic == "leader/state" and value.get("acquisition"):
            ages.append(
                (
                    value["provenance"]["time"]["received_monotonic_ns"]
                    - value["acquisition"]["start_ns"]
                )
                / 1e6
            )
        elif topic == "control/command":
            commands.append(
                value["provenance"]["time"]["received_monotonic_ns"]
            )
        elif topic == "camera/frame_set":
            skews.append(max(map(abs, value["skews_ns"].values())) / 1e6)
            delays.append(
                (
                    value["decided_monotonic_ns"]
                    - value["anchor"]["color"]["time"]["received_monotonic_ns"]
                )
                / 1e6
            )
    seconds = (item["stop_receipt_ns"] - item["start_receipt_ns"]) / 1e9
    recording = item["recording"]
    return {
        "episode": item["episode"],
        "seconds": seconds,
        "mcap_bytes": path.stat().st_size,
        "mcap_megabytes_per_second": path.stat().st_size / seconds / 1e6,
        "leader_acquisition_age_ms": distribution(ages),
        "accepted_max_view_skew_ms": distribution(skews),
        "matching_decision_delay_ms": distribution(delays),
        "command_gap_ms": distribution(
            [(b - a) / 1e6 for a, b in zip(commands, commands[1:])]
        ),
        "capture_timings": item["capture_timings"],
        "sources": item["sources"],
        "recording": {
            key: recording[key]
            for key in (
                "encode_total_ms",
                "encode_max_ms",
                "max_queue_delay_ms",
                "peak_queue",
                "peak_feedback_queue",
                "payload_bytes",
            )
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=pathlib.Path)
    args = parser.parse_args()
    report = json.loads((args.batch / "report.json").read_text())
    result = {
        "batch_status": report["status"],
        "batch_error": report.get("error"),
        "acceptance_not_reassessed": True,
        "episodes": [episode(args.batch, item) for item in report["episodes"]],
    }
    output = args.batch / "timing-cost.json"
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(output)


if __name__ == "__main__":
    main()

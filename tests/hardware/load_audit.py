"""Independent gates for a completed read-only camera/leader load batch."""

import argparse
import json
import pathlib

from simulation.acceptance import decisions
from ur12e_collection import projection, storage
from ur12e_collection.leader.probe import distribution


def audit(root):
    """Reopen each file and count real anchors; never pad an episode."""
    batch = json.loads((root / "cameras/report.json").read_text())
    leader = json.loads((root / "leader-report.json").read_text())
    if batch["state"] != "completed" or leader["state"] != "completed":
        raise ValueError("load batch did not complete")
    if len(batch["episodes"]) != 20:
        raise ValueError("fresh batch must contain 20 complete episodes")
    episodes = []
    for item in batch["episodes"]:
        path = root / "cameras" / item["episode"]
        seconds = (item["stop_receipt_ns"] - item["start_receipt_ns"]) / 1e9
        if seconds != 40:
            raise ValueError("episode duration differs from 40 seconds")
        verified = storage.verify_episode(path)
        rows = [
            json.loads(message.data)
            for _, message in projection.messages(
                path / "episode.mcap",
                ("camera/frame_set", "diagnostics/frame_rejection"),
            )
        ]
        quality = decisions(
            rows, item["start_receipt_ns"], item["stop_receipt_ns"]
        )
        for row in rows:
            if (
                row["reason"] == "accepted"
                and max(map(abs, row["skews_ns"].values())) > 16_700_000
            ):
                raise ValueError("accepted skew exceeds 16.7 ms")
        episodes.append(
            {
                "episode": item["episode"],
                "quality": quality,
                "verified": verified,
            }
        )
        print(item["episode"], "verified", flush=True)
    accepted = sum(item["quality"]["accepted"] for item in episodes)
    anchors = sum(item["quality"]["decisions"] for item in episodes)
    if accepted / anchors < 0.997:
        raise ValueError("batch grouping below 99.7 percent")
    if any(
        camera[key]
        for camera in batch["cameras"].values()
        for key in ("color_gaps", "depth_gaps", "depth_repeats")
    ):
        raise ValueError("source gaps or repeats occurred")
    previous = first = None
    gaps = []
    count = 0
    with (root / "samples.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if (
                row["sequence"] != count
                or len(row["position"]) != 7
                or any(row["errors"])
            ):
                raise ValueError("invalid leader identity or state")
            if previous:
                if (
                    row["epoch"] != previous["epoch"]
                    or row["start_ns"] < previous["end_ns"]
                ):
                    raise ValueError("leader chronology changed")
                gap = (row["start_ns"] - previous["start_ns"]) / 1e6
                if not 0 < gap <= 100:
                    raise ValueError("leader freshness gate failed")
                gaps.append(gap)
            first = row if first is None else first
            previous = row
            count += 1
    if count != leader["samples"] or not first or not previous:
        raise ValueError("leader evidence count differs")
    if set(leader["traffic"]) != {"0x2", "0x8a"}:
        raise ValueError("unexpected wire opcode")
    health_count = 0
    with (root / "health.jsonl").open() as stream:
        for line in stream:
            row = json.loads(line)
            if any(row["errors"]):
                raise ValueError("leader health status error")
            if any(row["torque"]) or any(row["hardware_error"]):
                raise ValueError("unexpected powered or faulted leader")
            health_count += 1
    if health_count < 1:
        raise ValueError("leader health evidence missing")
    return {
        "state": "PASS",
        "scope": "read-only load; no control or combined leader MCAP",
        "episodes": episodes,
        "accepted": accepted,
        "anchors": anchors,
        "leader_samples": count,
        "leader_hz": (count - 1)
        * 1e9
        / (previous["start_ns"] - first["start_ns"]),
        "leader_gap_ms": distribution(gaps),
        "leader_cpu_cores": leader["cpu_cores"],
        "health_records": health_count,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=pathlib.Path)
    args = parser.parse_args()
    result = {"state": "FAIL"}
    try:
        result = audit(args.root)
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        (args.root / "independent-audit.json").write_text(
            json.dumps(result, indent=2) + "\n"
        )

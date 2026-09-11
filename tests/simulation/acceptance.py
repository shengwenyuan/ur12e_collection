"""Independent final gates for actual URSim plus synthetic-camera batches."""

import argparse
import json
import pathlib

from ur12e_collection import mcap_read, storage


def decisions(items: list, start: int, stop: int, replay=None) -> dict:
    """Count every anchor, including boundary rejections, without resampling."""
    items.sort(key=lambda value: value["anchor"]["color"]["sequence"])
    if not items:
        raise ValueError("no wrist decisions")
    anchors = [item["anchor"]["color"] for item in items]
    if replay is None:
        expected_next = lambda value: value + 1
    else:
        stride = replay["sequence_stride"]
        positions = replay["wrist_sequences"]
        following = dict(
            zip(positions, positions[1:] + [positions[0] + stride])
        )
        expected_next = (
            lambda value: (value // stride) * stride + following[value % stride]
        )
    if any(
        b["sequence"] != expected_next(a["sequence"])
        for a, b in zip(anchors, anchors[1:])
    ):
        raise ValueError("wrist decisions have missing or repeated identities")
    receipts = [item["time"]["received_monotonic_ns"] for item in anchors]
    if (
        not 0 <= receipts[0] - start <= 50_000_000
        or not 0 < stop - receipts[-1] <= 50_000_000
        or any(not 0 < b - a for a, b in zip(receipts, receipts[1:]))
    ):
        raise ValueError("wrist decisions do not cover the capture interval")
    accepted = sum(item["reason"] == "accepted" for item in items)
    consecutive = maximum = 0
    for item in items:
        consecutive = 0 if item["reason"] == "accepted" else consecutive + 1
        maximum = max(maximum, consecutive)
    if accepted / len(items) < 0.995 or maximum > 2:
        raise ValueError("per-episode grouping quality gate failed")
    return {
        "accepted": accepted,
        "decisions": len(items),
        "acceptance": accepted / len(items),
        "max_consecutive_rejections": maximum,
        "max_receipt_gap_ms": max(
            (b - a for a, b in zip(receipts, receipts[1:])), default=0
        )
        / 1e6,
    }


def audit(root: pathlib.Path, count: int = 20, duration: float = 40) -> dict:
    """Reopen completed MCAP, ignoring prior success claims as evidence."""
    report = json.loads((root / "report.json").read_text(encoding="utf-8"))
    if (
        report.get("status") != "PASS"
        or report.get("error")
        or len(report["episodes"]) != count
    ):
        raise ValueError("batch did not complete the requested episode count")
    episodes = []
    for episode in report["episodes"]:
        name = episode["episode"]
        if pathlib.Path(name).name != name:
            raise ValueError("episode name is not local to the batch")
        elapsed = (
            episode["stop_receipt_ns"] - episode["start_receipt_ns"]
        ) / 1e9
        if not duration <= elapsed < duration + 0.15:
            raise ValueError("episode duration gate failed")
        verified = storage.verify_episode(root / name)
        context = episode["recording"]["snapshot"]["control"]
        if verified["counts"]["control/command"] / elapsed < (
            0.9 * context["control_hz"]
        ):
            raise ValueError("recorded control rate gate failed")
        replay = context.get("inputs", {}).get("cameras")
        for source in episode["sources"].values():
            if replay:
                if source["error"] or source["frames"] < 1:
                    raise ValueError("replay source integrity gate failed")
            elif any(
                source[key]
                for key in ("color_gaps", "depth_gaps", "depth_repeats")
            ):
                raise ValueError("native source integrity gate failed")
        items = [
            json.loads(message.data)
            for _, message in mcap_read.messages(
                root / name / "episode.mcap",
                ("camera/frame_set", "diagnostics/frame_rejection"),
            )
        ]
        quality = decisions(
            items,
            episode["start_receipt_ns"],
            episode["stop_receipt_ns"],
            replay,
        )
        if quality["accepted"] != verified["counts"]["camera/frame_set"]:
            raise ValueError("decision and payload counts differ")
        episodes.append({"episode": name, "seconds": elapsed, **quality})
    accepted = sum(item["accepted"] for item in episodes)
    total = sum(item["decisions"] for item in episodes)
    if accepted / total < 0.997:
        raise ValueError("batch grouping quality gate failed")
    return {
        "status": "PASS",
        "simulated": True,
        "episodes": episodes,
        "accepted": accepted,
        "decisions": total,
        "acceptance": accepted / total,
        "current_verifier": True,
        "all_depth_hashes_verified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=pathlib.Path)
    parser.add_argument("--episodes", type=int, default=20)
    parser.add_argument("--seconds", type=float, default=40)
    args = parser.parse_args()
    output = args.batch / "independent-audit.json"
    try:
        result = audit(args.batch, args.episodes, args.seconds)
    except Exception as error:
        result = {"status": "FAIL", "error": str(error)}
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "output": str(output),
                "error": result.get("error"),
            }
        )
    )
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

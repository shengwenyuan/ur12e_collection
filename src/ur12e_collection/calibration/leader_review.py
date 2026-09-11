"""Offline passive-motion analysis; UR alignment stays explicitly unverified."""

import argparse
import json
import pathlib
import statistics

from ur12e_collection.leader import mapping


def window(rows, start_ns, end_ns):
    """Use only wholly contained acquisitions in the final two-second hold."""
    selected = [
        r for r in rows if start_ns <= r["start_ns"] <= r["end_ns"] < end_ns
    ]
    if (
        len(selected) < 30
        or selected[-1]["start_ns"] - selected[0]["start_ns"] < 1_000_000_000
    ):
        return {"state": "insufficient", "samples": len(selected)}
    if any(
        b["start_ns"] - a["start_ns"] > 100_000_000
        for a, b in zip(selected, selected[1:])
    ):
        return {"state": "gap", "samples": len(selected)}
    axes = list(zip(*(r["position"] for r in selected)))
    return {
        "state": "measured",
        "samples": len(selected),
        "center": [statistics.median(v) for v in axes],
        "spread": [max(v) - min(v) for v in axes],
        "last_sample": selected[-1],
    }


def analyze(folder: pathlib.Path) -> dict:
    """Report candidates and unresolved physical facts, never activate them."""
    report = json.loads((folder / "report.json").read_text())
    rows = [
        json.loads(line)
        for line in (folder / "samples.jsonl").read_text().splitlines()
    ]
    for index, row in enumerate(rows):
        if (
            row["epoch"] != report["epoch"]
            or len(row["position"]) != 7
            or row["errors"] != [0] * 7
        ):
            raise ValueError("invalid sample identity or motor errors")
        for key in ("sequence", "start_ns", "end_ns"):
            mapping.integer(row[key])
        if row["start_ns"] < 0 or row["end_ns"] < row["start_ns"]:
            raise ValueError("invalid acquisition interval")
        for value in row["position"]:
            mapping.integer(value)
        if index and (
            row["sequence"] != rows[index - 1]["sequence"] + 1
            or row["start_ns"] < rows[index - 1]["end_ns"]
        ):
            raise ValueError("discontinuous sample order")
    holds = {
        p["name"]: window(
            rows,
            report["start_ns"] + int(max(p["start_s"], p["end_s"] - 2) * 1e9),
            report["start_ns"] + int(p["end_s"] * 1e9),
        )
        for p in report["phases"]
        if any(
            word in p["name"]
            for word in (
                "hold_",
                "rest",
                "reference_start",
                "reference_end",
                "gripper_",
            )
        )
    }
    joints = [_joint(holds, motor) for motor in range(1, 7)]
    return {
        "capture_state": report["state"],
        "source_error": report.get("error"),
        "operator_declared_home": report["operator_declared_home"],
        "holds": holds,
        "joints": joints,
        "gripper": _gripper(holds),
        "branch_discontinuities": {
            str(i + 1): sum(
                abs(b["position"][i] - a["position"][i]) > 2048
                for a, b in zip(rows, rows[1:])
            )
            for i in range(7)
        },
        "motion_ready": False,
        "ur_directions_verified": False,
        "physical_home_verified": False,
        "mechanical_ranges_verified": False,
        "scale_verified": False,
    }


def _joint(holds, motor):
    names = [
        f"j{motor}_{suffix}"
        for suffix in ("rest", "hold_a", "hold_b", "rest_end")
    ]
    windows = [
        holds.get(names[0], holds.get("reference_start", {"state": "missing"})),
        holds[names[1]],
        holds[names[2]],
        holds.get(names[3], holds.get("reference_end", {"state": "missing"})),
    ]
    if any(w["state"] != "measured" for w in windows):
        return {"motor": motor, "state": "incomplete"}
    rest = windows[0]["last_sample"]["position"]
    a, b = windows[1]["center"], windows[2]["center"]
    end = windows[3]["last_sample"]["position"]
    axis = motor - 1
    da, db = a[axis] - rest[axis], b[axis] - rest[axis]
    return {
        "motor": motor,
        "state": "observed",
        "delta_a_counts": da,
        "delta_b_counts": db,
        "opposite_excursions": da * db < 0 and min(abs(da), abs(db)) >= 6,
        "return_error_counts": end[axis] - rest[axis],
        "target_hold_spreads": [w["spread"][axis] for w in windows],
        "other_joint_delta_counts": {
            str(i + 1): max(abs(a[i] - rest[i]), abs(b[i] - rest[i]))
            for i in range(7)
            if i != axis
        },
        "ur_sign": None,
        "return_reference": (
            "per_joint" if names[3] in holds else "final_whole_arm"
        ),
    }


def _gripper(holds):
    result = {}
    for endpoint in ("open", "closed"):
        values = [
            value
            for name, value in holds.items()
            if name.startswith(f"gripper_{endpoint}_")
        ]
        if not values:
            return {"state": "incomplete"}
        if any(v["state"] != "measured" for v in values):
            return {"state": "incomplete"}
        centers = [v["center"][6] for v in values]
        result[endpoint] = {
            "candidate_count": round(statistics.median(centers)),
            "approaches": len(values),
            "repeat_spread_counts": max(centers) - min(centers),
            "hold_spreads": [v["spread"][6] for v in values],
        }
    stable = all(
        v["repeat_spread_counts"] <= 2 and max(v["hold_spreads"]) <= 2
        for v in result.values()
    )
    travel = abs(
        result["open"]["candidate_count"] - result["closed"]["candidate_count"]
    )
    return result | {
        "state": (
            "candidate" if stable and 20 <= travel < 2048 else "needs_review"
        ),
        "repeatability_verified": stable
        and all(v["approaches"] >= 3 for v in result.values()),
        "robotiq_open_raw": 0,
        "robotiq_closed_raw": 255,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    review = analyze(args.folder)
    with args.output.open("x") as output:
        output.write(json.dumps(review, indent=2) + "\n")

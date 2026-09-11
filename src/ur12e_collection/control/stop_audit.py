"""Offline stop/hold audit; SDK acknowledgments alone never establish PASS."""

import argparse
import json
import math
import pathlib

from ur12e_collection.control import settling

POLICY = "settling-v2"


def direction_gates(events, samples, before):
    """Check the exact READY request and observed joint-space direction."""
    plan = events["run_plan"][0]["plan"]
    parameters = plan["parameters"]
    initial = list(map(math.radians, plan["initial_deg"]))
    target = list(map(math.radians, [0, -90, -90, -90, 90, 0]))
    tolerance = math.radians(0.1)
    return {
        "reviewed_command": (
            events["move_request"][0].get("parameters") == parameters
            and parameters["target_deg"] == [0, -90, -90, -90, 90, 0]
            and parameters["speed_deg_s"] == 1
            and parameters["acceleration_deg_s2"] == 2
            and events["stop_request"][0].get("deceleration_deg_s2") == 2
        ),
        "toward_ready": all(
            min(a, b) - tolerance <= q <= max(a, b) + tolerance
            for row in samples
            for q, a, b in zip(row["q"], initial, target)
        ),
        "interrupted_before_arrival": max(
            abs(a - b) for a, b in zip(before[-1]["q"], target)
        )
        > tolerance,
    }


def audit(rows):
    """Reject missing evidence before measuring the stop/hold gates."""
    # One audit retains named intermediates for review of independent gates.
    # pylint: disable=too-many-locals
    events = {}
    for row in rows:
        events.setdefault(row["event"], []).append(row)
    required = (
        "run_plan",
        "move_request",
        "move_ack",
        "sigint_sent",
        "sigint_handled",
        "stop_request",
        "stop_ack",
        "owner_finished",
        "observation_complete",
    )
    missing = [key for key in required if len(events.get(key, [])) != 1]
    failures = [
        key
        for key in ("owner_error", "feedback_error", "observation_fault")
        if events.get(key)
    ]
    samples = events.get("feedback", [])
    if missing or failures or len(samples) < 2:
        return {
            "state": "FAIL",
            "policy": POLICY,
            "missing_or_duplicate_events": missing,
            "error_events": failures,
            "samples": len(samples),
        }

    def stamp(key):
        return events[key][0]["monotonic_ns"] / 1e9

    signal_at, stop_at = stamp("sigint_sent"), stamp("stop_request")

    def speed(row):
        return math.degrees(max(map(abs, row["qd"])))

    before = [
        r
        for r in samples
        if signal_at - 0.2 <= r["monotonic_ns"] / 1e9 <= signal_at
    ]
    after = [r for r in samples if r["monotonic_ns"] / 1e9 >= stop_at]
    window = settling.Standstill()
    settled = next(
        (
            r
            for r in after
            if window.update(r["qd"], r["source_s"], r["monotonic_ns"])
        ),
        None,
    )
    if not before or not after or settled is None:
        return {
            "state": "FAIL",
            "policy": POLICY,
            "reason": "missing pre-signal motion or post-stop rest",
        }
    held = [r for r in after if r["monotonic_ns"] >= settled["monotonic_ns"]]
    source = [r["source_s"] for r in samples]
    host = [r["monotonic_ns"] / 1e9 for r in samples]
    # Repeated cached reads do not improve freshness; bound each plateau too.
    advanced = host[0]
    cache_age = 0
    for index in range(1, len(samples)):
        if source[index] > source[index - 1]:
            advanced = host[index]
        cache_age = max(cache_age, host[index] - advanced)
    metrics = {
        "signal_delay_s": signal_at - stamp("move_request"),
        "stop_dispatch_delay_s": stop_at - signal_at,
        "stop_time_s": settled["monotonic_ns"] / 1e9 - stop_at,
        "observed_peak_deg_s": max(map(speed, samples)),
        "hold_peak_deg_s": max(map(speed, held)),
        "hold_drift_deg": max(
            math.degrees(abs(a - b))
            for r in held
            for a, b in zip(r["q"], settled["q"])
        ),
        "post_signal_observation_s": stamp("observation_complete") - signal_at,
        "max_source_gap_s": max(b - a for a, b in zip(source, source[1:])),
        "max_receipt_gap_s": max(b - a for a, b in zip(host, host[1:])),
        "max_cache_age_s": cache_age,
    }
    delay = events["run_plan"][0]["plan"]["parameters"]["interrupt_after_s"]
    timer_reason = events["sigint_sent"][0]["reason"]
    gates = {
        "timed_sigint": (
            isinstance(delay, int)
            and not isinstance(delay, bool)
            and delay in (2, 10)
            and (
                timer_reason == "scheduled_timer"
                or (delay == 2 and timer_reason == "two_second_timer")
            )
            and delay <= metrics["signal_delay_s"] <= delay + 0.1
        ),
        "moving_at_interrupt": max(map(speed, before)) > 0.1,
        "prompt_stop_request": 0 <= metrics["stop_dispatch_delay_s"] <= 0.1,
        "stable_within_two_seconds": (
            0 <= metrics["stop_time_s"] <= settling.STOP_TIMEOUT_NS / 1e9
        ),
        "motion_speed": metrics["observed_peak_deg_s"] <= 1.2,
        "hold": metrics["hold_peak_deg_s"] <= math.degrees(settling.STOP_SPEED)
        and metrics["hold_drift_deg"] <= math.degrees(settling.HOLD_DRIFT),
        "observation_duration": (
            metrics["post_signal_observation_s"] >= 30
            and stamp("observation_complete") - host[-1] <= 0.05
        ),
        "feedback_continuity": (
            all(b >= a for a, b in zip(source, source[1:]))
            and all(b > a for a, b in zip(host, host[1:]))
            and source[-1] > source[0]
            and max(
                metrics[k]
                for k in (
                    "max_source_gap_s",
                    "max_receipt_gap_s",
                    "max_cache_age_s",
                )
            )
            <= 0.25
        ),
        "normal_state": all(
            (r["robot"], r["safety"]) == (7, 1) for r in samples
        ),
        "program_stopped": all(r["runtime"] == 1 for r in samples[-100:]),
    }
    gates.update(direction_gates(events, samples, before))
    return {
        "state": "PASS" if all(gates.values()) else "FAIL",
        "policy": POLICY,
        "gates": gates,
        "metrics": metrics,
        "samples": len(samples),
    }


def main(argv: list[str] | None = None):
    """Write an audit alongside preserved raw evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path)
    args = parser.parse_args(argv)
    rows = [
        json.loads(line)
        for line in (args.directory / "trace.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    result = audit(rows)
    output = args.output or args.directory / f"audit-{POLICY}.json"
    with output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["state"] == "PASS" else 1)


if __name__ == "__main__":
    main()

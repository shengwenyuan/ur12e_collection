"""Headless precision acceptance using synthetic leader input and local Isaac."""

import argparse
import collections
import dataclasses
import json
import math
import pathlib
import sys
import time

from ur12e_collection import timing
from ur12e_collection.control import guards, model, owner, records, settling
import precision_cases as cases
from ur12e_collection.followers import config as configuration, local
from ur12e_collection.leader import (
    audit,
    episode,
    input as leader_input,
    mapping,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
POSE = (0.0, -1.85, -2.1, -1.5 * math.pi + 3.95, math.pi / 2, 0.0)


class Leader:
    """Test-only source; no serial import, USB device or motor write."""

    origin = {"kind": "synthetic", "fixture": "height-precision-v1"}

    def __init__(self, calibration, fault=None, case="sweep"):
        self.calibration = calibration
        self.fault = fault
        self.case = case
        self.rows = collections.deque(maxlen=16)
        self.began = None
        self.sequence = 0

    def samples(self, now):
        if self.rows and now - self.rows[-1].start_ns < 8_000_000:
            return tuple(self.rows)
        elapsed = 0 if self.began is None else (now - self.began) / 1e9
        if self.fault == "leader" and elapsed >= 8:
            return tuple(self.rows)
        delta = cases.trajectory(elapsed, self.case)
        counts = tuple(
            2200
            + round(q / (axis.sign * axis.ratio * mapping.RADIANS_PER_COUNT))
            for q, axis in zip(delta, self.calibration.joints)
        )
        self.rows.append(
            episode.Sample(
                "generated-precision", self.sequence, now, now, (*counts, 2200)
            )
        )
        self.sequence += 1
        return tuple(self.rows)


def prepare(args):
    """Produce a private physics fixture; never change station HOME/config."""
    args.output.mkdir(parents=True, exist_ok=False)
    value = json.loads((ROOT / "config/teleop.isaac-physics.json").read_text())
    real = json.loads((ROOT / "config/teleop.ur.json").read_text())
    value["limits"] = real["limits"] | {
        "ready": POSE,
        # Existing M14 solver standstill tolerance, for fixture engagement.
        # Controller.halt still applies the unchanged strict real stop gate.
        "stopped_speed": 0.01,
        "arrival": 0.01,
    }
    value["guards"] = real["guards"]
    value["leader"]["calibration"] = str(ROOT / "config/gello.relative.json")
    value["scene"]["root"] = str(args.scene_root.resolve())
    value["follower"]["endpoint"] = str(args.output / "follower.sock")
    spec = json.loads((ROOT / "config/precision.example.json").read_text())
    spec["urdf"] = str(args.scene_root / "assets/robots/ur12e/ur12e.urdf")
    if args.no_correction:
        spec["correction_seconds"] = 1e12
    value["precision"] = spec
    (args.output / "config.json").write_text(json.dumps(value, indent=2) + "\n")


def settle(device, limits, seconds=12):
    """Wait for actual solver standstill before capturing the fixture seed."""
    began = time.monotonic()
    stable = None
    while time.monotonic() - began < seconds:
        device.heartbeat()
        state = device.read()
        if max(map(abs, state.qd)) <= limits.stopped_speed:
            stable = stable or time.monotonic()
            if time.monotonic() - stable >= 0.3:
                return state
        else:
            stable = None
        time.sleep(1 / 120)
    raise RuntimeError(f"physics did not settle: qd={state.qd}")


def run(args):
    """Exercise the shared input, controller and audit against solver feedback."""
    value = configuration.load(args.output / "config.json")
    if value["follower"]["backend"] != "isaac_physics":
        raise ValueError("acceptance requires the local physics backend")
    policy = guards.Policy(**value["guards"])
    calibration = mapping.load(value["leader"]["calibration"])
    device = local.Transport(**value["follower"])
    report = {"passed": False, "hardware_connected": False}
    controller = None
    samples = []
    active = None
    try:
        state = settle(device, value["limits"])
        # Initial placement/settling belongs to this isolated fixture only.
        # Capturing its measured seed removes drive gravity bias from HOME checks.
        limits = dataclasses.replace(value["limits"], ready=state.q)
        report["measured_fixture_seed"] = dataclasses.asdict(state)
        source = Leader(calibration, args.fault, args.case)
        for _ in range(9):
            source.samples(time.monotonic_ns())
            device.heartbeat()
            state = device.read()
            time.sleep(0.0085)
        started = time.monotonic_ns()
        controller = owner.Controller(device, limits)
        controller.tick(started)
        active = leader_input.Input(
            source,
            calibration,
            limits,
            controller.progress.feedback,
            started,
            guards=policy,
            precision=value["precision"],
        )
        controller.engage(active.sample(started), started)
        source.began = started
        checker = audit.Audit(active.context(), started)
        factory = records.Records(
            {"leader_id": "gello", "command_id": "isaac"}, simulated=True
        )
        (args.output / "context.json").write_text(json.dumps(active.context()))
        tracking = guards.Tracking(policy)
        previous = started
        deadline = started + 8_333_333
        frozen = None
        with (args.output / "trace.jsonl").open("w") as trace:
            while (time.monotonic_ns() - started) / 1e9 < cases.DURATIONS[
                args.case
            ]:
                now = time.monotonic_ns()
                if now < deadline:
                    time.sleep((deadline - now) / 1e9)
                    continue
                controller.tick(now)
                measured = controller.progress.feedback
                tracking.check(controller.progress.target.q, measured, now)
                if args.fault == "feedback" and now - started >= 8_000_000_000:
                    frozen = frozen or measured
                mapping_began = time.monotonic_ns()
                target = active.sample(mapping_began, frozen or measured)
                mapping_ns = time.monotonic_ns() - mapping_began
                controller.follow(target, time.monotonic_ns())
                intent = factory.intent(target, active)
                checker.intent(intent)
                checker.sent(factory.sent(target, time.monotonic_ns()))
                row = {
                    "elapsed_s": (now - started) / 1e9,
                    "feedback": dataclasses.asdict(measured),
                    "target": dataclasses.asdict(target),
                    "intent": dataclasses.asdict(intent),
                    "velocity": active.conditioner.velocity,
                    "cycle_ns": now - previous,
                    "mapping_ns": mapping_ns,
                }
                trace.write(json.dumps(row, allow_nan=False) + "\n")
                samples.append(row)
                previous = now
                deadline = timing.next_deadline(
                    deadline, time.monotonic_ns(), 8_333_333
                )
        report.update(summarize(samples, args.case))
        report["algorithm_passed"] = (
            report["coverage_passed"] and report["settled_tail"]
        )
    except (
        Exception
    ) as error:  # Retain failure evidence before simulator cleanup.
        report["error"] = f"{type(error).__name__}: {error}"
        expected = {
            "leader": "leader input is stale",
            "feedback": "precision feedback is stale",
        }.get(args.fault)
        report["expected_fault_rejected"] = bool(
            expected and expected in str(error)
        )
        if controller is not None:
            report["stop_state"] = controller.state
            report["last_feedback"] = dataclasses.asdict(
                controller.progress.feedback
            )
    finally:
        if samples and "samples" not in report:
            report.update(summarize(samples, args.case))
        if active is not None:
            active.close()
        if controller is not None:
            try:
                report.update(stop(controller, device, args.output))
                report["passed"] = bool(
                    (
                        report.get("algorithm_passed")
                        or report.get("expected_fault_rejected")
                    )
                    and report["strict_stop_passed"]
                )
            except Exception as error:
                report["stop_error"] = str(error)
            try:
                controller.close()
            except Exception as error:
                report["close_error"] = str(error)
                report["passed"] = False
        device.close()
        (args.output / "report.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report, indent=2), flush=True)
    return 0 if report["passed"] else 1


def stop(controller, device, output):
    """Preserve the original rejection and measure the actual stop separately."""
    began = time.monotonic_ns()
    if controller.state != "fault":
        controller.halt(began)
    monitor = settling.Standstill(controller.limits.freshness_ns)
    with (output / "stop.jsonl").open("w") as stream:
        while time.monotonic_ns() - began <= settling.STOP_TIMEOUT_NS:
            now = time.monotonic_ns()
            if controller.state == "fault":
                feedback = device.read()
                if now - feedback.received_ns > controller.limits.freshness_ns:
                    raise RuntimeError("stop feedback is stale")
            else:
                feedback = controller.tick(now)
            stream.write(json.dumps(dataclasses.asdict(feedback)) + "\n")
            if monitor.update(feedback.qd, feedback.timestamp, now):
                return {
                    "strict_stop_passed": True,
                    "stop_state": controller.state,
                    "stop_seconds": (now - began) / 1e9,
                    "stop_confirmed_ns": feedback.received_ns,
                    "stopped_q": feedback.q,
                }
            time.sleep(1 / 120)
    return {
        "strict_stop_passed": False,
        "stop_state": controller.state,
        "stop_seconds": (time.monotonic_ns() - began) / 1e9,
    }


def summarize(rows, case):
    """Report motion/lag metrics separately from the already-run command audit."""
    states = [r["intent"]["mapping_state"] for r in rows]
    heights = [s["z_m"] for s in states]
    gains = [s["gain"] for s in states]
    lag = [
        model.distance(tuple(s["accepted"]), tuple(r["target"]["q"]))
        for s, r in zip(states, rows)
    ]
    corrections = [
        model.distance(
            tuple(s["accepted"]), tuple(r["intent"]["joint_positions_rad"])
        )
        for s, r in zip(states, rows)
    ]

    def joint_at(t):
        return min(rows, key=lambda r: abs(r["elapsed_s"] - t))["feedback"][
            "q"
        ][0]

    return {
        "samples": len(rows),
        "command_hz": len(rows) / rows[-1]["elapsed_s"],
        "z_range_m": [min(heights), max(heights)],
        "gain_range": [min(gains), max(gains)],
        "maximum_pending_rad": max(lag),
        "maximum_correction_rad": max(corrections),
        "base_residual_travel_2_3_to_5s_rad": abs(joint_at(5) - joint_at(2.3)),
        "maximum_cycle_ms": max(r["cycle_ns"] for r in rows) / 1e6,
        "mapping_p99_ms": sorted(r["mapping_ns"] for r in rows)[
            int(len(rows) * 0.99)
        ]
        / 1e6,
        "coverage_passed": (
            (min(gains) <= 0.5001 and max(gains) >= 0.9999)
            if case in ("sweep", "deep")
            else True
        ),
        "settled_tail": max(
            (
                abs(v)
                for r in rows
                if r["elapsed_s"] >= cases.DURATIONS[case] - 3
                for v in r["velocity"]
            ),
            default=math.inf,
        )
        < 1e-5,
        "case": case,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run"))
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--scene-root", type=pathlib.Path)
    parser.add_argument("--no-correction", action="store_true")
    parser.add_argument("--fault", choices=("leader", "feedback"))
    parser.add_argument(
        "--case", choices=tuple(cases.DURATIONS), default="sweep"
    )
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.operation == "prepare":
        if args.scene_root is None:
            parser.error("--scene-root is required for preparation")
        prepare(args)
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

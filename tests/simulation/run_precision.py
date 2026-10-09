"""Own isolated Isaac lifetimes through readiness, motion and stop evidence."""

import argparse
import json
import os
import pathlib
import signal
import shutil
import subprocess
import sys
import tempfile
import time

import precision
from ur12e_collection.control import model, settling


def run(args):
    artifacts = args.scene_root / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="precision-", dir=artifacts
    ) as directory:
        adapter = pathlib.Path(directory) / "contacts.py"
        shutil.copyfile(
            pathlib.Path(__file__).with_name("contact_adapter.py"), adapter
        )
        return execute(args, adapter)


def execute(args, adapter):
    precision.prepare(args)
    path = args.output / "config.json"
    config = json.loads(path.read_text())
    config["scene"]["adapter"] = str(adapter)
    # The corrected fixed-base model must meet the unchanged real stop gate.
    config["limits"]["stopped_speed"] = 0.00017453292519943296
    if args.solver:
        config["physics"]["solver_type"] = args.solver
    if args.step_hz:
        config["physics"]["step_hz"] = args.step_hz
    if args.adapter:
        config["diagnostic_adapter"] = str(args.adapter.resolve())
    path.write_text(json.dumps(config, indent=2))
    command = [
        sys.executable,
        str(precision.ROOT / "scripts/isaac_follower.py"),
        "--config",
        str(path),
        "--headless",
        "--duration",
        "300",
        "--report",
        str(args.output / "service.json"),
    ]
    with (args.output / "isaac.log").open("w") as log:
        server = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 90
            endpoint = pathlib.Path(config["follower"]["endpoint"])
            while not endpoint.exists():
                if server.poll() is not None:
                    raise RuntimeError(
                        f"Isaac exited before readiness: {server.returncode}"
                    )
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Isaac startup timed out before any owner connected"
                    )
                time.sleep(0.1)
            precision.run(args)
            # Observe release independently, before terminating this server.
            deadline = time.monotonic() + 3
            service = {}
            while time.monotonic() < deadline:
                path = args.output / "service.json"
                if path.exists():
                    service = json.loads(path.read_text())
                time.sleep(0.1)
            report_path = args.output / "report.json"
            report = json.loads(report_path.read_text())
            report["ownership_released"] = (
                service.get("owner") is None and service.get("active") is False
            )
        finally:
            if server.poll() is None:
                os.killpg(server.pid, signal.SIGINT)
                try:
                    server.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    os.killpg(server.pid, signal.SIGTERM)
                    server.wait(timeout=10)
    solver_rows = list(
        map(json.loads, (args.output / "solver.jsonl").read_text().splitlines())
    )
    table_contacts = [
        (r["sample"]["acquired_ns"], p)
        for r in solver_rows
        for c in r["contacts"]
        if any(actor.startswith("/World/Table/") for actor in c["actors"])
        for p in c["points"]
        if sum(v * v for v in p["impulse"]) > 1e-12
    ]
    report["loaded_table_contact_points"] = len(table_contacts)
    stamp = report.get("last_feedback", {}).get("received_ns", 0)
    report["contact_rejection_passed"] = bool(
        args.case == "deep"
        and report.get("error")
        in (
            "ControlError: actual joint speed exceeded test limit",
            "ControlError: follower tracking error persisted",
        )
        and any(abs(ns - stamp) <= 100_000_000 for ns, _ in table_contacts)
    )
    if report.get("strict_stop_passed"):
        samples = [
            row["sample"]
            for row in solver_rows
            if row["sample"]["acquired_ns"] >= report["stop_confirmed_ns"]
        ]
        drift = max(
            model.distance(tuple(s["q"]), tuple(report["stopped_q"]))
            for s in samples
        )
        speed = max(abs(v) for s in samples for v in s["qd"])
        seconds = (samples[-1]["acquired_ns"] - samples[0]["acquired_ns"]) / 1e9
        report.update(
            post_release_drift_rad=drift,
            post_release_speed_rad_s=speed,
            post_release_seconds=seconds,
            post_release_hold_passed=seconds >= 2
            and drift <= settling.HOLD_DRIFT
            and speed <= settling.HOLD_SPEED,
        )
    report["passed"] = bool(
        (
            report.get("algorithm_passed")
            or report.get("expected_fault_rejected")
            or report["contact_rejection_passed"]
        )
        and report.get("strict_stop_passed")
        and report["ownership_released"]
        and report.get("post_release_hold_passed")
    )
    report_path.write_text(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--scene-root", type=pathlib.Path, required=True)
    parser.add_argument(
        "--case", choices=tuple(precision.cases.DURATIONS), default="sweep"
    )
    parser.add_argument("--fault", choices=("leader", "feedback"))
    parser.add_argument("--no-correction", action="store_true")
    parser.add_argument("--solver", choices=("PGS", "TGS"))
    parser.add_argument("--step-hz", type=int)
    parser.add_argument("--adapter", type=pathlib.Path)
    args = parser.parse_args()
    args.output, args.scene_root = (
        args.output.resolve(),
        args.scene_root.resolve(),
    )
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

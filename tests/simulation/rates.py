"""Bounded URSim-only command-rate comparison; no production rate override."""

import contextlib
import dataclasses
import json
import pathlib
import resource
import time

from ur12e_collection.control.owner import Controller
from ur12e_collection.control.ur import URTransport
from ur12e_collection.leader.probe import distribution
from ur12e_collection.timing import next_deadline
from ur12e_collection.simulation import connection, profile, targets


@contextlib.contextmanager
def motion(station, hz):
    """Create a test SDK owner only inside the verified simulator lease."""
    import rtde_control

    if (
        connection.dashboard(station.address, "running")
        != "Program running: false"
    ):
        raise RuntimeError("simulator already has a running program")
    control = rtde_control.RTDEControlInterface(
        station.address,
        float(hz),
        rtde_control.RTDEControlInterface.FLAG_UPLOAD_SCRIPT
        | rtde_control.RTDEControlInterface.FLAG_UPPER_RANGE_REGISTERS,
    )
    transport = URTransport(
        control, station.receiver, 1 / hz, owns_receiver=False
    )
    try:
        if not control.setWatchdog(5):
            raise RuntimeError("watchdog setup failed")
        yield transport
    finally:
        transport.close()


def wait_hold(owner):
    deadline = time.monotonic() + 60
    while owner.state != "hold":
        if time.monotonic() > deadline:
            raise TimeoutError("simulator did not settle")
        owner.tick(time.monotonic_ns())
        time.sleep(0.01)


def compare(station, hz, root):
    report = {"requested_command_hz": hz, "state": "failed", "simulated": True}
    stamps, costs, samples = [], [], []
    with motion(station, hz) as transport:
        owner = Controller(transport, profile.LIMITS, "simulation-wave")
        try:
            owner.tick(time.monotonic_ns())
            owner.go_ready(time.monotonic_ns())
            wait_hold(owner)
            started = time.monotonic_ns()
            wave = targets.Wave(owner.progress.feedback.q, started)
            owner.engage(wave.sample(started), started)
            cpu = time.process_time()
            deadline = started
            while time.monotonic_ns() - started < 20_000_000_000:
                begin = time.monotonic_ns()
                state = owner.tick(begin)
                target = wave.sample(time.monotonic_ns())
                sent = time.monotonic_ns()
                owner.follow(target, sent)
                stamps.append(sent)
                samples.append(
                    {
                        "sent_ns": sent,
                        "q": target.q,
                        "feedback": dataclasses.asdict(state),
                    }
                )
                costs.append((time.monotonic_ns() - begin) / 1e6)
                deadline = next_deadline(
                    deadline, time.monotonic_ns(), round(1e9 / hz)
                )
                time.sleep(max(0, (deadline - time.monotonic_ns()) / 1e9))
            elapsed = (time.monotonic_ns() - started) / 1e9
            report["cpu_cores"] = (time.process_time() - cpu) / elapsed
            stop = time.monotonic()
            owner.halt(time.monotonic_ns())
            wait_hold(owner)
            report["stop_seconds"] = time.monotonic() - stop
            anchor = owner.progress.feedback.q
            drift = 0.0
            until = time.monotonic() + 3
            while time.monotonic() < until:
                state = owner.tick(time.monotonic_ns())
                drift = max(
                    drift, max(abs(a - b) for a, b in zip(state.q, anchor))
                )
                time.sleep(0.01)
            report.update(state="completed", hold_drift_rad=drift)
        finally:
            owner.close()
            report.update(
                commands=len(stamps),
                actual_command_hz=(
                    (len(stamps) - 1) * 1e9 / (stamps[-1] - stamps[0])
                    if len(stamps) > 1
                    else None
                ),
                gap_ms=distribution(
                    [(b - a) / 1e6 for a, b in zip(stamps, stamps[1:])]
                ),
                cycle_work_ms=distribution(costs),
                maxrss_native=resource.getrusage(
                    resource.RUSAGE_SELF
                ).ru_maxrss,
            )
            (root / f"rate-{hz}.json").write_text(
                json.dumps({"report": report, "samples": samples}, indent=2)
                + "\n"
            )
            print(json.dumps(report), flush=True)
    return report


if __name__ == "__main__":
    output = pathlib.Path("/results") / f"rates-{time.time_ns()}"
    output.mkdir()
    with connection.open_station() as peer:
        for frequency in (60, 120):
            compare(peer, frequency, output)

"""Explicit camera-only batch collection with truthful software/lab reports."""

import dataclasses
import json
import math
import os
import pathlib
import resource
import sys
import time

from ur12e_collection import (
    matching,
    rig,
    session,
    snapshots,
    station,
    synthetic,
)


@dataclasses.dataclass(frozen=True)
class Options:
    """Bounded batch inputs; revision and backend are always explicit."""

    backend: str
    output: pathlib.Path
    revision: str
    task: str = "camera-shadow"
    episodes: int = 20
    seconds: float = 40.0
    station_path: pathlib.Path | None = None

    def __post_init__(self):
        if self.backend not in ("hardware", "synthetic"):
            raise ValueError("shadow requires an explicit backend")
        if not isinstance(self.episodes, int) or not 1 <= self.episodes <= 20:
            raise ValueError("episodes must be in [1, 20]")
        if not math.isfinite(self.seconds) or not 0 < self.seconds <= 40:
            raise ValueError("seconds must be in (0, 40]")
        if not self.revision or not self.task:
            raise ValueError("task and software revision are required")
        if (self.backend == "hardware") != (self.station_path is not None):
            raise ValueError("only hardware shadow requires a station file")


def _write_report(path: pathlib.Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _collect(
    source: rig.Rig, owner: session.Session, options: Options, report: dict
) -> None:
    while len(report["episodes"]) < options.episodes:
        frames = source.read()
        now = time.monotonic_ns()
        completed = owner.poll()
        if completed is not None:
            report["episodes"].append(completed)
            print(
                f"Completed {len(report['episodes'])}/{options.episodes}: "
                f"{completed['episode']}",
                file=sys.stderr,
                flush=True,
            )
            report["cameras"] = source.statistics()
            _write_report(options.output / "report.json", report)
            if len(report["episodes"]) == options.episodes:
                return
        if owner.state == "idle":
            path = options.output / f"episode-{len(report['episodes']):04d}"
            owner.start(path, now)
        deadline = owner.boundaries["start_receipt_ns"] + int(
            options.seconds * 1e9
        )
        for frame in frames:
            # Drain frames before the boundary; exclude later arrivals.
            if frame.color.time.received_monotonic_ns < deadline:
                owner.submit(frame, now)
        owner.advance(now)
        if owner.state == "recording" and now >= deadline:
            owner.stop(now)
        report["supervisor_peak_rss_bytes"] = resource.getrusage(
            resource.RUSAGE_SELF
        ).ru_maxrss * (1 if sys.platform == "darwin" else 1024)


def run(options: Options) -> dict:
    """Collect a new batch, preserving completed episodes on any later fault."""
    config = (
        synthetic.configuration()
        if options.backend == "synthetic"
        else station.load(options.station_path, cameras_ready=True)
    )
    options.output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "state": "running",
        "simulated": options.backend == "synthetic",
        "clock_accuracy": "not_validated",
        "motion": "not_started",
        "requested_episodes": options.episodes,
        "seconds_per_episode": options.seconds,
        "software_revision": options.revision,
        "episodes": [],
        "limits": {
            "camera_queue_capacity": rig.QUEUE_CAPACITY,
            "camera_stale_ns": rig.STALE_NS,
            "startup_s": 30,
            "warmup_s": 2,
            "clock_step_ns": 100_000_000,
            "clock_sanity_ns": 2_000_000_000,
        },
    }
    source = rig.Rig(config, options.backend)
    owner = None
    try:
        _write_report(options.output / "report.json", report)
        source.start()
        snapshot = snapshots.build(
            config,
            source.observations,
            {
                "task": options.task,
                "software_revision": options.revision,
                "clock_epoch": "unix",
                "clock_id": source.clock_id,
                "clock_basis": (
                    "synthetic"
                    if report["simulated"]
                    else "realsense_global_time"
                ),
                "clock_validated": False,
                "simulated": report["simulated"],
            },
        )
        owner = session.Session(
            snapshot, matching.MatchConfig(max_skew_ns=config["max_skew_ns"])
        )
        _collect(source, owner, options, report)
        report["state"] = "completed"
    except BaseException as error:
        if isinstance(error, matching.SourceFault):
            rejections = error.rejections
            report["source_fault"] = {
                "generation": error.generation,
                "rejections": [item.metadata() for item in rejections],
            }
        report.update(
            state=(
                "interrupted"
                if isinstance(error, KeyboardInterrupt)
                else "failed"
            ),
            error=str(error) or type(error).__name__,
        )
        raise
    finally:
        if owner is not None and owner.writer is not None:
            report["active_episode"] = {
                "episode": owner.writer.destination.name,
                "boundaries": dict(owner.boundaries),
                "matching": (
                    dict(owner.matcher.counters) if owner.matcher else {}
                ),
                "writer": owner.writer.health(),
            }
        already_failed = report["state"] in ("failed", "interrupted")
        cleanup_errors = []
        for closer in ([owner.close] if owner is not None else []) + [
            source.close
        ]:
            try:
                closer()
            except Exception as error:  # pylint: disable=broad-exception-caught
                cleanup_errors.append(str(error))
        if cleanup_errors:
            report.update(state="failed", cleanup_errors=cleanup_errors)
        report["cameras"] = source.statistics()
        _write_report(options.output / "report.json", report)
        if cleanup_errors and not already_failed:
            raise RuntimeError("; ".join(cleanup_errors))
    return report

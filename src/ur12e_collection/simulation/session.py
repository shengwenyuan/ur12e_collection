"""Explicit simulation composition; no physical station or leader fallback."""

import dataclasses
import json
import pathlib
import time

from ur12e_collection import recording, ros_observer, synthetic
from ur12e_collection.control.session import Session, Setup
from ur12e_collection.control import console
from ur12e_collection.simulation import connection
from ur12e_collection.simulation import profile, targets


@dataclasses.dataclass(frozen=True)
class Inputs:
    """Explicit simulator fixtures; never inferred from station settings."""

    leader_trace: object = None
    camera_input: object = None


def create(
    station,
    output: pathlib.Path,
    revision: str | None = None,
    *,
    observe=False,
    inputs: Inputs = Inputs(),
) -> Session:
    """Start persistent synthetic cameras before acquiring motion control."""
    permit = json.loads(
        pathlib.Path("/sim-permit.json").read_text(encoding="utf-8")
    )
    if revision is not None and revision != permit["source_revision"]:
        raise ValueError(
            "requested revision differs from frozen simulator source"
        )
    context = {
        "task": "ursim-teleoperation-validation",
        "software_revision": permit["source_revision"],
        "clock_epoch": "unix",
        "clock_basis": "synthetic",
        "clock_validated": False,
        "simulated": True,
        "control": {
            "backend": "ursim",
            "hande": "bypassed",
            "arm_id": profile.SERIAL,
            "leader_id": "simulation-wave",
            "command_id": "ur-rtde-servo",
            "owner_id": "session-owner",
            "monotonic_to_unix_ns": time.time_ns() - time.monotonic_ns(),
            "control_hz": 50,
            "max_control_gap_ns": profile.LIMITS.freshness_ns,
            "camera_queue_capacity": 8,
            "camera_transport": "shared_memory",
            "writer_queue_capacity": 16,
            "writer_feedback_capacity": 128,
            "encoding_workers": 3,
            "association": "independent_receipts_no_interpolation",
            "native_home": permit["home"],
            "simulator": {"image": profile.IMAGE, "version": profile.VERSION},
        },
    }
    leader_trace = inputs.leader_trace
    companion = None
    if leader_trace is not None:
        companion = leader_trace.companion()
        context["control"]["leader_id"] = "gello"
        context["control"]["leader_mapping"] = "episode_relative_conditioned_v1"
    config, source_factory = synthetic.configuration(), None
    if inputs.camera_input is not None:
        config, source_factory, provenance = inputs.camera_input
        context["control"]["inputs"] = provenance
        context["control"]["camera_transport"] = "pickle"
    recorder = recording.Recorder(
        config, context, source_factory=source_factory
    )
    observer = None
    try:
        snapshot = recorder.start()
        if observe:
            observer = ros_observer.Observer(snapshot)
            observer.start()
    except BaseException:
        recorder.close()
        if observer is not None:
            observer.close()
        raise
    return Session(
        station,
        recorder,
        Setup(
            profile.LIMITS,
            targets.Wave,
            snapshot,
            output,
            leader_trace.factory(profile.LIMITS) if leader_trace else None,
            companion,
        ),
        observer,
    )


def run(output: pathlib.Path, revision: str, stream, *, observe=False) -> dict:
    """Run the explicit simulator console and retain its report."""
    with console.keyboard(stream) as read_keys:
        output.mkdir(parents=True, exist_ok=False)
        report = {"state": "failed", "episodes": []}
        with connection.open_station() as station:
            owner = create(station, output, revision, observe=observe)
            try:
                report = console.drive(owner, read_keys)
            finally:
                owner.close()
                report["timings"] = owner.timings
                if owner.observer is not None:
                    report["observer"] = owner.observer.health()
                (output / "session.json").write_text(
                    json.dumps(report, indent=2), encoding="utf-8"
                )
        return report

"""Storage fault fixtures must target only the explicit disposable recorder."""

import errno
import threading
from unittest import mock

import pytest

from simulation import recording_faults


@pytest.mark.parametrize("kind", ["disk", "writer_backlog"])
def test_storage_failure_requires_the_explicit_trigger(kind, monkeypatch):
    original, source, pause = mock.Mock(), mock.Mock(), mock.Mock()
    monkeypatch.setattr(
        recording_faults.archive.ArchiveWriter, "group", original
    )
    monkeypatch.setattr(recording_faults.rig, "Rig", source)
    monkeypatch.setattr(recording_faults.time, "sleep", pause)
    trigger, abort = threading.Event(), threading.Event()
    config, context = {}, {"control": {"camera_queue_capacity": 8}}
    recording_faults.Factory(kind, trigger)(config, context, abort)
    source.assert_called_once_with(
        config, "synthetic", queue_capacity=8, stop=abort
    )
    write = recording_faults.archive.ArchiveWriter.group
    write("writer", "group")
    original.assert_called_once_with("writer", "group")
    pause.assert_not_called()
    trigger.set()
    if kind == "disk":
        with pytest.raises(OSError) as caught:
            write("writer", "group")
        assert caught.value.errno == errno.ENOSPC
        assert original.call_count == 1
    else:
        write("writer", "group")
        pause.assert_called_once_with(2)
        assert original.call_count == 2


def test_range_injection_waits_for_a_new_sample(monkeypatch):
    import dataclasses
    import pathlib
    from ur12e_collection.leader.episode import Sample

    monkeypatch.syspath_prepend(
        str(pathlib.Path(__file__).parent / "simulation")
    )
    import leader_faults

    old = Sample("test", 1, 10, 11, (2200,) * 7)
    fresh = dataclasses.replace(old, sequence=2, start_ns=20, end_ns=21)
    trace = object.__new__(leader_faults.FaultTrace)
    trace.fault, trace.frozen = "range", (old,)
    monkeypatch.setattr(leader_faults.Trace, "samples", lambda *_: (old,))
    assert trace.samples(12) == (old,)
    monkeypatch.setattr(leader_faults.Trace, "samples", lambda *_: (fresh,))
    injected = trace.samples(22)[-1]
    assert (
        injected.sequence == fresh.sequence
        and injected.start_ns == fresh.start_ns
    )
    assert injected.raw[:6] == (100_000,) * 6

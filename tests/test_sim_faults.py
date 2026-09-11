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

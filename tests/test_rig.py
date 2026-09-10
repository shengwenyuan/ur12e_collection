"""Bounded persistent source ownership without physical devices."""

import queue
import time
from unittest import mock

import pytest

from ur12e_collection import realsense_source, rig, synthetic


def test_global_time_requires_declared_domain_and_host_sanity(group_factory):
    images = group_factory().anchor.payload
    now = 1_700_000_000_000_000_000
    row = {
        "color_timestamp_ms": now / 1e6,
        "depth_timestamp_ms": now / 1e6 + 1,
        "color_domain": "timestamp_domain.global_time",
        "depth_domain": "timestamp_domain.global_time",
        "color_frame_number": 10,
        "depth_frame_number": 20,
        "received_monotonic_ns": 5000,
    }
    with mock.patch.object(realsense_source.time, "time_ns", return_value=now):
        frame = realsense_source.frame_from_sample(
            "wrist", "physical", "clock", (images.rgb, images.depth, row)
        )
        assert frame.depth_timestamp_ns - frame.timestamp_ns == 1_000_000
        assert not frame.color.simulated
        row["depth_domain"] = "timestamp_domain.hardware_clock"
        with pytest.raises(ValueError, match="global"):
            realsense_source.frame_from_sample(
                "wrist", "physical", "clock", (images.rgb, images.depth, row)
            )
        row["depth_domain"] = "timestamp_domain.global_time"
        row["color_timestamp_ms"] -= 3000
        with pytest.raises(ValueError, match="sanity"):
            realsense_source.frame_from_sample(
                "wrist", "physical", "clock", (images.rgb, images.depth, row)
            )


def test_camera_queue_overflow_reports_error_and_closes(group_factory):
    def source(*_args):
        yield {"source_id": "wrist"}
        yield group_factory().anchor

    frames, status, stop = mock.MagicMock(), mock.MagicMock(), mock.MagicMock()
    frames.put_nowait.side_effect = queue.Full
    with mock.patch.object(rig, "_synthetic_stream", source):
        rig._worker(
            {}, "wrist", "clock", (frames, status, stop, "synthetic", None)
        )
    assert status.send.call_args_list[0].args[0][0] == "ready"
    assert "overflow" in status.send.call_args_list[1].args[0][1]
    frames.cancel_join_thread.assert_called_once()
    status.close.assert_called_once()


@pytest.mark.parametrize("fault", ["exit", "stale", "clock"])
def test_supervisor_faults_are_explicit(fault):
    source = rig.Rig(synthetic.configuration(), "synthetic")
    camera = mock.MagicMock()
    camera.status.poll.return_value = False
    camera.process.is_alive.return_value = fault != "exit"
    camera.process.exitcode = 0
    camera.frames.get_nowait.side_effect = queue.Empty
    camera.observed = {"source_id": "wrist"}
    camera.last_receipt = time.monotonic_ns() - (
        3_000_000_000 if fault == "stale" else 0
    )
    source._cameras["wrist"] = camera
    if fault == "clock":
        source._epoch_offset += 200_000_000
    try:
        with pytest.raises((RuntimeError, TimeoutError)):
            source.read()
    finally:
        source.close()
    camera.status.close.assert_called_once()


def test_partial_startup_closes_unstarted_channels():
    source = rig.Rig(synthetic.configuration(), "synthetic")
    context = mock.MagicMock()
    parent, child = mock.MagicMock(), mock.MagicMock()
    context.Pipe.return_value = parent, child
    context.Process.return_value.start.side_effect = OSError("spawn failed")
    source._context = context
    with pytest.raises(OSError, match="spawn"):
        source.start()
    parent.close.assert_called_once()
    child.close.assert_called_once()
    context.Queue.return_value.close.assert_called_once()

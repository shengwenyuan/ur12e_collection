"""Exercise probe failure cleanup and sample fidelity without physical cameras."""

from unittest import mock

import numpy as np
import pytest

from ur12e_collection import cameras


def test_pipeline_cleanup_after_capture_failure(tmp_path):
    """A read timeout closes a started device and remains a reported failure."""
    sdk = mock.MagicMock()
    pipeline = sdk.pipeline.return_value
    pipeline.wait_for_frames.side_effect = RuntimeError("read timeout")
    report = cameras._capture(
        sdk, "fixture", 1, tmp_path
    )  # pylint: disable=protected-access
    assert report["state"] == "failed"
    assert "read timeout" in report["error"]
    pipeline.stop.assert_called_once()


def test_sample_png_preserves_uint16(tmp_path):
    """PNG encoding must preserve invalid zeros and the largest raw depth value."""
    rgb = np.zeros((4, 4, 3), dtype=np.uint8)
    depth = np.array([[0, 1, 200, 65535]] * 4, dtype=np.uint16)
    cameras._save_samples(
        tmp_path, "fixture", rgb, depth
    )  # pylint: disable=protected-access
    assert (tmp_path / "fixture-depth.png").is_file()


def test_capture_stop_failure_is_not_a_pass(tmp_path):
    """SDK cleanup errors cannot masquerade as a completed camera check."""
    sdk = mock.MagicMock()
    sdk.pipeline.return_value.stop.side_effect = RuntimeError("stop failed")
    with (
        mock.patch.object(cameras, "aligned_sample"),
        mock.patch.object(cameras, "_record", return_value=({}, None, None)),
    ):
        with mock.patch.object(cameras, "_save_samples"):
            report = cameras._capture(
                sdk, "fixture", 1, tmp_path
            )  # pylint: disable=protected-access
    assert report["state"] == "failed"
    assert report["cleanup_error"] == "stop failed"


@pytest.mark.parametrize("exited", [False, True])
def test_camera_worker_timeout_or_crash_is_bounded(tmp_path, exited):
    """Native stalls and abrupt exits fail and release supervisor resources."""
    with mock.patch.object(cameras.multiprocessing, "get_context") as context:
        parent, child = mock.MagicMock(), mock.MagicMock()
        context.return_value.Pipe.return_value = (parent, child)
        parent.poll.return_value = exited
        parent.recv.side_effect = EOFError
        process = context.return_value.Process.return_value
        process.is_alive.return_value = not exited
        report = cameras._isolated_capture("fixture", 1, tmp_path)
    assert report["state"] == "failed"
    assert ("exited" if exited else "timed out") in report["error"]
    parent.poll.assert_called_once_with(41)
    parent.close.assert_called_once()
    child.close.assert_called()
    if not exited:
        process.terminate.assert_called_once()
        process.kill.assert_called_once()
    assert all(
        call.kwargs["timeout"] <= 2 for call in process.join.call_args_list
    )


def test_capture_counts_real_depth_instead_of_rgbd_pairs(tmp_path):
    """A repeated SDK depth frame is not a new 30 Hz depth observation."""
    samples = [
        (object(), object(), {"color_frame_number": c, "depth_frame_number": d})
        for c, d in ((10, 20), (11, 20), (13, 23))
    ]
    with (
        mock.patch.object(cameras, "aligned_sample", side_effect=samples),
        mock.patch.object(
            cameras.time, "monotonic", side_effect=[0, 0.1, 0.2, 0.3, 1, 1]
        ),
    ):
        stats, _, _ = cameras._record(
            mock.MagicMock(), None, 1, tmp_path / "frames.jsonl"
        )
    assert stats["frames"] == 3
    assert stats["counter_gaps"] == 1
    assert stats["depth_counter_gaps"] == 2
    assert stats["depth_repeated_frames"] == 1
    assert stats["observed_unique_depth_fps"] == 2

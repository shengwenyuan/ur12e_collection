"""Read-only viewer policies and nominal geometry, without robot motion."""

import importlib
import importlib.util
import io
import json
import pathlib
import shutil
import subprocess
import sys
from unittest import mock

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]


@pytest.fixture
def viewer(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("sim_viewer")


def observation(stamp=1.0):
    return {"timestamp_s": stamp, "actual_q": [0.0] * 6}


def test_frozen_controller_is_not_refreshed_by_repeated_receipts(viewer):
    state = viewer.State()
    state.accept(observation(), 10)
    state.accept(observation(), 12)
    assert not state.snapshot(12)["fresh"]
    assert state.snapshot(12)["age_ms"] == 2000
    state.accept(observation(2), 12)
    assert state.snapshot(12)["fresh"]
    assert not state.snapshot(14)["fresh"]


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"timestamp_s": 1, "actual_q": [0] * 5},
        {"timestamp_s": float("nan"), "actual_q": [0] * 6},
        {"timestamp_s": 1, "actual_q": [float("inf")] * 6},
        {"timestamp_s": True, "actual_q": [0] * 6},
    ],
)
def test_malformed_state_rejected(viewer, value):
    with pytest.raises(ValueError):
        viewer.State().accept(value, 1)


def test_regression_and_mutated_cached_pose_rejected(viewer):
    state = viewer.State()
    state.accept(observation(2), 1)
    with pytest.raises(ValueError):
        state.accept(observation(1), 2)
    changed = observation(2)
    changed["actual_q"][0] = 1
    with pytest.raises(ValueError):
        state.accept(changed, 2)


def test_reader_loss_retains_last_pose_but_marks_unavailable(viewer):
    state = viewer.State()
    viewer.consume(io.StringIO(json.dumps(observation()) + "\n"), state)
    result = state.snapshot(100)
    assert not result["fresh"] and result["actual_q"] == [0] * 6
    assert "disconnected" in result["error"]
    viewer.consume(io.StringIO("x" * 16385), state)
    assert "oversized" in state.snapshot(100)["error"]


def test_launcher_has_no_control_mount_or_external_network(viewer, tmp_path):
    command = viewer.reader_command("image", tmp_path / "permit", "fixture")
    assert command[command.index("--network") + 1] == "ur12e-sim_control"
    assert "--read-only" in command and "--privileged" not in command
    assert not any("sim-lock" in token or "/dev/" in token for token in command)
    assert "--publish" not in command and "-p" not in command
    assert command[-2:] == ["-u", "/viewer-reader.py"]


def test_receive_only_client_never_initializes_or_acquires_motion(monkeypatch):
    receiver = mock.Mock()
    receiver.getTimestamp.return_value = 1.0
    receiver.getActualQ.return_value = [0.0] * 6
    sdk = mock.Mock(RTDEReceiveInterface=mock.Mock(return_value=receiver))
    monkeypatch.setitem(sys.modules, "rtde_receive", sdk)
    spec = importlib.util.spec_from_file_location(
        "viewer_reader", ROOT / "scripts/sim_viewer/reader.py"
    )
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    monkeypatch.setattr(
        reader.connection, "verify_boundary", lambda: "isolated-peer"
    )
    forbidden = mock.Mock(side_effect=AssertionError("motion API used"))
    monkeypatch.setattr(reader.connection, "open_station", forbidden)
    monkeypatch.setattr(
        reader.ur,
        "dashboard",
        lambda _: {
            "state": "available",
            "responses": {
                "get serial number": reader.profile.SERIAL,
                "PolyscopeVersion": reader.profile.VERSION,
            },
        },
    )
    monkeypatch.setattr(
        reader.time, "sleep", mock.Mock(side_effect=KeyboardInterrupt)
    )
    with pytest.raises(KeyboardInterrupt):
        reader.run()
    sdk.RTDEReceiveInterface.assert_called_once_with(
        "isolated-peer", 30.0, ["timestamp", "actual_q"]
    )
    receiver.disconnect.assert_called_once()
    assert [call[0] for call in receiver.method_calls] == [
        "getTimestamp",
        "getActualQ",
        "getTimestamp",
        "disconnect",
    ]
    forbidden.assert_not_called()


def test_nominal_home_and_all_six_rotations():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is used only for the standalone viewer math check")
    script = """
      import {frames} from './scripts/sim_viewer/assets/kinematics.js';
      const q = [0,-Math.PI/2,-Math.PI/2,-Math.PI/2,Math.PI/2,0];
      console.log(JSON.stringify([frames(q).at(-1), ...q.map((_,i) => {
        const shifted = [...q]; shifted[i] += 0.1; return frames(shifted).at(-1);
      })]));
    """
    values = json.loads(
        subprocess.check_output(
            [node, "--input-type=module", "-e", script], cwd=ROOT, text=True
        )
    )
    home = values[0]
    assert [home[i] for i in (3, 7, 11)] == pytest.approx(
        [0.6914, -0.17415, 0.67685]
    )
    assert [home[i] for i in (2, 6, 10)] == pytest.approx([0, 0, -1])
    for shifted in values[1:]:
        assert max(abs(a - b) for a, b in zip(home, shifted)) > 0.05
    # Wrist3 rotates the flange even though its origin stays in place.
    assert [values[6][i] for i in (3, 7, 11)] == pytest.approx(
        [home[i] for i in (3, 7, 11)]
    )

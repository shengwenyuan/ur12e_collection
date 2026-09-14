"""Physical replay lifecycle exercised entirely with isolated device doubles."""

import dataclasses
import json
import types
from unittest import mock

import numpy as np
import pytest

from ur12e_collection import cli, contracts, station
from ur12e_collection.calibration import geometry, replay, rollout, routes
from ur12e_collection.control import model, owner
from ur12e_collection.followers import config as configuration
from ur12e_collection.simulation import profile
from test_aprilgrid_pipeline import route_document


class Device:
    def __init__(self, clock):
        self.clock = clock
        self.q = profile.HOME
        self.moves, self.stops = [], []
        self.closed = False
        self.control = mock.Mock()
        self.control.getTCPOffset.return_value = [0, 0, 0.127, 0, 0, 0]

    def read(self):
        return model.State(
            self.q,
            (0.0,) * 6,
            self.clock.now / 1e9,
            self.clock.now,
            currents=(0.0,) * 6,
            tcp=(0.3, 0.1, 0.5, 0.1, 0.2, 0.3),
        )

    def heartbeat(self):
        pass

    def enable_watchdog(self):
        pass

    def move(self, q, speed, acceleration):
        self.q = tuple(v + 0.00001 for v in q)
        self.moves.append((q, speed, acceleration))

    def stop(self, servo):
        self.stops.append(servo)

    def close(self):
        self.closed = True


def frame(state, role="wrist", exposure=None):
    receipt = state.received_ns + 1
    return rollout.Frame(
        role,
        contracts.Provenance(
            "camera-test",
            int(state.timestamp * 120),
            contracts.SampleTime(receipt, "test", receipt),
        ),
        receipt if exposure is None else exposure,
        b"png",
        {"sharpness": 30},
    )


def test_full_twenty_point_capture_uses_actual_pose_and_nonzero_offset():
    clock = types.SimpleNamespace(now=1_000_000_000)
    device = Device(clock)
    controller = owner.Controller(device, profile.LIMITS)
    route = routes.parse(route_document("wrist"), "wrist", profile.LIMITS)
    capture = rollout.Capture(controller, route, [0, 0, 0.127, 0, 0, 0])
    controller.tick(clock.now)
    capture.start(clock.now)
    for _ in range(6000):
        clock.now += 10_000_000
        capture.traversal.step(clock.now)
        capture.traversal.image(frame(controller.progress.feedback))
        if capture.traversal.state == "complete":
            break
    records = capture.document()
    assert len(records) == len(device.moves) == 20
    assert not device.stops
    assert all(
        m[1:] == (profile.LIMITS.ready_speed, profile.LIMITS.ready_acceleration)
        for m in device.moves
    )
    assert records[0]["actual"]["q"] != tuple(
        route.document["waypoints"][0]["q"]
    )
    expected = geometry.pose(device.read().tcp) @ geometry.inverse(
        geometry.pose([0, 0, 0.127, 0, 0, 0])
    )
    assert np.allclose(records[0]["T_base_flange"], expected)
    assert (
        records[0]["dwell"]["stop_receipt_ns"]
        - records[0]["dwell"]["start_receipt_ns"]
        == 2_000_000_000
    )


@pytest.mark.parametrize(
    "failure",
    ["pre_dwell", "missing_board", "start_mismatch", "stale_feedback"],
)
def test_replay_does_not_advance_on_invalid_capture(failure):
    clock = types.SimpleNamespace(now=1_000_000_000)
    device = Device(clock)
    controller = owner.Controller(device, profile.LIMITS)
    route = routes.parse(route_document("wrist"), "wrist", profile.LIMITS)
    capture = rollout.Capture(controller, route, [0] * 6)
    controller.tick(clock.now)
    if failure == "start_mismatch":
        controller.progress.feedback = dataclasses.replace(
            device.read(), q=(0.0,) * 6
        )
        with pytest.raises(model.ControlError, match="start"):
            capture.start(clock.now)
        assert not device.moves
        return
    capture.start(clock.now)
    with pytest.raises((ValueError, model.ControlError)):
        for _ in range(300):
            clock.now += 10_000_000
            capture.traversal.step(
                clock.now
                + (1_000_000_000 if failure == "stale_feedback" else 0)
            )
            if failure == "pre_dwell":
                assert not capture.traversal.image(
                    frame(device.read(), exposure=1)
                )
    assert len(device.moves) == 1 and device.stops
    assert capture.traversal.state == "failed"


@pytest.fixture
def environment(tmp_path, monkeypatch):
    from pathlib import Path

    config = configuration.load(
        Path(__file__).parents[1] / "config/teleop.ur.json"
    )
    document = route_document("wrist")
    document["robot_serial"] = config["follower"]["serial"]
    route_path = tmp_path / "poses.json"
    route_path.write_text(json.dumps(document))
    station_doc = station.example()
    station_doc["cameras"]["wrist"]["serial"] = "camera-test"
    station_path = tmp_path / "station.json"
    station_path.write_text(json.dumps(station_doc))
    args = types.SimpleNamespace(
        config=Path(__file__).parents[1] / "config/teleop.ur.json",
        station=station_path,
        poses=route_path,
        role="wrist",
        output=tmp_path / "run",
        operator_approved=True,
        validate_only=False,
    )
    clock = types.SimpleNamespace(now=1_000_000_000)

    def sleep(seconds):
        clock.now += max(1, round(seconds * 1e9))

    monkeypatch.setattr(
        replay,
        "time",
        types.SimpleNamespace(monotonic_ns=lambda: clock.now, sleep=sleep),
    )
    monkeypatch.setattr(replay, "sys", types.SimpleNamespace(platform="linux"))
    monkeypatch.setenv("UR12E_LEASE", str(tmp_path / "lease"))
    device = Device(clock)
    factory = mock.Mock(return_value=device)
    monkeypatch.setattr(replay.hardware, "open_transport", factory)

    class Source:
        def __init__(self, route):
            self.route = route

        def ready(self):
            return {
                "serial": "camera-test",
                "model": "D405",
                "profile": self.route.profile,
            }

        def poll(self):
            return frame(device.read())

        def close(self):
            assert device.closed or not factory.called

    monkeypatch.setattr(replay.camera, "Source", Source)
    monkeypatch.setattr(replay.trace, "Trace", lambda _: mock.Mock())
    return args, device, factory


@pytest.mark.parametrize("fault", [None, "interrupt", "camera", "offset"])
def test_entry_lifecycle_stops_before_camera_cleanup_and_preserves_partial(
    environment, monkeypatch, fault
):
    args, device, _ = environment
    if fault in ("interrupt", "camera"):

        def fail(_self):
            raise (
                KeyboardInterrupt
                if fault == "interrupt"
                else ValueError("camera failed")
            )

        monkeypatch.setattr(replay.camera.Source, "poll", fail)
    if fault == "offset":
        device.control.getTCPOffset.side_effect = [
            [0, 0, 0.127, 0, 0, 0],
            [0] * 6,
        ]
    if fault:
        with pytest.raises((ValueError, KeyboardInterrupt)):
            replay.run(args)
        assert not args.output.exists()
        partial = args.output.with_name("run.partial")
        assert (
            json.loads((partial / "run.json").read_text())["state"] == "partial"
        )
        assert device.stops
    else:
        result = replay.run(args)
        assert result["observations"] == 20
        document = json.loads((args.output / "run.json").read_text())
        assert document["state"] == "complete"
        assert len(list((args.output / "images").glob("*.png"))) == 20
    assert device.closed


@pytest.mark.parametrize("approved,validate", [(False, False), (False, True)])
def test_no_control_on_validation_or_missing_authorization(
    environment, approved, validate
):
    args, _, factory = environment
    args.operator_approved, args.validate_only = approved, validate
    if validate:
        assert replay.run(args)["motion_ready"] is False
    else:
        with pytest.raises(ValueError, match="operator-approved"):
            replay.run(args)
    factory.assert_not_called()


@pytest.mark.parametrize("camera", ["left", "right", "wrist"])
def test_three_cli_entries_parse_without_devices(camera):
    args = cli.parser().parse_args(["cali", f"--{camera}", "--validate-only"])
    assert args.role == (camera if camera == "wrist" else f"third_{camera}")


def test_calibration_runs_both_solvers_only_after_capture_closes(
    environment, monkeypatch
):
    from ur12e_collection.calibration import commands, pipeline

    args, device, _ = environment
    args.solve = args.verify = None

    def solve(run, destination):
        assert device.closed
        assert (run / "run.json").exists()
        assert destination.name == "run.result"
        return {"calibration_id": "test-result"}

    monkeypatch.setattr(pipeline, "solve", solve)
    assert commands.run(args) == 0


def test_camera_mailbox_is_bounded_and_faults_on_stalled_worker(monkeypatch):
    import queue
    from ur12e_collection.calibration import camera

    source = camera.Source.__new__(camera.Source)
    source.pending = queue.Queue(maxsize=2)
    source.process = mock.Mock()
    source.process.is_alive.return_value = True
    source.last_progress = 0
    monkeypatch.setattr(
        camera, "time", types.SimpleNamespace(monotonic=lambda: 1)
    )
    assert source.poll() is None
    source.pending.put(("tick", None))
    assert source.poll() is None and source.last_progress == 1
    monkeypatch.setattr(
        camera, "time", types.SimpleNamespace(monotonic=lambda: 5)
    )
    with pytest.raises(ValueError, match="stopped progressing"):
        source.poll()
    source.pending.put(("fault", "disconnected"))
    with pytest.raises(ValueError, match="disconnected"):
        source.poll()

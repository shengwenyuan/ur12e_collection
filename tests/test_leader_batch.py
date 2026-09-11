"""Exercise the whole guided sequence with a fake clock and no hardware."""

import io
import json
from types import SimpleNamespace
from unittest import mock

import pytest

from ur12e_collection.calibration import leader_batch as batch, leader_review
from ur12e_collection.leader import bus, episode, source


class Clock:
    def __init__(self):
        self.now = 1_000_000_000

    def sleep(self, _seconds):
        self.now += 20_000_000


class Reader:
    def __init__(self, clock, fault=None):
        self.clock = clock
        self.fault = fault
        self.inventory = {"1": {"torque": int(fault == "startup_torque")}}
        self.epoch = "fixture"
        self.traffic = {"0x82": 1}
        self.mailbox = self
        self.peak = 1
        self.closed = False
        self.sequence = 0

    def start(self):
        pass

    def close(self):
        self.closed = True

    def view(self):
        age = (self.clock.now - 1_000_000_000) / 1e9
        if self.fault == "interrupt" and age > 1:
            raise KeyboardInterrupt
        if self.fault == "disconnect" and age > 1:
            raise bus.ReadError("disconnected")
        torque = int(self.fault == "running_torque" and age > 1)
        health = bus.Block(
            self.clock.now - 1,
            self.clock.now,
            64,
            (bytes([torque, 0, 0, 0, 0, 0, 0]),) * 7,
            (0,) * 7,
        )
        return SimpleNamespace(health=health)

    def drain(self):
        if self.closed:
            return ()
        elapsed = (self.clock.now - 1_000_000_000) / 1e9
        phase = next(
            p for p in batch.phases() if p["start_s"] <= elapsed < p["end_s"]
        )
        raw = [2000] * 6 + [3200]
        if "hold_a" in phase["name"]:
            raw[phase["motor"] - 1] += 60
        elif "hold_b" in phase["name"]:
            raw[phase["motor"] - 1] -= 60
        elif "gripper_closed" in phase["name"]:
            raw[6] = 3700
        value = episode.Sample(
            self.epoch,
            self.sequence,
            self.clock.now - 1,
            self.clock.now,
            tuple(raw),
        )
        self.sequence += 1
        return (source.Motion(value, (0,) * 7),)


def capture(tmp_path, fault=None):
    clock = Clock()
    reader = Reader(clock, fault)
    with (
        mock.patch.object(batch.source, "Reader", return_value=reader),
        mock.patch.object(
            batch.time, "monotonic_ns", side_effect=lambda: clock.now
        ),
        mock.patch.object(batch.time, "sleep", side_effect=clock.sleep),
        mock.patch("socket.socket", side_effect=AssertionError("no network")),
    ):
        result = batch.capture(
            "fake", 3000000, tmp_path / "run", home_declared=True
        )
    return reader, result


def test_complete_sequence_and_offline_review_without_live_assessment(tmp_path):
    reader, result = capture(tmp_path)
    assert reader.closed and result["state"] == "completed"
    assert result["phases"][-1]["end_s"] == 150
    review = leader_review.analyze(tmp_path / "run")
    assert review["gripper"]["open"]["candidate_count"] == 3200
    assert review["gripper"]["closed"]["candidate_count"] == 3700
    assert review["gripper"]["state"] == "candidate"
    assert review["gripper"]["repeatability_verified"] is False
    assert (
        result["gripper_convention"] == "output_shaft_view_ccw_open_cw_closed"
    )
    assert all(j["opposite_excursions"] for j in review["joints"])
    assert all(j["return_error_counts"] == 0 for j in review["joints"])
    assert all(j["ur_sign"] is None for j in review["joints"])
    assert (
        review["operator_declared_home"]
        and not review["physical_home_verified"]
    )
    assert not review["motion_ready"]
    events = (tmp_path / "run/events.jsonl").read_text().splitlines()
    assert len(events) == len(batch.phases())
    path = tmp_path / "run/samples.jsonl"
    lines = path.read_text().splitlines()
    value = json.loads(lines[-1])
    value["epoch"] = "new"
    lines[-1] = json.dumps(value)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match="identity"):
        leader_review.analyze(tmp_path / "run")


@pytest.mark.parametrize(
    "fault", ["startup_torque", "running_torque", "disconnect", "interrupt"]
)
def test_faults_preserve_failure_and_close_without_correction(tmp_path, fault):
    reader, result = capture(tmp_path, fault)
    assert result["state"] == "failed" and reader.closed
    assert result["motion_ready"] is False
    assert (tmp_path / "run/report.json").exists()


def test_late_cue_never_catches_up_by_mislabeling_actions():
    guide = batch.Guide(batch.phases(), 1_000_000_000, io.StringIO())
    with pytest.raises(RuntimeError, match="delayed"):
        guide.tick(1_600_000_000)
    assert guide.index == 0


def test_uncertain_endpoint_or_missing_axis_is_not_a_calibration():
    holds = {
        f"gripper_{endpoint}_{i}": {
            "state": "measured",
            "center": [0] * 6 + [3200 + i * 8 + offset],
            "spread": [0] * 7,
        }
        for endpoint, offset in [("open", 0), ("closed", 500)]
        for i in range(3)
    }
    assert leader_review._gripper(holds)["state"] == "needs_review"
    assert leader_review.window([], 0, 2_000_000_000)["state"] == "insufficient"

"""Taught-route sequencing, stationary image association and failure gates."""

import dataclasses

import pytest

from ur12e_collection.calibration.traversal import Pose, Traversal
from ur12e_collection.control import model, owner
from ur12e_collection.simulation import profile
from ur12e_collection import synthetic


class Transport:
    def __init__(self):
        self.now = 1_000_000_000
        self.q = profile.HOME
        self.moves = []
        self.stops = []

    def read(self):
        return model.State(
            self.q,
            (0.0,) * 6,
            self.now / 1e9,
            self.now,
            currents=(0.0,) * 6,
            tcp=(0.0,) * 6,
        )

    def heartbeat(self):
        pass

    def move(self, q, speed, acceleration):
        self.moves.append((q, speed, acceleration))
        self.q = q

    def stop(self, servo):
        self.stops.append(servo)


def make(capture):
    transport = Transport()
    controller = owner.Controller(transport, profile.LIMITS)
    controller.tick(transport.now)
    poses = tuple(
        Pose(
            f"pose-{i}",
            (tuple(q + (i % 3) * 0.01 for q in profile.HOME),),
            ("wrist",),
            "validation" if i % 5 == 0 else "training",
        )
        for i in range(20)
    )
    traversal = Traversal(controller, poses, capture)
    traversal.start(transport.now)
    return transport, traversal


def test_twenty_taught_poses_each_capture_for_two_seconds():
    evidence = []
    transport, script = make(
        lambda pose, frame, state: evidence.append(
            (
                pose.pose_id,
                frame.color.time.received_monotonic_ns,
                state.received_ns,
            )
        )
        or True
    )
    for index in range(3000):
        transport.now += 20_000_000
        script.step(transport.now)
        if script.state == "complete":
            break
        if script.state == "capturing" and index % 2 == 0:
            frame = synthetic.frame(
                "wrist",
                index,
                "test",
                transport.now + 1,
                1_700_000_000_000_000_000 + transport.now,
            )
            script.image(frame)
    assert script.state == "complete" and len(script.results) == 20
    assert len(transport.moves) == 20
    assert all(
        r["stop_receipt_ns"] - r["start_receipt_ns"] == 2_000_000_000
        for r in script.results
    )
    assert all(previous < receipt for _, receipt, previous in evidence)
    assert not transport.stops


def test_missing_board_fails_without_advancing_to_next_pose():
    transport, script = make(lambda *_args: False)
    with pytest.raises(ValueError, match="missing valid"):
        for _ in range(200):
            transport.now += 20_000_000
            script.step(transport.now)
    assert script.state == "failed" and len(transport.moves) == 1
    assert transport.stops


def test_all_routes_are_checked_before_the_first_motion():
    transport = Transport()
    controller = owner.Controller(transport, profile.LIMITS)
    with pytest.raises(model.ControlError):
        Traversal(
            controller,
            (Pose("bad", ((9.0,) * 6,), ("wrist",), "training"),),
            lambda *_: True,
        )
    assert not transport.moves

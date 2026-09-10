"""ROS projections preserve units; optional telemetry cannot own the arm."""

import dataclasses
import json
import math
import time

import pytest

from ur12e_collection import observation, ros_observer
from ur12e_collection.control import model, records


def samples(controlled):
    factory = records.Records(controlled["control"], simulated=True)
    target = model.Target((0.1,) * 6, 0, 2_000_000, "simulation-wave")
    actual = model.State(
        (0.2,) * 6,
        (0.3,) * 6,
        1.0,
        3_000_000,
        currents=(1.2,) * 6,
        tcp=(0.1, 0.2, 0.3, 0, math.pi, 0),
    )
    return (
        factory.intent(target),
        factory.sent(target, 2_500_000),
        *factory.feedback(actual),
    )


def test_actual_intent_sent_units_and_raw_provenance(controlled):
    projected = [
        observation.project(row, controlled["control"])
        for row in samples(controlled)
    ]
    assert set(projected[0]) == {"records", "leader_joints"}
    assert set(projected[1]) == {"records", "sent_joints"}
    assert set(projected[2]) == {"records"}
    assert set(projected[3]) == {"records", "actual_joints", "tcp"}
    actual = projected[3]["actual_joints"]
    assert actual["position"] == [0.2] * 6
    assert actual["velocity"] == [0.3] * 6
    assert actual["effort"] == []
    assert actual["header"] == {
        "frame_id": "ur/ursim-123/base",
        "stamp": {"sec": 1_700_000_000, "nanosec": 3_000_000},
    }
    for row, value in zip(samples(controlled), projected):
        assert json.loads(value["records"]["data"]) == json.loads(
            json.dumps(dataclasses.asdict(row))
        )
    assert projected[3]["tcp"]["pose"]["orientation"] == pytest.approx(
        {"x": 0, "y": 1, "z": 0, "w": 0}
    )


@pytest.mark.parametrize(
    "rotation",
    [(0, 0, 0), (0.2, -0.8, 2.4), (1e-15, 0, 0), (0, 0, 2 * math.pi)],
)
def test_rotation_vector_unit_quaternion(rotation):
    value = observation.quaternion(rotation)
    assert sum(v * v for v in value.values()) == pytest.approx(1)
    assert value["w"] == pytest.approx(math.cos(math.hypot(*rotation) / 2))


def test_overflow_and_unstarted_observer_do_not_block(controlled):
    observer = ros_observer.Observer(controlled)
    try:
        assert observer.health()["state"] == "starting"
        observer.records(samples(controlled))
        assert observer.health()["dropped_records"] == 4
        observer.ready = True
        # No consumer: saturate the actual IPC queue, then test bounded loss.
        for _ in range(ros_observer.CAPACITY):
            observer.records(samples(controlled))
        started = time.monotonic()
        observer.records(samples(controlled))
        assert time.monotonic() - started < 0.05
        assert observer.health()["dropped_records"] == 8
    finally:
        observer.close()
    assert observer.health()["state"] == "closed"


def test_jazzy_roundtrip_late_context_and_observer_death(controlled):
    rclpy = pytest.importorskip("rclpy")
    qos = pytest.importorskip("rclpy.qos")
    sensor = pytest.importorskip("sensor_msgs.msg")
    geometry = pytest.importorskip("geometry_msgs.msg")
    std = pytest.importorskip("std_msgs.msg")
    observer = ros_observer.Observer(controlled)
    observer.start()
    observer.status("recording", "episode-0000")
    time.sleep(0.2)
    rclpy.init(args=[])
    node = rclpy.create_node(
        "observer_acceptance", start_parameter_services=False
    )
    seen = {}
    subscriptions = []
    try:
        for name, kind in {
            "actual_joints": sensor.JointState,
            "leader_joints": sensor.JointState,
            "sent_joints": sensor.JointState,
            "tcp": geometry.PoseStamped,
            "records": std.String,
            "context": std.String,
            "status": std.String,
        }.items():
            retained = name in ("context", "status")
            profile = qos.QoSProfile(
                depth=16,
                reliability=(
                    qos.ReliabilityPolicy.RELIABLE
                    if retained
                    else qos.ReliabilityPolicy.BEST_EFFORT
                ),
                durability=(
                    qos.DurabilityPolicy.TRANSIENT_LOCAL
                    if retained
                    else qos.DurabilityPolicy.VOLATILE
                ),
            )
            subscriptions.append(
                node.create_subscription(
                    kind,
                    ros_observer.NAMESPACE + "/" + name,
                    lambda msg, topic=name: seen.setdefault(topic, msg),
                    profile,
                )
            )
        deadline = time.monotonic() + 10
        while len(seen) != 7 and time.monotonic() < deadline:
            observer.records(samples(controlled))
            rclpy.spin_once(node, timeout_sec=0.05)
        assert set(seen) == {
            "actual_joints",
            "leader_joints",
            "sent_joints",
            "tcp",
            "records",
            "context",
            "status",
        }
        assert json.loads(seen["context"].data) == controlled
        assert json.loads(seen["status"].data)["phase"] == "recording"
        assert json.loads(seen["status"].data)["read_only"] is True
        assert list(seen["actual_joints"].position) == [0.2] * 6
        assert list(seen["actual_joints"].effort) == []
        assert seen["tcp"].pose.orientation.y == pytest.approx(1)
        assert seen["actual_joints"].header.stamp.nanosec == 3_000_000
        observer.process.kill()
        observer.process.join(2)
        started = time.monotonic()
        for _ in range(100):
            observer.records(samples(controlled))
        assert time.monotonic() - started < 0.1
        assert observer.health()["state"] == "failed"
        assert observer.health()["dropped_records"] >= 400
    finally:
        observer.close()
        node.destroy_node()
        rclpy.shutdown()

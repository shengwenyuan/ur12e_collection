"""Optional bounded ROS observation process; never an authority or recorder."""

import json
import multiprocessing
import queue
import time

from ur12e_collection import observation, workers

CAPACITY = 32
NAMESPACE = "/ur12e_collection"


def _publishers(node):
    # ROS is an optional live consumer; normal collection imports no rclpy.
    # pylint: disable=import-outside-toplevel,import-error
    from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
    from sensor_msgs.msg import JointState
    from geometry_msgs.msg import PoseStamped
    from std_msgs.msg import String

    transient = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.TRANSIENT_LOCAL,
    )
    stream = QoSProfile(depth=16, reliability=ReliabilityPolicy.BEST_EFFORT)
    types = {
        "actual_joints": JointState,
        "leader_joints": JointState,
        "sent_joints": JointState,
        "tcp": PoseStamped,
        "records": String,
        "status": String,
        "context": String,
    }
    return {
        name: (
            kind,
            node.create_publisher(
                kind,
                name,
                transient if name in ("status", "context") else stream,
            ),
        )
        for name, kind in types.items()
    }


def _emit(publishers, name, fields):
    # pylint: disable-next=import-outside-toplevel,import-error
    from rosidl_runtime_py.set_message import set_message_fields

    kind, publisher = publishers[name]
    message = kind()
    set_message_fields(message, fields)
    publisher.publish(message)


def _worker(snapshot, channels):
    workers.ignore_terminal_interrupt()
    messages, replies = channels
    node = None
    try:
        # pylint: disable=import-outside-toplevel,import-error
        import rclpy

        rclpy.init(args=[])
        node = rclpy.create_node(
            "observer",
            namespace=NAMESPACE,
            start_parameter_services=False,
            enable_rosout=False,
        )
        publishers = _publishers(node)

        _emit(
            publishers,
            "context",
            {"data": json.dumps(snapshot, allow_nan=False)},
        )
        replies.send(("ready", None))
        while True:
            try:
                operation, value = messages.get(timeout=0.05)
            except queue.Empty:
                rclpy.spin_once(node, timeout_sec=0)
                continue
            if operation == "stop":
                break
            if operation == "status":
                _emit(
                    publishers,
                    "status",
                    {
                        "data": json.dumps(
                            value
                            | {
                                "read_only": True,
                            }
                        )
                    },
                )
            else:
                for record in value:
                    for name, fields in observation.project(
                        record, snapshot["control"]
                    ).items():
                        _emit(publishers, name, fields)
            rclpy.spin_once(node, timeout_sec=0)
    except Exception as error:  # pylint: disable=broad-exception-caught
        replies.send(("error", str(error)))
    finally:
        if node is not None:
            node.destroy_node()
            rclpy.shutdown()
        replies.close()


class Observer:
    """Bounded observation cannot backpressure or reconnect robot control."""

    def __init__(self, snapshot: dict):
        context = multiprocessing.get_context("spawn")
        self.messages = context.Queue(CAPACITY)
        self.replies, child = context.Pipe(duplex=False)
        self.dropped = 0
        self.ready = False
        self.process = context.Process(
            target=_worker,
            args=(
                snapshot,
                (
                    self.messages,
                    child,
                ),
            ),
            name="ros-observer",
        )
        self.child = child
        self.error = None
        self.closed = False
        self.last_status = None
        self.status_ns = 0

    def start(self) -> None:
        """Fail optional setup before motion if Jazzy cannot initialize."""
        self.process.start()
        self.child.close()
        if not self.replies.poll(15):
            self.close()
            raise TimeoutError("ROS observer startup timed out")
        kind, value = self.replies.recv()
        if kind != "ready":
            self.close()
            raise RuntimeError(f"ROS observer initialization failed: {value}")
        self.ready = True

    def health(self) -> dict:
        """Expose observer loss without changing the collection outcome."""
        if not self.closed:
            while self.replies.poll():
                try:
                    kind, value = self.replies.recv()
                except EOFError:
                    break
                if kind == "error":
                    self.error = value
            if self.process.pid is not None and not self.process.is_alive():
                self.error = self.error or "observer process exited"
        return {
            "state": (
                "closed"
                if self.closed
                else (
                    "failed"
                    if self.error
                    else "online" if self.ready else "starting"
                )
            ),
            "error": self.error,
            "dropped_records": self.dropped,
        }

    def _send(self, operation, value):
        if not self.ready or self.closed or self.health()["error"]:
            return False
        try:
            self.messages.put_nowait((operation, value))
        except (queue.Full, OSError, ValueError):
            return False
        return True

    def records(self, values: tuple) -> None:
        """Count rejected telemetry; authoritative MCAP is separate."""
        if not self._send("records", values):
            self.dropped += len(values)

    def status(self, phase: str, episode: str | None) -> None:
        """Retry current phase after overflow and refresh at 2 Hz."""
        now = time.monotonic_ns()
        latest = phase, episode
        if latest == self.last_status and now - self.status_ns < 500_000_000:
            return
        if self._send(
            "status",
            {
                "phase": phase,
                "episode": episode,
                "receipt_monotonic_ns": now,
                "dropped_records": self.dropped,
            },
        ):
            self.last_status, self.status_ns = latest, now

    def close(self) -> None:
        """Bound cleanup without touching devices or raw archives."""
        if self.closed:
            return
        self.health()
        self._send("stop", None)
        if self.process.pid is not None:
            workers.stop(self.process)
        self.messages.cancel_join_thread()
        self.messages.close()
        self.replies.close()
        self.child.close()
        self.closed = True

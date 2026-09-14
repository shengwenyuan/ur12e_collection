"""Measured stationary evidence collected under the shared route controller."""

import dataclasses

from ur12e_collection.calibration import geometry, traversal
from ur12e_collection.control import model


@dataclasses.dataclass(frozen=True)
class Frame:
    """One encoded RGB view with SDK and host clocks, decoded by a worker."""

    role: str
    color: object
    exposure_ns: int
    png: bytes
    detection: dict


class Capture:
    """Keep one sharp view per stop; encode and write outside motion."""

    def __init__(self, controller, route, tcp_offset):
        self.route = route
        self.offset = geometry.pose(tcp_offset)
        self.traversal = traversal.Traversal(
            controller, route.poses, self.image
        )
        self.selected = {}

    def start(self, now_ns):
        """Require the declared measured start, without an implicit HOME."""
        state = self.traversal.controller.progress.feedback
        if (
            state is None
            or model.distance(state.q, self.route.start)
            > self.traversal.controller.limits.arrival
        ):
            raise model.ControlError(
                "calibration start differs from declared start_q"
            )
        self.traversal.start(now_ns)

    def image(self, pose, frame, state):
        """Derive flange from this image's actual TCP and the active offset."""
        if (
            frame.color.source_id != self.route.document["camera_serial"]
            or frame.color.simulated
        ):
            raise ValueError(
                "capture camera identity or physical provenance differs"
            )
        checkpoint = self.traversal.checkpoint
        receipt = frame.color.time.received_monotonic_ns
        if not checkpoint.start_ns <= frame.exposure_ns <= receipt:
            return False
        if receipt - frame.exposure_ns > 250_000_000:
            return False
        if state.tcp is None:
            raise ValueError("actual TCP pose is missing")
        previous = self.selected.get(pose.pose_id)
        if (
            previous
            and previous[0].detection["sharpness"]
            >= frame.detection["sharpness"]
        ):
            return True
        observation = {
            "pose_id": pose.pose_id,
            "split": pose.split,
            "actual": dataclasses.asdict(state),
            "T_base_flange": (
                geometry.pose(state.tcp) @ geometry.inverse(self.offset)
            ).tolist(),
            "color": dataclasses.asdict(frame.color),
            "exposure_monotonic_ns": frame.exposure_ns,
            "detection": frame.detection,
        }
        self.selected[pose.pose_id] = (frame, observation)
        return True

    def document(self):
        """Require completion; requested joints are never measurements."""
        if self.traversal.state != "complete":
            raise ValueError("calibration rollout is incomplete")
        observations = []
        for index, pose in enumerate(self.route.poses):
            _, record = self.selected[pose.pose_id]
            observations.append(
                record
                | {
                    "image": f"images/{index:03d}.png",
                    "dwell": self.traversal.results[index],
                }
            )
        return observations

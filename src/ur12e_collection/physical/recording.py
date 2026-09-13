"""Compose persistent output-only resources for physical recording."""

import dataclasses
import pathlib
import time

from ur12e_collection import feedback, recording, station


@dataclasses.dataclass(frozen=True)
class Options:
    """Explicit physical station, task and output root for recording."""

    station: pathlib.Path
    output: pathlib.Path
    task: str


class Resources:
    """Own cameras and independent read-only feedback for an entire session."""

    def __init__(self, config, options, revision):
        if not options.task.strip():
            raise ValueError("recording task must be explicit")
        value = station.load(options.station, cameras_ready=True)
        if (value["ur"]["host"], value["ur"]["serial"]) != (
            config["follower"]["host"],
            config["follower"]["serial"],
        ) or (value["hande"]["host"], value["hande"]["port"]) != (
            config["follower"]["host"],
            config["gripper"]["port"],
        ):
            raise ValueError("recording devices differ from controlled devices")
        value["gello"]["backend"] = "dynamixel_readonly"
        self.output = options.output / f"session-{time.time_ns()}"
        self.output.mkdir(parents=True, exist_ok=False)
        context = {
            "task": options.task,
            "software_revision": revision,
            "clock_epoch": "unix",
            "clock_basis": "realsense_global_time",
            "clock_validated": False,
            "simulated": False,
            "control": {
                "backend": "ur",
                "hande": "urcap",
                "arm_id": config["follower"]["serial"],
                "leader_id": "gello",
                "command_id": "ur-rtde-servo",
                "owner_id": "session-owner",
                "hande_id": (
                    f"hande@{value['hande']['host']}:{value['hande']['port']}"
                ),
                "monotonic_to_unix_ns": time.time_ns() - time.monotonic_ns(),
                "control_hz": 120,
                "feedback_hz": 125,
                "minimum_command_hz": 30,
                "max_control_gap_ns": config["limits"].freshness_ns,
                "association": "independent_receipts_no_interpolation",
                "leader_mapping": "episode_relative_conditioned_v1",
                "inputs": {
                    "follower": config["follower"],
                    "gripper": config["gripper"],
                    "limits": dataclasses.asdict(config["limits"]),
                    "guards": dataclasses.asdict(config["guards"]),
                    "leader_device": config["leader"]["device"],
                    "leader_baudrate": config["leader"]["baudrate"],
                    "home_open_gripper": config["home_open_gripper"],
                },
                "camera_queue_capacity": 8,
                "camera_transport": "shared_memory",
                "writer_queue_capacity": 4,
                "writer_feedback_capacity": 128,
                "encoding_workers": 3,
                "verification_workers": 3,
            },
        }
        self.recorder = recording.Recorder(value, context)
        self.readers = feedback.Feedback(value, "hardware")
        self.snapshot = None

    def start(self):
        """Initialize sensors before opening any robot control interface."""
        self.snapshot = self.recorder.start()
        return self.snapshot

    def close(self):
        """Release recording resources after the motion owner has stopped."""
        try:
            self.readers.close()
        finally:
            self.recorder.close()

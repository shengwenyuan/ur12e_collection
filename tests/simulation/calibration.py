"""Actual URSim taught routes and two-second image checkpoint acceptance."""

import dataclasses
import json
import math
import pathlib
import time

import cv2

from ur12e_collection import synthetic
from ur12e_collection.calibration.traversal import Pose, Traversal
from ur12e_collection.control.backends import open_backend
from ur12e_collection.control.owner import Controller
from ur12e_collection.simulation import profile


def main():
    root = pathlib.Path("/results") / f"calibration-{time.time_ns()}"
    root.mkdir()
    report = {
        "status": "FAIL",
        "image_source": "synthetic_no_board_geometry",
        "captures": [],
    }
    selected = set()

    def capture(pose, frame, state):
        key = pose.pose_id, frame.role
        if key not in selected:
            name = f"{pose.pose_id}-{frame.role}.png"
            ok, encoded = cv2.imencode(
                ".png", cv2.cvtColor(frame.payload.rgb, cv2.COLOR_RGB2BGR)
            )
            assert ok
            (root / name).write_bytes(encoded.tobytes())
            report["captures"].append(
                {
                    "pose_id": pose.pose_id,
                    "role": frame.role,
                    "image": name,
                    "frame": frame.metadata(),
                    "actual_state": dataclasses.asdict(state),
                }
            )
            selected.add(key)
        return True

    controller = None
    try:
        with open_backend("ursim") as transport:
            controller = Controller(transport, profile.LIMITS)
            controller.tick(time.monotonic_ns())
            controller.go_ready(time.monotonic_ns())
            while controller.state != "hold":
                controller.tick(time.monotonic_ns())
                time.sleep(0.02)
            poses = tuple(
                Pose(
                    f"pose-{i:02d}",
                    (
                        tuple(
                            home
                            + 0.12
                            * math.sin(i * 0.7 + joint)
                            * math.sin(i * 0.3)
                            for joint, home in enumerate(profile.HOME)
                        ),
                    ),
                    ("wrist",) if i < 10 else ("third_left", "third_right"),
                    "validation" if i % 5 == 0 else "training",
                )
                for i in range(20)
            )
            traversal = Traversal(controller, poses, capture)
            traversal.start(time.monotonic_ns())
            index = 0
            due = 0
            deadline = time.monotonic() + 180
            while traversal.state != "complete":
                if time.monotonic() > deadline:
                    raise TimeoutError("calibration traversal timed out")
                traversal.step(time.monotonic_ns())
                now = time.monotonic_ns()
                if now >= due:
                    for role in ("wrist", "third_left", "third_right"):
                        traversal.image(
                            synthetic.frame(
                                role,
                                index,
                                "calibration-fixture",
                                now,
                                time.time_ns(),
                            )
                        )
                    index += 1
                    due = now + 33_333_333
                time.sleep(0.01)
            report["checkpoints"] = traversal.results
            assert len(selected) == 30
            assert all(
                value["stop_receipt_ns"] - value["start_receipt_ns"]
                == 2_000_000_000
                for value in traversal.results
            )
            report["status"] = "PASS"
            controller.close()
    except BaseException as error:
        if controller is not None:
            controller.fail("calibration acceptance failed")
        report["error"] = repr(error)
        raise
    finally:
        (root / "report.json").write_text(json.dumps(report, indent=2))
        print(
            json.dumps(
                {
                    "report": str(root / "report.json"),
                    "status": report["status"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()

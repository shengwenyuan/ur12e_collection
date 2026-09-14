"""One isolated calibration RGB worker; never imported by the motion driver."""

import multiprocessing
import queue
import time

import cv2
import numpy as np

from ur12e_collection import cameras, contracts, realsense_source
from ur12e_collection.calibration import aprilgrid, rollout, routes


class Source:
    """Bounded camera process keeps detection/PNG work outside the watchdog."""

    def __init__(self, route):
        context = multiprocessing.get_context("spawn")
        self.pending = context.Queue(maxsize=2)
        self.stop = context.Event()
        self.process = context.Process(
            target=_worker,
            args=(route.document, self.pending, self.stop),
            name="calibration-camera",
            daemon=True,
        )
        self.last_progress = time.monotonic()
        self.process.start()

    def ready(self):
        """Require actual stream identity before a control connection exists."""
        try:
            kind, value = self.pending.get(timeout=20)
        except queue.Empty as error:
            raise ValueError("calibration camera startup timed out") from error
        if kind != "ready":
            raise ValueError(f"calibration camera startup failed: {value}")
        self.last_progress = time.monotonic()
        return value

    def poll(self):
        """Never wait for a camera or codec on the controller thread."""
        try:
            kind, value = self.pending.get_nowait()
        except queue.Empty:
            if time.monotonic() - self.last_progress > 3:
                raise ValueError(
                    "calibration camera stopped progressing"
                ) from None
            if not self.process.is_alive():
                raise ValueError("calibration camera worker exited") from None
            return None
        self.last_progress = time.monotonic()
        if kind == "fault":
            raise ValueError(f"calibration camera failed: {value}")
        return value

    def close(self):
        """Bound worker cleanup after the robot owner closes."""
        self.stop.set()
        self.process.join(3)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(2)
        self.pending.close()
        self.pending.cancel_join_thread()


def _offer(pending, kind, value):
    try:
        pending.put_nowait((kind, value))
    except queue.Full:
        pass  # Stale candidates are disposable; a missing view fails the dwell.


def _worker(document, pending, stop):
    try:
        cv2.setNumThreads(1)
        _stream(document, pending, stop)
    except Exception as error:  # pylint: disable=broad-exception-caught
        _offer(pending, "fault", str(error))
    finally:
        pending.cancel_join_thread()


def _stream(document, pending, stop):
    # SDK resources and frame provenance share one worker lifecycle.
    # pylint: disable=too-many-locals
    import pyrealsense2 as rs  # pylint: disable=import-outside-toplevel,import-error

    identity = {
        "serial": document["camera_serial"],
        "model": document["camera_model"],
    }
    device = realsense_source.device_for_camera(rs, identity)
    mode = document["profile"]
    settings = rs.config()
    settings.enable_device(identity["serial"])
    settings.enable_stream(
        rs.stream.color,
        mode["width"],
        mode["height"],
        rs.format.rgb8,
        mode["fps"],
    )
    pipeline = rs.pipeline()
    active = pipeline.start(settings)
    try:
        profile = active.get_stream(rs.stream.color).as_video_stream_profile()
        if (
            profile.width(),
            profile.height(),
            profile.fps(),
            profile.format(),
        ) != (mode["width"], mode["height"], 30, rs.format.rgb8):
            raise ValueError(
                "actual camera profile differs; no automatic fallback"
            )
        warmup = time.monotonic() + 3
        while time.monotonic() < warmup and not stop.is_set():
            pipeline.wait_for_frames(2000)
        pending.put(
            (
                "ready",
                {
                    "serial": identity["serial"],
                    "model": identity["model"],
                    "profile": mode,
                    "factory_intrinsics": cameras.color_intrinsics(profile),
                    "firmware": device.get_info(
                        rs.camera_info.firmware_version
                    ),
                    "usb": device.get_info(rs.camera_info.usb_type_descriptor),
                },
            ),
            timeout=2,
        )
        previous = -1
        while not stop.is_set():
            color = pipeline.wait_for_frames(2000).get_color_frame()
            receipt = time.monotonic_ns()
            wall = time.time_ns()
            source = round(color.get_timestamp() * 1_000_000)
            if (
                color.get_frame_timestamp_domain()
                != rs.timestamp_domain.global_time
            ):
                raise ValueError("calibration requires SDK global time")
            if source <= previous or not 0 <= wall - source <= 250_000_000:
                raise ValueError(
                    "camera exposure is stale, future or nonprogressing"
                )
            previous = source
            rgb = np.asanyarray(color.get_data())
            try:
                detection = aprilgrid.detect(
                    rgb, aprilgrid.Grid(**document["board"]), routes.DETECTION
                )
            except ValueError:
                _offer(pending, "tick", None)
                continue  # Require visibility at stops, not in transit.
            success, encoded = cv2.imencode(
                ".png", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            )
            if not success:
                raise ValueError("calibration PNG encoding failed")
            provenance = contracts.Provenance(
                identity["serial"],
                color.get_frame_number(),
                contracts.SampleTime(
                    source, "timestamp_domain.global_time", receipt
                ),
                False,
            )
            _offer(
                pending,
                "frame",
                rollout.Frame(
                    document["role"],
                    provenance,
                    receipt - (wall - source),
                    encoded.tobytes(),
                    detection,
                ),
            )
    finally:
        pipeline.stop()

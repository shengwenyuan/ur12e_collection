"""Explicit, bounded M07 camera diagnostics; never command robot joints."""

import concurrent.futures
import dataclasses
import json
import multiprocessing
import pathlib
import time
from typing import Any

from ur12e_collection import workers


@dataclasses.dataclass
class _FrameCounter:
    previous: int | None = None
    count: int = 0
    gaps: int = 0
    repeats: int = 0

    def observe(self, number: int, *, require_new: bool = False) -> None:
        """Count source frames, keeping repeated depth distinct from gaps."""
        if self.previous is not None:
            delta = number - self.previous
            if delta < 0 or (require_new and delta == 0):
                raise RuntimeError("invalid camera frame counter progression")
            self.gaps += max(0, delta - 1)
            self.repeats += delta == 0
        self.previous = number
        self.count += 1


def inventory(rs: Any) -> list[dict]:
    """Read model/serial/firmware/USB identity and supported target profiles."""
    result = []
    for device in rs.context().query_devices():
        details = {}
        for name in (
            "name",
            "serial_number",
            "firmware_version",
            "usb_type_descriptor",
        ):
            key = getattr(rs.camera_info, name)
            details[name] = (
                device.get_info(key) if device.supports(key) else None
            )
        profiles = set()
        for sensor in device.query_sensors():
            for profile in sensor.get_stream_profiles():
                if not profile.is_video_stream_profile():
                    continue
                video = profile.as_video_stream_profile()
                if (video.width(), video.height(), profile.fps()) == (
                    640,
                    480,
                    30,
                ):
                    profiles.add(
                        (str(profile.stream_type()), str(profile.format()))
                    )
        details["profiles_640x480_30"] = sorted(profiles)
        result.append(details)
    return result


def color_intrinsics(profile: Any) -> dict:
    """Read factory color intrinsics and distortion without recalibration."""
    values = profile.as_video_stream_profile().get_intrinsics()
    return {
        name: getattr(values, name)
        for name in ("width", "height", "fx", "fy", "ppx", "ppy", "coeffs")
    } | {"model": str(values.model)}


def aligned_sample(align: Any, frames: Any) -> tuple:
    """Copy aligned arrays while retaining original stream timestamps."""
    import numpy as np  # pylint: disable=import-outside-toplevel

    receipt = time.monotonic_ns()
    color, depth = frames.get_color_frame(), frames.get_depth_frame()
    if not color or not depth:
        raise RuntimeError("incomplete RGB-D frameset")
    aligned = align.process(frames)
    rgb = np.asanyarray(aligned.get_color_frame().get_data()).copy()
    z16 = np.asanyarray(aligned.get_depth_frame().get_data()).copy()
    if rgb.shape != (480, 640, 3) or z16.shape != (480, 640):
        raise RuntimeError("unexpected aligned image dimensions")
    if rgb.dtype != np.uint8 or z16.dtype != np.uint16:
        raise RuntimeError("unexpected aligned image types")
    return (
        rgb,
        z16,
        {
            "color_frame_number": color.get_frame_number(),
            "depth_frame_number": depth.get_frame_number(),
            "color_timestamp_ms": color.get_timestamp(),
            "depth_timestamp_ms": depth.get_timestamp(),
            "color_domain": str(color.get_frame_timestamp_domain()),
            "depth_domain": str(depth.get_frame_timestamp_domain()),
            "received_monotonic_ns": receipt,
        },
    )


def _record(
    pipeline: Any, align: Any, seconds: float, path: pathlib.Path
) -> tuple:
    start = time.monotonic()
    colors, depths = _FrameCounter(), _FrameCounter()
    rgb = depth = None
    with path.open("x", encoding="utf-8") as stream:
        while time.monotonic() - start < seconds:
            rgb, depth, entry = aligned_sample(
                align, pipeline.wait_for_frames(1000)
            )
            colors.observe(entry["color_frame_number"], require_new=True)
            depths.observe(entry["depth_frame_number"])
            stream.write(json.dumps(entry) + "\n")
    elapsed = time.monotonic() - start
    if rgb is None or depth is None:
        raise RuntimeError("no aligned frames received")
    return (
        {
            "frames": colors.count,
            "counter_gaps": colors.gaps,
            "depth_counter_gaps": depths.gaps,
            "depth_repeated_frames": depths.repeats,
            "elapsed_s": elapsed,
            "observed_fps": colors.count / elapsed,
            "observed_unique_depth_fps": (depths.count - depths.repeats)
            / elapsed,
        },
        rgb,
        depth,
    )


def _save_samples(
    output: pathlib.Path, serial: str, rgb: Any, depth: Any
) -> None:
    import cv2  # pylint: disable=import-outside-toplevel
    import numpy as np  # pylint: disable=import-outside-toplevel

    rgb_path = output / f"{serial}-rgb.png"
    depth_path = output / f"{serial}-depth.png"
    if not cv2.imwrite(str(rgb_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)):
        raise RuntimeError("RGB sample write failed")
    if not cv2.imwrite(
        str(depth_path), depth, [cv2.IMWRITE_PNG_COMPRESSION, 1]
    ):
        raise RuntimeError("depth sample write failed")
    decoded = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
    if not np.array_equal(depth, decoded):
        raise RuntimeError("depth sample failed lossless verification")


def _capture(
    rs: Any, serial: str, seconds: float, output: pathlib.Path
) -> dict:
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_device(serial)
    config.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
    config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    report = {"serial": serial, "frames": 0, "state": "failed"}
    started = False
    try:
        profile = pipeline.start(config)
        started = True
        report["depth_scale_m"] = (
            profile.get_device().first_depth_sensor().get_depth_scale()
        )
        report["color_intrinsics"] = color_intrinsics(
            profile.get_stream(rs.stream.color)
        )
        align = rs.align(rs.stream.color)
        for _ in range(15):
            aligned_sample(align, pipeline.wait_for_frames(2000))
        stats, rgb, depth = _record(
            pipeline, align, seconds, output / f"{serial}.jsonl"
        )
        report.update(stats)
        _save_samples(output, serial, rgb, depth)
        report.update(state="passed", depth_png_exact=True)
    except (RuntimeError, OSError, ValueError) as error:
        report["error"] = str(error)
    finally:
        if started:
            try:
                pipeline.stop()
            except RuntimeError as error:
                report.update(state="failed", cleanup_error=str(error))
    return report


def _capture_worker(
    serial: str, seconds: float, output: pathlib.Path, pipe: Any
) -> None:
    try:
        import pyrealsense2 as rs  # pylint: disable=import-outside-toplevel,import-error

        pipe.send(_capture(rs, serial, seconds, output))
    except (ImportError, RuntimeError, OSError, ValueError) as error:
        pipe.send({"serial": serial, "state": "failed", "error": str(error)})
    finally:
        pipe.close()


def _isolated_capture(
    serial: str, seconds: float, output: pathlib.Path
) -> dict:
    """Isolate native alignment and bound stalled camera workers."""
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_capture_worker,
        args=(serial, seconds, output, child),
        daemon=True,
    )
    failure = {"serial": serial, "frames": 0, "state": "failed"}
    started = False
    try:
        process.start()
        started = True
        child.close()
        # Includes SDK startup, 15 warm-up frames and final PNG verification.
        if parent.poll(seconds + 40):
            try:
                return parent.recv()
            except EOFError:
                return failure | {
                    "error": "camera worker exited without a report"
                }
        return failure | {"error": "camera worker timed out"}
    finally:
        if started:
            workers.stop(process)
        parent.close()
        child.close()


def probe(
    seconds: float, output: pathlib.Path | None, serials: list[str]
) -> dict:
    """Enumerate, or explicitly capture all selected physical cameras."""
    import pyrealsense2 as rs  # pylint: disable=import-outside-toplevel,import-error

    devices = inventory(rs)
    present = {device["serial_number"] for device in devices}
    if len(serials) != len(set(serials)) or set(serials) - present:
        raise ValueError("requested serials must be unique connected cameras")
    report = {
        "schema_version": 1,
        "devices": devices,
        "captures": [],
        "role_binding": "not_inferred",
        "worker_model": "spawned_process_per_camera",
    }
    if seconds == 0:
        return report
    if not 0 < seconds <= 60 or output is None:
        raise ValueError(
            "capture requires 0 < seconds <= 60 and an output directory"
        )
    selected = serials or sorted(present)
    if not selected:
        raise ValueError("no RealSense cameras connected")
    output.mkdir(parents=True, exist_ok=False)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(selected)
    ) as pool:
        futures = [
            pool.submit(_isolated_capture, serial, seconds, output)
            for serial in selected
        ]
        report["captures"] = [future.result() for future in futures]
    (output / "report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report

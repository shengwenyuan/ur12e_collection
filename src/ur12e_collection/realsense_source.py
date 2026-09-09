"""Persistent, camera-only SDK generator, isolated inside one worker process."""

import decimal
import time

from ur12e_collection import cameras, codecs, contracts, matching


def frame_from_sample(
    role: str, serial: str, clock_id: str, sample: tuple
) -> matching.Frame:
    """Require SDK global time; preserve its mapped values and raw domains."""
    rgb, depth, row = sample
    provenance = {}
    for kind in ("color", "depth"):
        if row[f"{kind}_domain"] != "timestamp_domain.global_time":
            raise ValueError("hardware shadow requires SDK global timestamps")
        timestamp = int(
            decimal.Decimal(str(row[f"{kind}_timestamp_ms"])) * 1_000_000
        )
        if abs(timestamp - time.time_ns()) > 2_000_000_000:
            raise ValueError(
                "camera global timestamp outside host sanity window"
            )
        provenance[kind] = contracts.Provenance(
            serial,
            row[f"{kind}_frame_number"],
            contracts.SampleTime(
                timestamp,
                row[f"{kind}_domain"],
                row["received_monotonic_ns"],
            ),
            False,
        )
    color, raw_depth = provenance["color"], provenance["depth"]
    return matching.Frame(
        role,
        0,
        clock_id,
        color.time.source_ns,
        color,
        raw_depth,
        raw_depth.time.source_ns,
        codecs.Images(rgb, depth),
    )


def _device(rs, camera):
    """Check observed identity/model and request SDK global time."""
    devices = {
        d.get_info(rs.camera_info.serial_number): d
        for d in rs.context().query_devices()
    }
    if camera["serial"] not in devices:
        raise ValueError("configured camera is absent")
    device = devices[camera["serial"]]
    name = device.get_info(rs.camera_info.name)
    model = next(
        (m for m in ("D435IF", "D435i", "D405") if m.lower() in name.lower()),
        None,
    )
    if model != camera["model"]:
        raise ValueError("configured camera model differs")
    for sensor in device.query_sensors():
        if sensor.supports(rs.option.global_time_enabled):
            sensor.set_option(rs.option.global_time_enabled, 1.0)
    return device


def stream(config: dict, role: str, clock_id: str, stop):
    """Yield observed readiness and frames until explicitly stopped."""
    import pyrealsense2 as rs  # pylint: disable=import-outside-toplevel,import-error

    serial = config["cameras"][role]["serial"]
    device = _device(rs, config["cameras"][role])
    settings = rs.config()
    settings.enable_device(serial)
    settings.enable_stream(rs.stream.color, 640, 480, rs.format.rgb8, 30)
    settings.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
    pipeline = rs.pipeline()
    profile = pipeline.start(settings)
    try:
        align = rs.align(rs.stream.color)
        warmup = time.monotonic() + 2
        while time.monotonic() < warmup and not stop.is_set():
            cameras.aligned_sample(align, pipeline.wait_for_frames(2000))
        # Test clock availability before advertising source readiness.
        sample = cameras.aligned_sample(align, pipeline.wait_for_frames(2000))
        frame_from_sample(role, serial, clock_id, sample)
        observed = {
            "source_id": serial,
            "model": config["cameras"][role]["model"],
            "depth_scale_m": profile.get_device()
            .first_depth_sensor()
            .get_depth_scale(),
            "color_intrinsics": cameras.color_intrinsics(
                profile.get_stream(rs.stream.color)
            ),
            "firmware": device.get_info(rs.camera_info.firmware_version),
            "usb": device.get_info(rs.camera_info.usb_type_descriptor),
        }
        yield observed
        while not stop.is_set():
            yield frame_from_sample(
                role,
                serial,
                clock_id,
                cameras.aligned_sample(align, pipeline.wait_for_frames(2000)),
            )
    finally:
        pipeline.stop()

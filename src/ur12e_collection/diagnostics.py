"""M01 diagnostics inspect dependencies and mounts without touching devices."""

import importlib
import pathlib
import platform
import tempfile
from importlib import metadata
from typing import Any

import ur12e_collection

DEPENDENCIES = {
    "jsonschema": "jsonschema",
    "rclpy": None,
    "numpy": "numpy",
    "av": "av",
    "mcap": "mcap",
    "mcap_ros2": "mcap-ros2-support",
    "cv2": "opencv-contrib-python-headless",
    "pyrealsense2": "pyrealsense2",
    "rtde_receive": "ur-rtde",
}


def dependency(module: str, distribution: str | None) -> dict[str, Any]:
    """Import a library, never instantiate a connection or camera context."""
    try:
        importlib.import_module(module)
        installed = metadata.version(distribution) if distribution else None
    except (ImportError, OSError, metadata.PackageNotFoundError) as error:
        return {"state": "unavailable", "reason": type(error).__name__}
    return {"state": "available", "version": installed}


def mount(path: pathlib.Path) -> dict[str, str]:
    """Probe write access with a temporary file; preserve existing data."""
    if not path.is_dir():
        return {"state": "unavailable", "reason": "directory_missing"}
    try:
        with tempfile.TemporaryFile(dir=path) as stream:
            stream.write(b"mount-check")
            stream.flush()
    except OSError as error:
        return {"state": "unavailable", "reason": type(error).__name__}
    return {"state": "available"}


def report(
    backend: str, config_dir: pathlib.Path, data_dir: pathlib.Path
) -> dict:
    """Report capabilities without asserting physical readiness."""
    return {
        "schema_version": 1,
        "version": ur12e_collection.version(),
        "backend": backend,
        "python": platform.python_version(),
        "platform": platform.machine(),
        "dependencies": {
            name: dependency(name, dist) for name, dist in DEPENDENCIES.items()
        },
        "mounts": {"config": mount(config_dir), "data": mount(data_dir)},
        "hardware": {"state": "not_checked", "motion_ready": False},
    }

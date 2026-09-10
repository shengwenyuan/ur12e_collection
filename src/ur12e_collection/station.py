"""M02 station schema and atomic persistence; no hardware connections."""

import contextlib
import fcntl
import json
import os
import pathlib
import tempfile
from importlib import resources
from typing import Any, Callable

import jsonschema

from ur12e_collection import contracts


def schema() -> dict[str, Any]:
    """Return the versioned schema distributed with the package."""
    resource = resources.files("ur12e_collection").joinpath(
        "schemas/station.json"
    )
    return json.loads(resource.read_text(encoding="utf-8"))


def validate(document: dict[str, Any], *, cameras_ready: bool = False) -> None:
    """Validate a draft, optionally requiring three unique camera identities."""
    json.dumps(document, allow_nan=False)
    jsonschema.Draft202012Validator(schema()).validate(document)
    if document.get("setup") is not None or document["calibration"] is not None:
        # Optional calibration code is loaded only for configured geometry.
        # pylint: disable-next=import-outside-toplevel
        from ur12e_collection.calibration import manifest

        try:
            manifest.active(document)
        except (KeyError, TypeError) as error:
            raise ValueError(
                f"invalid calibration configuration: {error}"
            ) from error
    cameras = document["cameras"]
    serials = [cameras[role]["serial"] for role in contracts.CAMERA_ROLES]
    present = [serial for serial in serials if serial is not None]
    if len(set(present)) != len(present):
        raise ValueError("camera serials must be unique across roles")
    if cameras_ready and len(present) != len(contracts.CAMERA_ROLES):
        raise ValueError("camera readiness requires all three serials")


def load(path: pathlib.Path, *, cameras_ready: bool = False) -> dict[str, Any]:
    """Load using exactly the same validation as writes and the CLI."""
    document = json.loads(path.read_text(encoding="utf-8"))
    validate(document, cameras_ready=cameras_ready)
    return document


def example() -> dict[str, Any]:
    """Return an incomplete station draft; it cannot authorize motion."""
    return {
        "schema_version": 1,
        "station_id": None,
        "ur": {"host": None, "serial": None, "ready_q_rad": None},
        "gello": {"backend": "unavailable", "ready_q_rad": None},
        "hande": {"transport": "server_client", "host": None, "port": None},
        "cameras": {
            role: {
                "model": "D405" if role == "wrist" else "D435i",
                "serial": None,
            }
            for role in contracts.CAMERA_ROLES
        },
        "camera_profile": {"width": 640, "height": 480, "fps": 30},
        "max_skew_ns": 16700000,
        "capture": {"wait_ns": 75000000, "empty_poll_ns": 1000000},
        "motion_accepted": False,
        "calibration": None,
    }


@contextlib.contextmanager
def _lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".lock").open(
        "a", encoding="utf-8"
    ) as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def update(path: pathlib.Path, change: Callable[[dict], dict]) -> dict:
    """Serialize configuration read, validation and replacement."""
    with _lock(path):
        document = change(load(path))
        _write(path, document, replace=True)
        return document


def write(
    path: pathlib.Path, document: dict[str, Any], *, replace: bool = False
) -> None:
    """Atomically store validated JSON; default creation never overwrites."""
    with _lock(path):
        _write(path, document, replace=replace)


def _write(path, document, *, replace):
    validate(document)
    payload = json.dumps(document, indent=2, allow_nan=False) + "\n"
    temporary = backup = None
    published = False
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = pathlib.Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if replace and path.exists():
            backup = temporary.with_name(temporary.name + ".previous")
            os.link(path, backup)
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
        published = True
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if published:
            if backup is not None:
                os.replace(backup, path)
            else:
                path.unlink()
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if backup is not None:
            backup.unlink(missing_ok=True)

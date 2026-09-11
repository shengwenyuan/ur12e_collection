"""Versioned episode context derived from station and observed camera facts."""

import functools
import json
from importlib import resources

import jsonschema
from referencing import Registry, Resource

from ur12e_collection import capture, contracts, station


@functools.lru_cache(maxsize=1)
def _validator() -> jsonschema.Draft202012Validator:
    definition = json.loads(
        resources.files("ur12e_collection")
        .joinpath("schemas/snapshot.json")
        .read_text(encoding="utf-8")
    )
    station_schema = station.schema()
    registry = Registry().with_resource(
        station_schema["$id"], Resource.from_contents(station_schema)
    )
    return jsonschema.Draft202012Validator(definition, registry=registry)


def copy(snapshot: dict) -> dict:
    """Validate and detach a snapshot from mutable configuration."""
    result = json.loads(json.dumps(snapshot, allow_nan=False))
    try:
        _validator().validate(result)
    except jsonschema.ValidationError as error:
        raise ValueError(f"invalid snapshot: {error.message}") from error
    if result["simulated"] != (result["clock_basis"] == "synthetic"):
        raise ValueError("snapshot clock basis differs from simulation flag")
    station.validate(result["station"], cameras_ready=True)
    for role in contracts.CAMERA_ROLES:
        expected = result["station"]["cameras"][role]
        observed = result["cameras"][role]
        if (observed["source_id"], observed["model"]) != (
            expected["serial"],
            expected["model"],
        ):
            raise ValueError(f"observed camera differs from station: {role}")
    leader_setup = result["station"]["gello"].get("setup")
    if (
        leader_setup is not None
        and leader_setup["simulated"] != result["simulated"]
    ):
        raise ValueError("leader setup provenance differs from episode")
    _calibration(result)
    if "capture" in result and result["capture"] != capture.resolve(
        result["station"]
    ):
        raise ValueError("snapshot capture differs from station")
    if "feedback" in result:
        devices = result["feedback"]["devices"]
        for device in devices.values():
            if (device["transport"] == "synthetic") != result["simulated"]:
                raise ValueError("feedback simulation differs from snapshot")
        if not result["simulated"]:
            config = result["station"]
            if devices["ur"]["source_id"] != config["ur"]["serial"]:
                raise ValueError("UR source differs from station")
            endpoint = (
                f"hande@{config['hande']['host']}:{config['hande']['port']}"
            )
            if devices["hande"]["source_id"] != endpoint:
                raise ValueError("Hand-E source differs from station")
    return result


def _calibration(result):
    """Bind active geometry to the declared setup and observed optics."""
    setup = result["station"].get("setup")
    if setup is not None and setup["simulated"] != result["simulated"]:
        raise ValueError("declared setup simulation differs from snapshot")
    for role, value in (result["calibration"] or {}).get("cameras", {}).items():
        if (
            value["context"]["intrinsics"]
            != result["cameras"][role]["color_intrinsics"]
        ):
            raise ValueError("calibration optics differ from observed camera")
    if result["calibration"] != result["station"]["calibration"]:
        raise ValueError("snapshot calibration differs from station")


def build(config: dict, observed: dict, context: dict) -> dict:
    """Merge explicit run context with station and SDK facts, then freeze."""
    return copy(
        context
        | {
            "schema_version": 1,
            "capture": capture.resolve(config),
            "station": config,
            "cameras": observed,
            "calibration": config["calibration"],
        }
    )

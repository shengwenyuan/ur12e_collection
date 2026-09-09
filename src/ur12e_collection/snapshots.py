"""Versioned episode context derived from station and observed camera facts."""

import functools
import json
from importlib import resources

import jsonschema
from referencing import Registry, Resource

from ur12e_collection import contracts, station


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
    if result["calibration"] != result["station"]["calibration"]:
        raise ValueError("snapshot calibration differs from station")
    return result


def build(config: dict, observed: dict, context: dict) -> dict:
    """Merge explicit run context with station and SDK facts, then freeze."""
    return copy(
        context
        | {
            "schema_version": 1,
            "station": config,
            "cameras": observed,
            "calibration": config["calibration"],
        }
    )

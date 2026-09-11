"""Versioned leader calibration bound to a declared assembly and evidence."""

import hashlib

from ur12e_collection import station
from ur12e_collection.leader import mapping


def declare(station_path, setup_id: str, *, simulated: bool):
    """An assembly change invalidates its calibration without motor access."""
    if (
        not isinstance(setup_id, str)
        or not setup_id.strip()
        or not isinstance(simulated, bool)
    ):
        raise ValueError("explicit assembly identity and provenance required")
    setup = {"id": setup_id, "simulated": simulated}

    def change(config):
        if config["gello"].get("setup") != setup:
            config["gello"].pop("calibration", None)
        config["gello"]["setup"] = setup
        return config

    return station.update(station_path, change)


def activate(calibration_path, evidence_path, station_path):
    """Bind verified evidence without attesting physical signs."""
    calibrated = mapping.load(calibration_path)
    if (
        hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        != calibrated.evidence_sha256
    ):
        raise ValueError("leader evidence hash differs")

    def change(config):
        setup = config["gello"].get("setup")
        if not setup:
            raise ValueError("declare the leader assembly before activation")
        config["gello"]["calibration"] = {
            "schema_version": 1,
            "setup_id": setup["id"],
            "simulated": setup["simulated"],
            "calibration_id": calibrated.identity(),
            "document": calibrated.document(),
            "physical_verified": False,
        }
        return config

    return station.update(station_path, change)

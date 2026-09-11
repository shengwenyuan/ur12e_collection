"""Assembly and HOME changes cannot silently retain incompatible calibration."""

import dataclasses
import hashlib

import pytest

from ur12e_collection import station
from ur12e_collection.calibration import leader_config
from test_leader_mapping import calibration


def test_activation_verifies_evidence_and_invalidates_assembly_changes(
    tmp_path,
):
    path = tmp_path / "station.json"
    config = station.example()
    config["ur"]["ready_q_rad"] = list(calibration().home_rad)
    station.write(path, config)
    source = tmp_path / "evidence.jsonl"
    source.write_text("test fixture\n")
    c = dataclasses.replace(
        calibration(),
        evidence_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
    )
    definition = tmp_path / "calibration.json"
    c.save(definition)
    with pytest.raises(ValueError, match="declare"):
        leader_config.activate(definition, source, path)
    leader_config.declare(path, "fixture-assembly", simulated=True)
    result = leader_config.activate(definition, source, path)
    frozen = path.read_bytes()
    assert result["gello"]["calibration"]["calibration_id"] == c.identity()
    assert result["gello"]["calibration"]["physical_verified"] is False
    source.write_text("changed")
    with pytest.raises(ValueError, match="hash"):
        leader_config.activate(definition, source, path)
    assert path.read_bytes() == frozen
    result = leader_config.declare(path, "remounted", simulated=True)
    assert "calibration" not in result["gello"]


def test_embedded_calibration_tampering_and_home_changes_are_rejected(tmp_path):
    path = tmp_path / "station.json"
    config = station.example()
    config["ur"]["ready_q_rad"] = list(calibration().home_rad)
    station.write(path, config)
    source = tmp_path / "evidence"
    source.write_bytes(b"fixture")
    c = dataclasses.replace(
        calibration(), evidence_sha256=hashlib.sha256(b"fixture").hexdigest()
    )
    definition = tmp_path / "calibration.json"
    c.save(definition)
    leader_config.declare(path, "fixture", simulated=True)
    result = leader_config.activate(definition, source, path)
    result["ur"]["ready_q_rad"][0] = 1.0
    with pytest.raises(ValueError, match="HOME"):
        station.write(path, result, replace=True)
    result = station.load(path)
    result["gello"]["calibration"]["document"]["joints"][0]["sign"] *= -1
    with pytest.raises(ValueError, match="identity"):
        station.write(path, result, replace=True)

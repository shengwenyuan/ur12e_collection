"""External calibration identity and offline MCAP persistence, no devices."""

import copy
import dataclasses
import json

import numpy as np
import pytest
import yaml

from ur12e_collection import snapshots, station, storage, synthetic
from ur12e_collection.calibration import external, manifest


@pytest.fixture
def inputs(tmp_path):
    report = {
        "mode": "eye_to_hand",
        "timestamp": "2026-10-02T20:11:03.905+00:00",
        "transform_meaning": "T_base_camera: camera pose in the robot base",
        "transform": np.eye(4).tolist(),
        "translation_m": [0.0, 0.0, 0.0],
        "observation_count": 30,
        "translation_residual_mm": {"max": 5.44},
    }
    source = tmp_path / "result.yaml"
    source.write_text(
        "# FINAL hand-eye calibration for camera_3 (serial 12345).\n"
        + yaml.safe_dump(report)
    )
    config = synthetic.configuration()
    config["ur"]["serial"] = "test-robot"
    config["cameras"]["third_left"]["serial"] = "12345"
    path = tmp_path / "station.json"
    station.write(path, config)
    return source, path


def test_serial_binding_preserves_roles_optics_and_records_external_status(
    inputs,
):
    source, path = inputs
    before = station.load(path)
    updated = external.activate(source, path, "12345")
    assert updated["cameras"] == before["cameras"]
    assert updated["camera_profile"] == before["camera_profile"]
    value = updated["calibration"]["cameras"]["third_left"]
    assert value["source"]["camera_name"] == "camera_3"
    assert value["source"]["yaml"] == source.read_text()
    assert value["validation"]["collector_validation"] == "not_run"
    assert value["source"]["report"]["translation_residual_mm"]["max"] == 5.44
    assert "intrinsics" not in value["context"]
    manifest.result(value)
    # Reimport is stable; updating a different camera preserves this result.
    assert external.activate(source, path, "12345") == updated
    second = path.with_name("second.yaml")
    document = station.load(path)
    document["cameras"]["third_right"]["serial"] = "67890"
    station.write(path, document, replace=True)
    second.write_text(source.read_text().replace("12345", "67890"))
    both = external.activate(second, path, "67890")
    assert both["calibration"]["cameras"]["third_left"] == value


@pytest.mark.parametrize("failure", ["serial", "matrix", "units", "mode"])
def test_invalid_import_is_atomic(inputs, failure):
    source, path = inputs
    before = path.read_bytes()
    text = source.read_text()
    report = yaml.safe_load(text)
    serial = "12345"
    if failure == "serial":
        serial = "99999"
    elif failure == "matrix":
        report["transform"][0][0] = 2
    elif failure == "units":
        report["translation_m"][0] = 1
    else:
        report["mode"] = "eye_in_hand"
    source.write_text(text.splitlines()[0] + "\n" + yaml.safe_dump(report))
    with pytest.raises(ValueError):
        external.activate(source, path, serial)
    assert path.read_bytes() == before


def test_changed_source_or_solution_and_false_acceptance_are_rejected(inputs):
    source, path = inputs
    result = external.activate(source, path, "12345")["calibration"]["cameras"][
        "third_left"
    ]
    for field in ("source", "solution", "validation"):
        changed = copy.deepcopy(result)
        if field == "source":
            changed[field]["yaml"] += "# changed\n"
        elif field == "solution":
            changed[field]["T_base_camera"][0][3] = 1
        else:
            changed[field]["collector_validation"] = "passed"
        changed["calibration_id"] = manifest.digest(
            {k: v for k, v in changed.items() if k != "calibration_id"}
        )
        with pytest.raises(ValueError):
            manifest.result(changed)


def test_external_snapshot_survives_metadata_and_mcap_roundtrip(
    inputs, tmp_path, snapshot, group_factory
):
    source, path = inputs
    config = external.activate(source, path, "12345")
    context = {
        k: snapshot[k]
        for k in (
            "task",
            "software_revision",
            "clock_epoch",
            "clock_id",
            "clock_basis",
            "clock_validated",
            "simulated",
        )
    }
    # Exercise physical-provenance serialization with generated pixels only.
    context.update(simulated=False, clock_basis="realsense_global_time")
    observed = synthetic.observations(config)
    observed["third_left"]["color_intrinsics"]["fx"] += 1
    frozen = snapshots.build(config, observed, context)
    original = copy.deepcopy(frozen)
    source.unlink()
    writer = storage.EpisodeWriter(
        tmp_path / "episode", frozen, simulated=False
    )
    group = group_factory()
    frames = tuple(
        dataclasses.replace(
            f,
            color=dataclasses.replace(
                f.color,
                source_id=config["cameras"][f.role]["serial"],
                simulated=False,
            ),
            depth=dataclasses.replace(
                f.depth,
                source_id=config["cameras"][f.role]["serial"],
                simulated=False,
            ),
        )
        for f in group.members
    )
    writer.submit(dataclasses.replace(group, anchor=frames[0], members=frames))
    report = writer.finish()
    assert report["snapshot"] == original
    metadata = json.loads((writer.destination / "metadata.json").read_text())
    assert metadata["snapshot"]["calibration"] == config["calibration"]
    assert (
        storage.verify_episode(writer.destination)["counts"]["metadata/episode"]
        == 1
    )

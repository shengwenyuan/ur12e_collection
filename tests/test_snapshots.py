"""The same versioned snapshot contract serves fixtures and real recording."""

import copy

import pytest

from ur12e_collection import snapshots, synthetic


def test_snapshot_builder_detaches_mutable_inputs(snapshot):
    config = synthetic.configuration()
    observed = synthetic.observations(config)
    context = {
        k: v
        for k, v in snapshot.items()
        if k not in ("station", "cameras", "calibration", "schema_version")
    }
    result = snapshots.build(config, observed, context)
    config["cameras"]["wrist"]["serial"] = "changed"
    observed["wrist"]["depth_scale_m"] = 9
    assert result == snapshot


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "identity",
        "model",
        "scale",
        "intrinsics",
        "extra",
        "simulation",
    ],
)
def test_invalid_snapshot_fails_before_recording(snapshot, change):
    value = copy.deepcopy(snapshot)
    if change == "version":
        value["schema_version"] = 2
    elif change == "identity":
        value["cameras"]["wrist"]["source_id"] = "another-device"
    elif change == "model":
        value["cameras"]["wrist"]["model"] = "D435i"
    elif change == "scale":
        value["cameras"]["wrist"]["depth_scale_m"] = 0
    elif change == "intrinsics":
        value["cameras"]["wrist"]["color_intrinsics"]["fx"] = float("nan")
    elif change == "extra":
        value["undeclared"] = True
    else:
        value["simulated"] = False
    with pytest.raises(ValueError):
        snapshots.copy(value)

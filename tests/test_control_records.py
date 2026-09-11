"""Controlled MCAP records reject false provenance and authority boundaries."""

import dataclasses

import pytest

from ur12e_collection import (
    archive,
    codecs,
    contracts,
    control_records,
    snapshots,
)
from ur12e_collection.control import model, records

OFFSET = 1_700_000_000_000_000_000


@pytest.mark.parametrize("hz", [50, 60, 120])
def test_snapshot_preserves_historical_and_selected_rates(controlled, hz):
    controlled["control"]["control_hz"] = hz
    assert snapshots.copy(controlled)["control"]["control_hz"] == hz
    controlled["control"]["feedback_hz"] = 125
    assert snapshots.copy(controlled)["control"]["feedback_hz"] == 125


def samples(snapshot):
    factory = records.Records(snapshot["control"], simulated=True)
    target = model.Target((0.0,) * 6, 0, 2_000_000, "simulation-wave")
    state = model.State(
        (0.1,) * 6,
        (0.2,) * 6,
        1.0,
        3_000_000,
        currents=(0.3,) * 6,
        tcp=(0.4,) * 6,
    )
    return [
        factory.authority("acquired", "space", 0),
        factory.intent(target),
        factory.sent(target, 2_500_000),
        *factory.feedback(state),
        factory.authority("released", "space", 40_000_000),
    ]


def write_archive(path, controlled, group):
    with path.open("wb") as stream:
        writer = archive.ArchiveWriter(stream, controlled, True, 20)
        try:
            writer.group(group)
            for sample in samples(controlled):
                writer.record(
                    sample,
                    sample.provenance.time.received_monotonic_ns + OFFSET,
                )
            writer.finish()
        finally:
            writer.close()


@pytest.mark.parametrize("workers", [1, 3])
@pytest.mark.parametrize("verification_workers", [1, 3])
def test_control_archive_decodes_and_preserves_actual(
    tmp_path, controlled, group_factory, workers, verification_workers
):
    controlled["control"]["encoding_workers"] = workers
    controlled["control"]["verification_workers"] = verification_workers
    path = tmp_path / "episode.mcap"
    write_archive(path, controlled, group_factory())
    result = archive.verify_mcap(path, controlled, True)
    assert result["counts"]["control/authority"] == 2
    assert result["counts"]["follower/state"] == 2
    assert result["all_depth_hashes_verified"]
    assert samples(controlled)[3].joint_positions_rad != (0.0,) * 6


@pytest.mark.parametrize("failure", ["pixels", "first_keyframe"])
def test_parallel_verification_rejects_corruption_and_reaps_jobs(
    tmp_path, controlled, group_factory, monkeypatch, failure
):
    import threading
    import time

    controlled["control"]["verification_workers"] = 3
    path = tmp_path / "episode.mcap"
    write_archive(path, controlled, group_factory())
    if failure == "pixels":
        original = codecs.decode_depth

        def changed(data):
            pixels = original(data)
            pixels[0, 0] ^= 1
            return pixels

        monkeypatch.setattr(codecs, "decode_depth", changed)
        message = "pixel digest"
    else:

        def missing_headers(_data):
            # The owner advances counts while this independent check is pending.
            time.sleep(0.01)
            return {1}

        monkeypatch.setattr(codecs, "nal_types", missing_headers)
        message = "keyframe"
    with pytest.raises(ValueError, match=message):
        archive.verify_mcap(path, controlled, True)
    assert not any(
        thread.name.startswith("image-verifier")
        for thread in threading.enumerate()
    )


@pytest.mark.parametrize("workers", [True, 0, 2, 4])
def test_verification_worker_budget_is_validated(controlled, workers):
    controlled["control"]["verification_workers"] = workers
    with pytest.raises(ValueError, match="snapshot"):
        snapshots.copy(controlled)


@pytest.mark.parametrize(
    "mutation",
    ["clock", "source", "command", "gripper", "release", "camera", "missing"],
)
def test_false_control_semantics_fail(controlled, group_factory, mutation):
    validator = control_records.Validator(controlled)
    data = samples(controlled)
    if mutation == "clock":
        item = data[1]
        data[1] = dataclasses.replace(
            item,
            provenance=dataclasses.replace(
                item.provenance,
                time=contracts.SampleTime(2_000_000, "wrong", 2_000_000),
            ),
        )
    elif mutation == "source":
        data[1] = dataclasses.replace(
            data[1],
            provenance=dataclasses.replace(
                data[1].provenance, source_id="gello"
            ),
        )
    elif mutation == "command":
        data[2] = dataclasses.replace(data[2], joint_positions_rad=(0.3,) * 6)
    elif mutation == "gripper":
        data[3] = dataclasses.replace(data[3], gripper_position_raw=0)
    elif mutation == "release":
        data.pop()
    elif mutation == "camera":
        validator.frames(group_factory(2))
    else:
        data.pop(4)
    with pytest.raises(ValueError):
        for item in data:
            validator.check(
                item, item.provenance.time.received_monotonic_ns + OFFSET
            )
        validator.finish()


def test_read_only_and_control_context_are_exclusive(controlled):
    controlled["feedback"] = {}
    with pytest.raises(ValueError, match="snapshot"):
        snapshots.copy(controlled)


def test_cached_feedback_is_not_another_sample(controlled):
    factory = records.Records(controlled["control"], simulated=True)
    state = model.State(
        (0.0,) * 6, (0.0,) * 6, 1.0, 1, currents=(0.0,) * 6, tcp=(0.0,) * 6
    )
    assert len(factory.feedback(state)) == 2
    assert factory.feedback(dataclasses.replace(state, received_ns=2)) == ()


@pytest.mark.parametrize("missing", ["last_ur_pair", "tail", "interior"])
def test_control_stream_cannot_end_with_missing_feedback(controlled, missing):
    data = samples(controlled)
    last = data.pop()
    if missing == "last_ur_pair":
        state = data[-2]
        data.append(
            dataclasses.replace(
                state,
                provenance=dataclasses.replace(
                    state.provenance,
                    sequence=1,
                    time=dataclasses.replace(
                        state.provenance.time,
                        source_ns=1_020_000_000,
                        received_monotonic_ns=23_000_000,
                    ),
                ),
            )
        )
    else:
        last = dataclasses.replace(
            last,
            provenance=dataclasses.replace(
                last.provenance,
                time=contracts.SampleTime(
                    1_000_000_000, "host_monotonic", 1_000_000_000
                ),
            ),
        )
        if missing == "interior":
            state = data[-2]
            data.append(
                dataclasses.replace(
                    state,
                    provenance=dataclasses.replace(
                        state.provenance,
                        sequence=1,
                        time=dataclasses.replace(
                            state.provenance.time,
                            source_ns=1_500_000_000,
                            received_monotonic_ns=503_000_000,
                        ),
                    ),
                )
            )
    data.append(last)
    validator = control_records.Validator(controlled)
    with pytest.raises(ValueError, match="required|cover|gap"):
        for item in data:
            validator.check(
                item, item.provenance.time.received_monotonic_ns + OFFSET
            )
        validator.finish()

"""Offline projection preserves measured state and rejects missing authority."""

import dataclasses
import json

import numpy as np
import pytest

from ur12e_collection import projection, storage
from ur12e_collection.control.session import write_outcome
from test_control_records import OFFSET, samples


@pytest.fixture
def episode(tmp_path, controlled, group_factory):
    path = tmp_path / "episode"
    writer = storage.EpisodeWriter(path, controlled, simulated=True)
    writer.submit(group_factory(1))
    for item in samples(controlled):
        writer.submit_records(
            ((item, item.provenance.time.received_monotonic_ns + OFFSET),)
        )
    writer.finish()
    write_outcome(path, "retained")
    return path


def test_projection_separates_actual_state_action_and_source_time(episode):
    source = projection.Episode(episode, "sent_command")
    rows = list(source.frames())
    assert len(rows) == 1
    row = rows[0]
    assert np.array_equal(row["action"], np.zeros(6, np.float32))
    assert np.array_equal(row["observation.state"], np.full(6, 0.1, np.float32))
    assert row["source.wrist_receipt_ns"][0] == 34_333_333
    assert row["source.camera_ns"][0] == OFFSET + 34_333_333
    assert row["observation.images.wrist"].shape == (480, 640, 3)
    source.unchanged()


@pytest.mark.parametrize("receipt", [1_000_000, 100_000_000])
def test_no_future_or_stale_control_association(controlled, receipt):
    timeline = projection.Timeline([dataclasses.asdict(samples(controlled)[2])])
    with pytest.raises(ValueError, match="preceding"):
        timeline.at(receipt)


def test_discard_and_changed_outcome_are_explicit(episode):
    source = projection.Episode(episode, "leader_intent")
    write_outcome(episode, "discarded")
    with pytest.raises(ValueError, match="changed"):
        source.unchanged()
    with pytest.raises(ValueError, match="discarded"):
        projection.Episode(episode, "sent_command")


def test_invalid_or_missing_action_source_rejected(episode):
    with pytest.raises(ValueError, match="action source"):
        projection.Episode(episode, "actual")
    metadata = json.loads((episode / "metadata.json").read_text())
    assert metadata["snapshot"]["control"]["hande"] == "bypassed"


def test_export_does_not_modify_existing_partial(
    episode, tmp_path, monkeypatch
):
    from ur12e_collection import lerobot_export

    monkeypatch.setattr(lerobot_export, "_dependencies", lambda: ())
    partial = tmp_path / "training.partial"
    partial.mkdir()
    (partial / "original").write_bytes(b"preserve")
    with pytest.raises(FileExistsError):
        lerobot_export.export(
            [episode], tmp_path / "training", "sent_command", rgb_arm_only=True
        )
    assert list(partial.iterdir()) == [partial / "original"]
    assert (partial / "original").read_bytes() == b"preserve"
    assert not (tmp_path / "training.lock").exists()


def test_export_failed_writer_never_publishes(episode, tmp_path, monkeypatch):
    from ur12e_collection import lerobot_export

    monkeypatch.setattr(lerobot_export, "_dependencies", lambda: ())

    def fail(_dependencies, partial, _episodes):
        partial.mkdir()
        (partial / "unfinished").write_bytes(b"interrupted encoder")
        raise OSError("encoder failure")

    monkeypatch.setattr(lerobot_export, "_write", fail)
    destination = tmp_path / "training"
    with pytest.raises(OSError, match="encoder failure"):
        lerobot_export.export(
            [episode], destination, "sent_command", rgb_arm_only=True
        )
    assert not destination.exists()
    assert (tmp_path / "training.partial/failure.json").exists()
    assert not (tmp_path / "training.lock").exists()

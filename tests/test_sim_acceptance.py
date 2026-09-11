"""Final simulation gates reject gaps, false successes and weak grouping."""

import copy
import json

import pytest

from simulation import acceptance


def entries():
    return [
        {
            "reason": "accepted",
            "anchor": {
                "color": {
                    "sequence": i,
                    "time": {
                        "received_monotonic_ns": 1_000_000 + i * 33_333_333
                    },
                }
            },
        }
        for i in range(1200)
    ]


def test_quality_includes_rejected_anchor_and_all_boundaries():
    items = entries()
    items[0]["reason"] = "missing_view"
    value = acceptance.decisions(items, 0, 40_000_000_000)
    assert value["accepted"] == 1199 and value["decisions"] == 1200


@pytest.mark.parametrize(
    "failure", ["gap", "repeat", "burst", "quality", "boundary"]
)
def test_bad_decision_stream_is_not_a_pass(failure):
    items = entries()
    if failure == "gap":
        items.pop(30)
    elif failure == "repeat":
        items[30] = copy.deepcopy(items[29])
    elif failure in ("burst", "quality"):
        for index in (
            range(30, 33) if failure == "burst" else range(0, 1200, 100)
        ):
            items[index]["reason"] = "missing_view"
    else:
        items = items[3:]
    with pytest.raises(ValueError):
        acceptance.decisions(items, 0, 40_000_000_000)


def test_error_bearing_report_never_counts_as_success(tmp_path):
    (tmp_path / "report.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "error": "final readback failed",
                "episodes": [],
            }
        )
    )
    with pytest.raises(ValueError, match="complete"):
        acceptance.audit(tmp_path, 0)


def test_host_receipt_jitter_is_reported_without_inventing_source_gaps():
    items = entries()
    items[30]["anchor"]["color"]["time"]["received_monotonic_ns"] += 60_000_000
    items[31]["anchor"]["color"]["time"]["received_monotonic_ns"] += 28_000_000
    result = acceptance.decisions(items, 0, 40_000_000_000)
    assert result["accepted"] == result["decisions"] == 1200
    assert result["max_receipt_gap_ms"] > 90


def replay_entries():
    """A recorded source omits two original identities on each replay cycle."""
    items = entries()
    source = {"sequence_stride": 6, "wrist_sequences": [1, 2, 4, 5]}
    for index, item in enumerate(items):
        cycle, position = divmod(index, 4)
        item["anchor"]["color"]["sequence"] = (
            cycle * 6 + source["wrist_sequences"][position]
        )
    return items, source


def test_known_recorded_gaps_are_not_new_replay_loss():
    items, source = replay_entries()
    result = acceptance.decisions(items, 0, 40_000_000_000, source)
    assert result["accepted"] == 1200
    with pytest.raises(ValueError, match="identities"):
        acceptance.decisions(items, 0, 40_000_000_000)


@pytest.mark.parametrize("failure", ["gap", "repeat", "rejection"])
def test_replay_provenance_cannot_hide_new_loss(failure):
    items, source = replay_entries()
    if failure == "gap":
        items.pop(30)
    elif failure == "repeat":
        items[30] = copy.deepcopy(items[29])
    else:
        for index in range(30, 33):
            items[index]["reason"] = "missing_view"
    with pytest.raises(ValueError):
        acceptance.decisions(items, 0, 40_000_000_000, source)

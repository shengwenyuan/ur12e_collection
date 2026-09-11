"""Completed files cannot hide a failed or discontinuous leader workload."""

import json

import pytest

from hardware import load_audit


def prepare(root, monkeypatch):
    (root / "cameras").mkdir()
    batch = {
        "state": "completed",
        "cameras": {},
        "episodes": [
            {
                "episode": f"episode-{i:04d}",
                "start_receipt_ns": 0,
                "stop_receipt_ns": 40_000_000_000,
            }
            for i in range(20)
        ],
    }
    (root / "cameras/report.json").write_text(json.dumps(batch))
    leader = {
        "state": "completed",
        "samples": 2,
        "traffic": {"0x2": 14, "0x8a": 2},
        "cpu_cores": 0.3,
    }
    (root / "leader-report.json").write_text(json.dumps(leader))
    rows = [
        {
            "sequence": i,
            "position": [0] * 7,
            "errors": [0] * 7,
            "epoch": "one",
            "start_ns": i * 8_333_333,
            "end_ns": i * 8_333_333 + 2_000_000,
        }
        for i in range(2)
    ]
    health = {"errors": [0] * 7, "torque": [0] * 7, "hardware_error": [0] * 7}
    monkeypatch.setattr(
        load_audit.storage, "verify_episode", lambda _path: {"verified": True}
    )
    monkeypatch.setattr(load_audit.mcap_read, "messages", lambda *_args: [])
    monkeypatch.setattr(
        load_audit,
        "decisions",
        lambda *_args: {"accepted": 1200, "decisions": 1200},
    )
    return rows, health


@pytest.mark.parametrize(
    "fault", ["none", "gap", "sequence", "epoch", "torque", "health"]
)
def test_independent_raw_checks_reject_hidden_leader_faults(
    tmp_path, monkeypatch, fault
):
    rows, health = prepare(tmp_path, monkeypatch)
    if fault == "gap":
        rows[1]["start_ns"] = 101_000_000
        rows[1]["end_ns"] = 103_000_000
    elif fault == "sequence":
        rows[1]["sequence"] = 2
    elif fault == "epoch":
        rows[1]["epoch"] = "restarted"
    elif fault == "torque":
        health["torque"][0] = 1
    elif fault == "health":
        health["errors"][0] = 1
    (tmp_path / "samples.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in rows)
    )
    (tmp_path / "health.jsonl").write_text(json.dumps(health) + "\n")
    if fault == "none":
        assert load_audit.audit(tmp_path)["state"] == "PASS"
    else:
        with pytest.raises(ValueError):
            load_audit.audit(tmp_path)

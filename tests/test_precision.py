"""Precision gain, pending motion and independently reconstructable evidence."""

import copy
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import shutil

import pytest

from ur12e_collection import archive, control_records, snapshots
from ur12e_collection.control import (
    conditioning,
    guards,
    model,
    precision,
    records,
)
from ur12e_collection.leader import audit, episode, input as leader_input
from ur12e_collection.followers import config
from test_leader_episode import HOME, calibration

START = 1_000_000_000
PERIOD = 8_333_333


def test_default_ur_profile_is_portable_and_enabled(tmp_path):
    root = Path(__file__).parents[1] / "config"
    shutil.copytree(root / "kinematics", tmp_path / "kinematics")
    path = tmp_path / "teleop.ur.json"
    shutil.copyfile(root / path.name, path)
    value = config.load(path)
    policy = value["precision"]
    assert policy.path == tmp_path / "kinematics/ur12e.urdf"
    observed = policy.observe(
        model.State(HOME, (0.0,) * 6, 1.0, START), START, 100_000_000
    )
    assert math.isfinite(observed["z_m"])
    assert 0.5 <= observed["gain"] <= 1.0
    document = json.loads(path.read_text())
    document["precision"]["sha256"] = "0" * 64
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="SHA256"):
        config.load(path)


@pytest.mark.parametrize("enabled", ["false", "true", 0, 1, None])
def test_precision_switch_requires_boolean(tmp_path, enabled):
    with pytest.raises(ValueError, match="Boolean"):
        precision.load({"enabled": enabled}, tmp_path)


def test_disabled_profile_matches_simple_mapping_without_geometry(tmp_path):
    document = json.loads(
        (Path(__file__).parents[1] / "config/teleop.ur.json").read_text()
    )
    document["precision"]["enabled"] = False
    # No asset exists at this relative path; disabled mode never opens it.
    path = tmp_path / "teleop.ur.json"
    path.write_text(json.dumps(document))
    value = config.load(path)
    assert value["precision"] is None
    del document["precision"]
    path.write_text(json.dumps(document))
    ordinary = config.load(path)
    source = Source()
    feedback = model.State(HOME, (0.0,) * 6, 1.0, START)
    inputs = [
        leader_input.Input(
            source,
            calibration(),
            item["limits"],
            feedback,
            START,
            precision=item.get("precision"),
        )
        for item in (value, ordinary)
    ]
    assert inputs[0].context() == inputs[1].context()
    assert "precision" not in inputs[0].context()
    for step in range(120):
        now = START + step * PERIOD
        if step:
            source.advance(step, 40 if step < 60 else -40, now)
        # No height-feedback dependency or precision-only evidence remains.
        assert inputs[0].sample(now) == inputs[1].sample(now)
        assert inputs[0].mapping_state is None


def profile():
    """Analytic six-joint fixture: z = 0.2 - 0.1 sin(q0)."""
    names = (
        "shoulder_pan",
        "shoulder_lift",
        "elbow",
        "wrist_1",
        "wrist_2",
        "wrist_3",
    )
    parts = ['<robot name="analytic">']
    for i, name in enumerate(names):
        parts.append(
            f'<joint name="{name}_joint" type="revolute">'
            f'<parent link="link{i}"/><child link="link{i+1}"/>'
            f'<origin xyz="0 0 {0.2 if i == 0 else 0}"/>'
            f'<axis xyz="{"0 1 0" if i == 0 else "1 0 0"}"/>'
            "</joint>"
        )
    parts.append(
        '<joint name="tip" type="fixed"><parent link="link6"/>'
        '<child link="flange"/><origin xyz="0.1 0 0"/>'
        "</joint></robot>"
    )
    urdf = "".join(parts)
    return precision.from_document(
        {
            "urdf": urdf,
            "sha256": hashlib.sha256(urdf.encode()).hexdigest(),
            "settings": {
                "reference_z_m": 0.154,
                "knots": [[0.035, 0.5], [0.05, 0.75], [0.07, 1.0]],
                "lead_seconds": 0.2,
                "correction_seconds": 0.2,
            },
        }
    )


class Source:
    origin = {"kind": "synthetic", "purpose": "precision regression"}

    def __init__(self):
        self.rows = tuple(
            episode.Sample(
                "precision-fixture",
                i,
                START - (2 - i) * 20_000_000,
                START - (2 - i) * 20_000_000,
                (2200,) * 6 + (3200,),
            )
            for i in range(3)
        )

    def samples(self, _now):
        return self.rows

    def advance(self, step, offset, now):
        self.rows = (
            episode.Sample(
                "precision-fixture",
                step + 2,
                now,
                now,
                (2200 + offset,) + (2200,) * 5 + (3200,),
            ),
        )


def active(settings=None):
    source = Source()
    policy = profile() if settings is None else settings
    limits = model.Limits(
        (-6.0,) * 6,
        (6.0,) * 6,
        HOME,
        speed=math.radians(24),
        acceleration=math.radians(30),
        ready_speed=0.1,
        ready_acceleration=0.1,
    )
    feedback = model.State(HOME, (0.0,) * 6, 1.0, START)
    leader = leader_input.Input(
        source, calibration(), limits, feedback, START, precision=policy
    )
    leader.sample(START)
    return source, leader


def feedback_at(z, now):
    q = (math.asin((0.2 - z) / 0.1), *HOME[1:])
    return model.State(q, (0.0,) * 6, now / 1e9, now)


@pytest.mark.parametrize(
    "z,gain",
    [
        (0.180, 0.5),
        (0.189, 0.5),
        (0.1965, 0.625),
        (0.204, 0.75),
        (0.214, 0.875),
        (0.224, 1.0),
        (0.260, 1.0),
    ],
)
def test_gain_knots_and_intermediate_values(z, gain):
    p = profile()
    observed = p.observe(feedback_at(z, START), START, 100_000_000)
    assert observed["z_m"] == pytest.approx(z, abs=1e-12)
    assert observed["gain"] == pytest.approx(gain, abs=1e-12)
    for edge in (0.189, 0.204, 0.224):
        assert (
            abs(p.settings.gain(edge + 1e-10) - p.settings.gain(edge - 1e-10))
            < 4e-9
        )


@pytest.mark.parametrize(
    "change",
    [
        {"correction_seconds": 0},
        {"lead_seconds": -1},
        {"reference_z_m": math.nan},
        {"knots": ((0.07, 0.5), (0.03, 1.0))},
        {"knots": ((0.03, 1.0), (0.07, 0.5))},
        {"knots": ((0.03, True), (0.07, 1.0))},
    ],
)
def test_invalid_precision_settings_rejected(change):
    with pytest.raises(ValueError):
        dataclasses.replace(profile().settings, **change)


def test_embedded_geometry_is_self_contained_and_hash_checked():
    p = profile()
    clone = precision.from_document(json.loads(json.dumps(p.document())))
    for q0 in (0, math.pi / 2, -0.3):
        q = (q0, *HOME[1:])
        assert clone.geometry.position(q)[2] == pytest.approx(
            0.2 - 0.1 * math.sin(q0)
        )
    invalid = p.document() | {"sha256": "0" * 64}
    with pytest.raises(ValueError, match="SHA256"):
        precision.from_document(invalid)


def test_gain_changes_do_not_move_an_idle_leader_or_repay_old_motion():
    source, leader = active()
    for i, z in enumerate((0.26, 0.214, 0.18, 0.214, 0.26), 1):
        now = START + i * PERIOD
        source.advance(i, 0, now)
        target = leader.sample(now, feedback_at(z, now))
        assert target.q == HOME
        assert leader.desired.q == HOME
        assert leader.reference == HOME


def run_trace(correction_seconds=0.2):
    p = profile()
    p.settings = dataclasses.replace(
        p.settings, correction_seconds=correction_seconds
    )
    source, leader = active(p)
    checker = audit.Audit(leader.context(), START)
    writer = records.Records(
        {"leader_id": "gello", "command_id": "fixture"}, simulated=True
    )
    targets, intents = [], []
    for i in range(1, 721):
        now = START + i * PERIOD
        # Build lag, hold the leader, reverse, hold, then cross upward.
        offset = 12 * min(i, 35) if i < 300 else max(0, 420 - 12 * (i - 300))
        source.advance(i, offset, now)
        z = 0.26 if i < 20 or i > 570 else 0.18
        target = leader.sample(now, feedback_at(z, now))
        intent = writer.intent(target, leader)
        checker.intent(intent)
        checker.sent(writer.sent(target, now))
        targets.append(target)
        intents.append(intent)
    return leader, targets, intents


def test_debt_contraction_limits_catchup_and_preserves_command_derivatives():
    leader, targets, intents = run_trace()
    _, uncorrected, _ = run_trace(1e12)
    # After the initial hand motion, fewer obsolete radians are executed.
    assert targets[290].q[0] < uncorrected[290].q[0] - 0.05
    assert (
        max(
            abs(i.mapping_state["accepted"][0] - i.joint_positions_rad[0])
            for i in intents
        )
        > 1e-4
    )
    prior = model.Target(HOME, 0, START)
    previous_v = (0.0,) * 6
    for target, intent in zip(targets, intents):
        dt = (target.created_ns - prior.created_ns) / 1e9
        v = tuple((a - b) / dt for a, b in zip(target.q, prior.q))
        a = max(abs(x - y) / dt for x, y in zip(v, previous_v))
        assert (
            a
            <= leader.limits.acceleration * intent.mapping_state["gain"] + 1e-8
        )
        assert max(map(abs, v)) <= leader.limits.speed + 1e-10
        prior, previous_v = target, v
    # No speed-limit restoration repays the earlier compressed forward travel.
    assert targets[-1].q[0] == pytest.approx(targets[569].q[0], abs=1e-5)


@pytest.mark.parametrize(
    "mutation",
    ["gain", "height", "accepted", "intent", "stale", "missing", "command"],
)
def test_independent_audit_rejects_forged_precision_evidence(mutation):
    source, leader = active()
    checker = audit.Audit(leader.context(), START)
    now = START + PERIOD
    source.advance(1, 5, now)
    target = leader.sample(now, feedback_at(0.20, now))
    writer = records.Records(
        {"leader_id": "gello", "command_id": "fixture"}, simulated=True
    )
    intent = copy.deepcopy(writer.intent(target, leader))
    if mutation == "gain":
        intent.mapping_state["gain"] += 0.1
    elif mutation == "height":
        intent.mapping_state["z_m"] += 0.01
    elif mutation == "accepted":
        intent.mapping_state["accepted"] = HOME
    elif mutation == "intent":
        intent = dataclasses.replace(intent, joint_positions_rad=HOME)
    elif mutation == "stale":
        intent.mapping_state["feedback"]["received_ns"] -= 200_000_000
    elif mutation == "missing":
        intent = dataclasses.replace(intent, mapping_state=None)
    if mutation == "command":
        checker.intent(intent)
        with pytest.raises(ValueError, match="conditioned command"):
            checker.sent(writer.sent(dataclasses.replace(target, q=HOME), now))
    else:
        with pytest.raises(ValueError):
            checker.intent(intent)


def test_stale_feedback_closes_input_without_reusing_last_gain():
    _, leader = active()
    with pytest.raises(model.ControlError, match="feedback"):
        leader.sample(START + PERIOD)
    with pytest.raises(model.ControlError, match="ended"):
        leader.sample(START + PERIOD, feedback_at(0.26, START + PERIOD))


def test_repeated_acquisition_is_consumed_once_despite_changed_height():
    source, leader = active()
    now = START + PERIOD
    source.advance(1, 4, now)
    leader.sample(now, feedback_at(0.18, now))
    reference = leader.reference
    for i in range(2, 5):
        now = START + i * PERIOD
        leader.sample(now, feedback_at(0.26, now))
        assert leader.reference == reference


def test_gain_drop_preserves_velocity_and_decays_to_the_new_speed_cap():
    _, leader = active()
    conditioner = conditioning.Conditioner(
        leader.limits, model.Target(HOME, 0, START)
    )
    conditioner.velocity = (0.3,) + (0.0,) * 5
    desired = (1.0,) + HOME[1:]
    acceleration = leader.limits.acceleration * 0.9 * 0.5
    for i in range(1, 101):
        previous = conditioner.velocity[0]
        conditioner.step(desired, START + i * PERIOD, gain=0.5)
        assert abs(conditioner.velocity[0] - previous) <= (
            acceleration * PERIOD / 1e9 + 1e-12
        )
        if i == 1:
            assert conditioner.velocity[0] > leader.limits.speed * 0.5
    assert conditioner.velocity[0] <= leader.limits.speed * 0.9 * 0.5 + 1e-12


@pytest.mark.parametrize("fault", ["raw_jump", "lag", "joint", "epoch"])
def test_precision_does_not_hide_existing_input_faults(fault):
    source, leader = active()
    leader.guards = guards.Policy(2.0, 0.01, 0.1, 0.5, 1.0)
    now = START + PERIOD
    source.advance(1, 100 if fault == "raw_jump" else 10, now)
    if fault == "lag":
        leader.guards = dataclasses.replace(leader.guards, intent_error=0.001)
    elif fault == "joint":
        leader.reference = leader.limits.upper
    elif fault == "epoch":
        source.rows = (dataclasses.replace(source.rows[0], epoch="reset"),)
    with pytest.raises(model.ControlError):
        leader.sample(now, feedback_at(0.18, now))
    assert leader.closed


def test_precision_audit_rejects_feedback_clock_change():
    source, leader = active()
    checker = audit.Audit(leader.context(), START)
    writer = records.Records(
        {"leader_id": "gello", "command_id": "fixture"}, simulated=True
    )
    for i in (1, 2):
        now = START + i * PERIOD
        source.advance(i, i, now)
        target = leader.sample(now, feedback_at(0.20, now))
        intent = copy.deepcopy(writer.intent(target, leader))
        if i == 1:
            checker.intent(intent)
            checker.sent(writer.sent(target, now))
        else:
            intent.mapping_state["feedback"][
                "source_clock"
            ] = "isaac_physics_simulation"
            with pytest.raises(ValueError, match="source changed"):
                checker.intent(intent)


def test_new_episode_resets_debt_and_schema_roundtrip():
    _, _, intents = run_trace()
    _, fresh = active()
    assert fresh.reference == HOME
    encoded = json.loads(json.dumps(dataclasses.asdict(intents[-1])))
    assert encoded["schema_version"] == 2
    decoded = archive._record_check(copy.deepcopy(encoded), True)
    assert decoded.mapping_state == encoded["mapping_state"]
    encoded["schema_version"] = 1
    with pytest.raises(ValueError, match="schema"):
        archive._record_check(encoded, True)


def test_snapshot_and_authority_require_identical_precision_contract(
    controlled,
):
    _, leader = active()
    control = controlled["control"]
    control.update(
        leader_id="gello",
        leader_mapping="height_relative_v1",
        inputs={"precision": leader.precision.document()},
    )
    snapshot = snapshots.copy(controlled)
    factory = records.Records(control, simulated=True)
    boundary = factory.authority("acquired", "space", START, leader.context())
    checker = control_records.Validator(snapshot)
    checker.check(boundary, START + control["monotonic_to_unix_ns"])
    snapshot["control"]["inputs"]["precision"]["settings"]["lead_seconds"] = 0.3
    checker = control_records.Validator(snapshot)
    with pytest.raises(ValueError, match="precision context"):
        checker.check(boundary, START + control["monotonic_to_unix_ns"])


def test_precision_episode_mcap_roundtrip(tmp_path, controlled, group_factory):
    source, leader = active()
    control = controlled["control"]
    control.update(
        leader_id="gello",
        leader_mapping="height_relative_v1",
        inputs={"precision": leader.precision.document()},
    )
    controlled = snapshots.copy(controlled)
    control = controlled["control"]
    writer = records.Records(control, simulated=True)
    path = tmp_path / "precision.mcap"
    offset = control["monotonic_to_unix_ns"]
    with path.open("wb") as stream:
        output = archive.ArchiveWriter(stream, controlled, True, 20)
        output.record(
            writer.authority("acquired", "space", START, leader.context()),
            START + offset,
        )
        output.group(group_factory(31))
        for i in range(1, 21):
            now = START + i * PERIOD
            source.advance(i, min(i, 10), now)
            measured = feedback_at(0.20, now)
            target = leader.sample(now, measured)
            for record in (
                writer.intent(target, leader),
                writer.sent(target, now),
                *writer.feedback(
                    dataclasses.replace(
                        measured, currents=(0.0,) * 6, tcp=(0.0,) * 6
                    )
                ),
            ):
                output.record(
                    record,
                    record.provenance.time.received_monotonic_ns + offset,
                )
        end = START + 21 * PERIOD
        output.record(writer.authority("released", "space", end), end + offset)
        output.finish()
    verified = archive.verify_mcap(path, controlled, True)
    assert verified["counts"]["leader/state"] == 20
    assert verified["counts"]["control/command"] == 20
    assert verified["all_depth_hashes_verified"]


@pytest.mark.parametrize("height", [0.18, 0.204, 0.224, 0.26])
@pytest.mark.parametrize("direction", [-1, 1])
def test_reversal_with_pending_motion_converges_without_repaying(
    height, direction
):
    source, leader = active()
    leader.guards = guards.Policy(math.pi, math.radians(30), 0.1, 0.5, 1)
    checker = audit.Audit(leader.context(), START)
    writer = records.Records(
        {"leader_id": "gello", "command_id": "fixture"}, simulated=True
    )
    reversal = None
    initial_velocity = None
    pending = None
    positions = []
    for i in range(1, 961):
        offset = 12 * i if i <= 30 else max(-120, 360 - 12 * (i - 30))
        now = START + i * PERIOD
        source.advance(i, direction * offset, now)
        # Restore full height only after the reverse request has settled.
        target = leader.sample(
            now, feedback_at(height if i < 720 else 0.26, now)
        )
        record = writer.intent(target, leader)
        checker.intent(record)
        checker.sent(writer.sent(target, now))
        if i == 30:
            pending = abs(leader.reference[0] - target.q[0])
            initial_velocity = abs(leader.conditioner.velocity[0])
        if (
            i > 30
            and reversal is None
            and direction * leader.conditioner.velocity[0] < -0.001
        ):
            reversal = (i - 30) * PERIOD / 1e9
        positions.append(target.q[0])
    assert pending > 0.05, "the test must reverse before catch-up completes"
    # Permit finite braking and reference contraction, not instant reversal.
    budget = initial_velocity / (0.9 * leader.limits.acceleration * 0.5) + 1
    assert reversal is not None and reversal <= budget
    assert max(positions[-120:]) - min(positions[-120:]) < 1e-8
    assert positions[-1] == pytest.approx(positions[719], abs=1e-5)
    assert max(map(abs, leader.conditioner.velocity)) < 1e-8


@pytest.mark.parametrize("z", [0.189, 0.204, 0.224])
def test_noisy_knot_crossings_and_irregular_cycles_preserve_command_bounds(z):
    source, leader = active()
    checker = audit.Audit(leader.context(), START)
    writer = records.Records(
        {"leader_id": "gello", "command_id": "fixture"}, simulated=True
    )
    now = START
    previous = leader.conditioner.target
    velocity = (0.0,) * 6
    for i in range(1, 601):
        period = (PERIOD, PERIOD * 2, 40_000_000)[i % 3]
        now += period
        source.advance(i, min(i, 120), now)
        target = leader.sample(now, feedback_at(z + 0.0005 * math.sin(i), now))
        dt = period / 1e9
        speeds = tuple((a - b) / dt for a, b in zip(target.q, previous.q))
        assert max(map(abs, speeds)) <= leader.limits.speed
        assert (
            max(abs(a - b) / dt for a, b in zip(speeds, velocity))
            <= leader.limits.acceleration
        )
        checker.intent(writer.intent(target, leader))
        checker.sent(writer.sent(target, now))
        previous, velocity = target, speeds
    assert max(map(abs, velocity)) < 1e-8


@pytest.mark.parametrize("offset_ns", [-100_000_001, 1])
def test_out_of_window_feedback_cannot_resume_a_closed_interval(offset_ns):
    source, leader = active()
    now = START + PERIOD
    source.advance(1, 1, now)
    with pytest.raises(model.ControlError, match="feedback"):
        leader.sample(now, feedback_at(0.20, now + offset_ns))
    assert leader.closed
    with pytest.raises(model.ControlError, match="ownership ended"):
        leader.sample(now + PERIOD, feedback_at(0.20, now + PERIOD))

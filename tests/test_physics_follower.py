"""Physical execution contracts without Isaac, hardware or a solver."""

import dataclasses
import json
import math
import time
from unittest import mock

import pytest

from ur12e_collection.control import model
from ur12e_collection.followers import config, local, physics, state


@pytest.fixture
def settings():
    return physics.Settings(
        240,
        (6000,) * 6,
        (600,) * 6,
        (330,) * 6,
        10000,
        100,
        130,
        0.6,
        0.5,
        0.0,
        0.0002,
        0.001,
    )


class Solver:
    """Prescribed measurements deliberately independent of drive requests."""

    def __init__(self):
        self.sample = physics.Sample(
            (0.0,) * 6, (0.1,) * 6, (0.021, 0.023), (0.002, -0.001), 0, 0, 1
        )
        self.targets = []
        self.paused = False

    def read(self):
        return self.sample

    def step(self, q, fingers):
        self.targets.append((q, fingers))
        if not self.paused:
            self.sample = dataclasses.replace(
                self.sample,
                time_s=self.sample.time_s + 1 / 240,
                sequence=self.sample.sequence + 1,
                acquired_ns=self.sample.acquired_ns + 4_166_667,
            )
        return self.sample


@pytest.fixture
def engine(settings):
    limits = model.Limits(lower=(-3.0,) * 6, upper=(3.0,) * 6, ready=(0.0,) * 6)
    return physics.Engine(limits, 0, Solver(), settings)


def test_contact_lag_and_asymmetric_jaws_are_actual_feedback(engine):
    engine.command("claim", {}, 0)
    engine.command("servo", {"q": (0.1,) * 6, "gripper_position": 255}, 0)
    engine.update(0.1)
    report = engine.snapshot(10)
    assert engine.driver.targets[-1][0] == (0.1,) * 6
    assert report["q"] == (0.0,) * 6
    assert report["qd"] == (0.1,) * 6
    assert report["finger_positions_m"] == (0.021, 0.023)
    assert report["gripper_aperture_m"] == pytest.approx(0.044)
    assert report["gripper_position"] == pytest.approx(30.6)
    assert not report["gripper_open"]
    assert report["time_s"] == 1 / 240
    assert engine.snapshot(11) == report


@pytest.mark.parametrize("operation", ["stop", "release", "expiry"])
def test_hold_preserves_residual_velocity_and_each_finger(engine, operation):
    engine.command("claim", {}, 0)
    engine.command("servo", {"q": (0.5,) * 6, "gripper_position": 255}, 0)
    if operation != "expiry":
        engine.command(operation, {}, 0.1)
    engine.update(0.6 if operation == "expiry" else 0.1)
    assert engine.driver.targets[-1] == ((0.0,) * 6, (0.021, 0.023))
    assert engine.qd == (0.1,) * 6
    assert bool(engine.fault) == (operation == "expiry")
    engine.update(0.7)
    assert engine.driver.targets[-1][1] == (0.021, 0.023)


def test_solver_pause_or_clock_reset_requires_restart(engine):
    engine.command("claim", {}, 0)
    engine.driver.paused = True
    with pytest.raises(model.ControlError, match="clock"):
        engine.update(0.1)
    sample = engine.sample
    with pytest.raises(model.ControlError):
        engine.command("claim", {}, 0.2)
    engine.update(0.3)
    assert engine.sample is sample
    assert len(engine.driver.targets) == 1


def test_home_starts_at_measured_position_and_remains_bounded(engine):
    engine.command("claim", {}, 0)
    engine.command("servo", {"q": (1.0,) * 6}, 0)
    engine.update(0.01)
    engine.command(
        "move", {"q": (0.5,) * 6, "speed": 0.3, "acceleration": 0.5}, 0.02
    )
    engine.update(0.03)
    assert 0 < engine.driver.targets[-1][0][0] < 0.001
    previous, speed = 0, 0
    for i in range(1, 801):
        now = 0.03 + i / 240
        engine.command("heartbeat", {}, now)
        engine.update(now)
        current = engine.driver.targets[-1][0][0]
        new_speed = (current - previous) * 240
        if i > 2:
            assert abs(new_speed) <= 0.3 + 1e-6
            assert abs(new_speed - speed) * 240 <= 0.5 + 1e-5
        previous, speed = current, new_speed


def test_open_readiness_checks_both_actual_fingers_and_velocities(engine):
    engine.sample = dataclasses.replace(
        engine.sample, fingers=(0.0249, 0.025), finger_velocities=(0, 0)
    )
    assert engine.snapshot(0)["gripper_open"]
    engine.sample = dataclasses.replace(engine.sample, fingers=(0.024, 0.026))
    assert not engine.snapshot(0)["gripper_open"]
    engine.sample = dataclasses.replace(
        engine.sample, fingers=(0.025, 0.025), finger_velocities=(0.005, 0)
    )
    assert not engine.snapshot(0)["gripper_open"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("solver_type", "unknown"),
        ("step_hz", True),
        ("step_hz", 60),
        ("arm_effort", [1] * 5),
        ("arm_stiffness", [math.nan] * 6),
        ("finger_damping", 0),
        ("open_tolerance_m", 0.01),
        ("restitution", math.nan),
        ("dynamic_friction", 1),
        ("finger_effort", True),
    ],
)
def test_invalid_physics_parameters_are_rejected(settings, field, value):
    with pytest.raises(ValueError):
        dataclasses.replace(settings, **{field: value})


def test_config_paths_relocate_and_kinematic_needs_no_physics(
    tmp_path, settings
):
    root = tmp_path / "scene"
    root.mkdir()
    (root / "scene.usda").touch()
    (root / "adapter.py").touch()
    value = {
        "schema_version": 1,
        "recording": False,
        "leader": {"calibration": "leader.json", "manual_support": True},
        "follower": {"backend": "isaac_physics", "endpoint": "p.sock"},
        "scene": {
            "root": "scene",
            "entrypoint": "scene.usda",
            "adapter": "adapter.py",
            "display_hz": 30,
        },
        "limits": {"lower": [-3] * 6, "upper": [3] * 6, "ready": [0] * 6},
        "gripper": {"closing_sign": 1, "aperture_speed_m_s": 0.05},
        "physics": dataclasses.asdict(settings),
    }
    path = tmp_path / "teleop.json"
    path.write_text(json.dumps(value))
    assert config.load(path)["scene"]["adapter"] == root / "adapter.py"
    value["follower"]["backend"] = "isaac_kinematic"
    del value["physics"]
    path.write_text(json.dumps(value))
    assert "physics" not in config.load(path)


def test_feedback_cache_cannot_refresh_acquisition_on_repeated_solver_sample():
    transport = local.Transport.__new__(local.Transport)
    transport.epoch, transport.backend = "test", "isaac_physics"
    transport.sample_sequence, transport.feedback = -1, None
    transport.socket = mock.Mock()
    transport.frames = mock.Mock()
    packet = {
        "version": local.VERSION,
        "source": "isaac_physics",
        "epoch": "test",
        "sequence": 1,
        "time_s": 0.1,
        "acquired_ns": time.monotonic_ns(),
        "q": [0] * 6,
        "qd": [0.1] * 6,
        "active": True,
        "fault": None,
        "gripper_position": 0,
        "gripper_open": True,
        "finger_positions_m": [0.025] * 2,
        "finger_velocities_m_s": [0] * 2,
    }
    transport.frames.receive.return_value = [local.encode(packet)]
    first = transport.read()
    assert transport.read() is first
    packet["fault"] = "paused"
    transport.frames.receive.return_value = [local.encode(packet)]
    with pytest.raises(model.ControlError, match="paused"):
        transport.read()
    packet["fault"], packet["source"] = None, "isaac_kinematic"
    transport.frames.receive.return_value = [local.encode(packet)]
    with pytest.raises(model.ControlError, match="source"):
        transport.read()


def test_physical_gripper_readiness_does_not_require_exact_zero():
    feedback = state.Feedback(
        (0,) * 6,
        (0,) * 6,
        1,
        1,
        True,
        "",
        gripper_position=0.2,
        gripper_open=True,
    )
    assert feedback.gripper_open


def test_slow_wall_cadence_does_not_accelerate_home_or_gripper(engine):
    engine.command("claim", {}, 0)
    engine.command(
        "move",
        {
            "q": (0.5,) * 6,
            "speed": 0.3,
            "acceleration": 0.5,
            "gripper_position": 255,
        },
        0,
    )
    before = engine.planner.gripper_position
    engine.command("heartbeat", {}, 0.4)
    engine.update(0.4)
    assert engine.planner.gripper_position - before <= 255 / 240 + 1e-9
    assert engine.driver.targets[-1][0][0] < 0.001
    assert engine.fault is None


def test_watchdog_uses_host_time_even_when_solver_runs_faster(engine):
    engine.command("claim", {}, 0)
    for _ in range(241):
        engine.update(0.1)
    assert engine.sample.time_s > 1
    assert engine.fault is None
    engine.update(0.6)
    assert engine.fault == "physical owner heartbeat expired"


@pytest.mark.parametrize("positions", [(), (0.02,), (float("nan"), 0.02)])
def test_missing_or_invalid_physical_jaw_readback_is_rejected(positions):
    with pytest.raises(model.ControlError, match="jaw"):
        state.Feedback(
            (0,) * 6,
            (0,) * 6,
            1,
            1,
            True,
            "",
            source_clock="isaac_physics_simulation",
            finger_positions_m=positions,
            finger_velocities_m_s=(0, 0),
        )


def test_render_time_does_not_starve_fixed_solver_steps(monkeypatch):
    from types import SimpleNamespace
    from ur12e_collection.followers import physical_application

    clock = [0.0]
    monkeypatch.setattr(
        physical_application.time, "monotonic", lambda: clock[0]
    )
    monkeypatch.setattr(
        physical_application.time,
        "sleep",
        lambda dt: clock.__setitem__(0, clock[0] + dt),
    )
    app = mock.Mock()
    app.is_running.side_effect = [True] * 40 + [False]
    driver = mock.Mock()
    driver.render.side_effect = lambda: clock.__setitem__(0, clock[0] + 0.1)
    service = mock.Mock()
    config_value = {
        "physics": SimpleNamespace(step_hz=240),
        "scene": {"display_hz": 30},
    }
    args = SimpleNamespace(duration=0, headless=False, report=None)
    physical_application.loop(app, driver, service, config_value, args)
    assert service.engine.update.call_count == 40
    assert 1 <= driver.render.call_count <= 5

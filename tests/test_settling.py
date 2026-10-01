"""Stop confirmation cannot be inferred from a low-speed crossing or cache."""

import dataclasses
import math

import pytest

from ur12e_collection.control import model, owner, settling
from ur12e_collection.simulation import profile


def sample(window, milliseconds, *, speed=0, source_ms=None):
    source = milliseconds if source_ms is None else source_ms
    return window.update(
        (math.radians(speed),) * 6, source / 1000, milliseconds * 1_000_000
    )


def test_crossing_resets_both_clocks_and_boundary_is_inclusive():
    window = settling.Standstill()
    assert not sample(window, 0)
    assert not sample(window, 100, speed=0.02)
    assert not sample(window, 200, speed=0.01)
    assert not sample(window, 399, speed=0.01)
    assert sample(window, 400, speed=0.01)
    assert not sample(window, 410, speed=0.02)


@pytest.mark.parametrize("source_ms", [0, 10, 199])
def test_receipt_time_cannot_turn_cache_into_standstill(source_ms):
    window = settling.Standstill()
    assert not sample(window, 0)
    assert not sample(window, 200, source_ms=source_ms)


@pytest.mark.parametrize("source_ms", [-100, 300, 10])
def test_gaps_and_rollback_start_a_new_window(source_ms):
    window = settling.Standstill()
    assert not sample(window, 0)
    assert not sample(window, 300, source_ms=source_ms)
    assert not sample(window, 400, source_ms=source_ms + 100)
    assert sample(window, 500, source_ms=source_ms + 200)


def test_nonfinite_speed_cannot_confirm_stop():
    window = settling.Standstill()
    assert not sample(window, 0)
    assert not sample(window, 200, speed=math.nan)
    assert not sample(window, 300)


class Transport:
    """Explicit feedback timeline; no simulator or SDK connection."""

    def __init__(self):
        self.feedback = model.State(profile.HOME, (0.0,) * 6, 0, 0)
        self.stops = []
        self.heartbeats = 0

    def read(self):
        return self.feedback

    def heartbeat(self):
        self.heartbeats += 1

    def stop(self, servo):
        self.stops.append(servo)

    def advance(self, milliseconds, speed=0):
        self.feedback = dataclasses.replace(
            self.feedback,
            timestamp=milliseconds / 1000,
            received_ns=milliseconds * 1_000_000,
            qd=(math.radians(speed),) * 6,
        )


@pytest.mark.parametrize("settles", [True, False])
def test_cancel_dispatches_now_and_confirms_or_faults_within_four_seconds(
    settles,
):
    device = Transport()
    control = owner.Controller(device, profile.LIMITS)
    control.tick(0)
    control.halt(0)
    assert device.stops == [False]
    for milliseconds in range(100, 3800, 100):
        device.advance(milliseconds, speed=0.02)
        control.tick(milliseconds * 1_000_000)
        assert control.state == "stopping"
    for milliseconds in (3800, 3900, 4000):
        device.advance(milliseconds, speed=0 if settles else 0.02)
        control.tick(milliseconds * 1_000_000)
    if settles:
        assert control.state == "hold"
        assert device.stops == [False]
    else:
        device.advance(4001)
        with pytest.raises(model.ControlError, match="timed out"):
            control.tick(4_001_000_000)
        assert control.state == "fault"


def test_cancel_does_not_confirm_from_repeated_cached_readback():
    device = Transport()
    control = owner.Controller(device, profile.LIMITS)
    control.tick(0)
    control.halt(0)
    control.tick(0)
    control.tick(200_000_000)
    assert control.state == "stopping"
    with pytest.raises(model.ControlError, match="stale"):
        control.tick(251_000_000)


def test_measured_slow_stop_keeps_heartbeat_after_old_deadline():
    device = Transport()
    control = owner.Controller(device, profile.LIMITS)
    control.tick(0)
    control.halt(0)
    for milliseconds in range(10, 2371, 10):
        # Reproduce the latest run's approximately 2.16-second crossing.
        device.advance(
            milliseconds, speed=0.016 if milliseconds < 2160 else 0.009
        )
        control.tick(milliseconds * 1_000_000)
        if milliseconds < 2360:
            assert control.state == "stopping"
    assert control.state == "hold"
    assert device.heartbeats == 238
    assert device.stops == [False]


def test_stop_timeout_explains_budget_without_refreshing_faulted_owner():
    device = Transport()
    control = owner.Controller(device, profile.LIMITS)
    control.tick(0)
    control.halt(0)
    for milliseconds in range(100, 4001, 100):
        device.advance(milliseconds, speed=0.02)
        control.tick(milliseconds * 1_000_000)
    count = device.heartbeats
    device.advance(4001, speed=0.02)
    with pytest.raises(
        model.ControlError, match="stop timed out.*budget_s=4.*max_speed"
    ):
        control.tick(4_001_000_000)
    assert device.heartbeats == count
    assert control.progress.target is None

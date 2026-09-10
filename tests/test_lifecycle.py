"""Distinct Space boundaries, repeat suppression and honest discard states."""

import pytest

from ur12e_collection.control.lifecycle import Lifecycle
from ur12e_collection.control.model import ControlError


def recording():
    lifecycle = Lifecycle()
    assert lifecycle.key(" ", 0) == "home"
    lifecycle.complete("home")
    assert lifecycle.key(" ", 1_000_000_000) == "prepare"
    lifecycle.complete("prepare")
    return lifecycle


def test_episode_then_explicit_home_then_distinct_new_start():
    lifecycle = recording()
    assert lifecycle.key(" ", 2_000_000_000) == "stop"
    assert lifecycle.key(" ", 3_000_000_000) is None
    lifecycle.complete("stop")
    assert lifecycle.key(" ", 4_000_000_000) is None
    lifecycle.complete("finalize")
    assert lifecycle.state == "held"
    assert lifecycle.key(" ", 5_000_000_000) == "home"
    lifecycle.complete("home")
    assert lifecycle.state == "ready"
    assert lifecycle.key(" ", 6_000_000_000) == "prepare"


def test_key_repeat_never_starts_second_phase_even_after_long_motion():
    lifecycle = Lifecycle()
    assert lifecycle.key(" ", 0) == "home"
    for i in range(1, 100):
        if i == 50:
            lifecycle.complete("home")
        assert lifecycle.key(" ", i * 50_000_000) is None
    assert lifecycle.state == "ready"
    assert lifecycle.key(" ", 6_000_000_000) == "prepare"


def test_active_and_held_discard_do_not_request_home():
    lifecycle = recording()
    assert lifecycle.key("a", 2_000_000_000) == "stop"
    assert lifecycle.discard
    lifecycle.complete("stop")
    lifecycle.complete("finalize")
    assert lifecycle.key("a", 3_000_000_000) == "discard"
    assert lifecycle.state == "held"


def test_fault_cannot_be_cleared_by_keys_or_late_completion():
    lifecycle = recording()
    lifecycle.fail()
    assert lifecycle.key(" ", 2_000_000_000) is None
    with pytest.raises(ControlError):
        lifecycle.complete("prepare")

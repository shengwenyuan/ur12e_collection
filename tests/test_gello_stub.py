"""Unavailable leader hooks must never invent a successful hardware action."""

from unittest import mock

import pytest

from ur12e_collection import gello


def test_stub_never_reports_ready_or_moves():
    """Every control request fails explicitly and opens no network connection."""
    leader = gello.UnavailableGello()
    with mock.patch("socket.socket", side_effect=AssertionError("network")):
        assert leader.read_state() is None
        assert leader.health()["ready"] is False
        for request in (
            lambda: leader.move_to((0,) * 6, ()),
            leader.hold,
            leader.stop,
        ):
            with pytest.raises(gello.GelloUnavailableError):
                request()

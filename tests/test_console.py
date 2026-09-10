"""Terminal restoration and the explicit no-physical-control CLI boundary."""

import os
import termios
from unittest import mock

import pytest

from ur12e_collection import cli
from ur12e_collection.control import console


def test_terminal_restored_after_interrupt():
    master, slave = os.openpty()
    with os.fdopen(slave, "r") as stream:
        original = termios.tcgetattr(stream.fileno())
        try:
            with pytest.raises(KeyboardInterrupt):
                with console.keyboard(stream) as keys:
                    assert (
                        not termios.tcgetattr(stream.fileno())[3]
                        & termios.ICANON
                    )
                    os.write(master, b" a")
                    assert keys() == [" ", "a"]
                    raise KeyboardInterrupt
            restored = termios.tcgetattr(stream.fileno())
            # macOS sets the transient PENDIN flag when restoring canonical input.
            restored[3] &= ~getattr(termios, "PENDIN", 0)
            original[3] &= ~getattr(termios, "PENDIN", 0)
            assert restored == original
        finally:
            os.close(master)


def test_physical_session_fails_before_network_or_simulator_import(capsys):
    with mock.patch("socket.socket", side_effect=AssertionError("network")):
        assert cli.main(["session", "--backend", "hardware"]) == 2
        assert cli.main(["session", "--backend", "ursim"]) == 1
    assert "control is disabled" in capsys.readouterr().err

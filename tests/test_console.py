"""Terminal restoration and the explicit no-physical-control CLI boundary."""

import os
import termios
from unittest import mock

import pytest

from ur12e_collection import cli
from ur12e_collection.control import console
from ur12e_collection.control import model, ur


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


def test_servo_duration_matches_selected_command_rate():
    sdk = mock.Mock()
    transport = ur.URTransport(sdk, mock.Mock())
    transport.servo((0.0,) * 6)
    assert sdk.servoJ.call_args.args[3] == 1 / model.COMMAND_HZ


def test_console_keeps_phase_and_skips_overrun_without_burst():
    clock, starts = [0], []
    owner = mock.Mock(state="held", snapshot={"control": {"control_hz": 120}})
    owner.completed = []

    def step():
        starts.append(clock[0])
        clock[0] += 25_000_000 if len(starts) == 3 else 2_000_000

    def keys():
        if len(starts) == 5:
            raise KeyboardInterrupt
        return []

    def sleep(seconds):
        clock[0] += round(seconds * 1e9) + 50_000

    owner.step.side_effect = step
    with (
        mock.patch.object(
            console.time, "monotonic_ns", side_effect=lambda: clock[0]
        ),
        mock.patch.object(console.time, "sleep", side_effect=sleep),
    ):
        assert console.drive(owner, keys)["state"] == "interrupted"
    period = round(1e9 / 120)
    assert starts == [
        0,
        period + 50_000,
        2 * period + 50_000,
        6 * period + 50_000,
        7 * period + 50_000,
    ]

"""Verify read-only wire isolation before any physical diagnostic."""

from unittest import mock

import pytest
from dynamixel_sdk import PacketHandler

from ur12e_collection.leader import bus


def test_motor_writes_cannot_reach_serial():
    """Exercise the real SDK packet encoder, not a duplicate opcode helper."""
    port = bus.ReadPort("test")
    port.ser = mock.Mock()
    packet = PacketHandler(2.0)
    for address, value in ((64, 1), (116, 0), (8, 3), (168, 132)):
        with pytest.raises(bus.ReadError, match="only PING"):
            packet.write1ByteTxRx(port, 1, address, value)
        port.is_using = False
    for opcode in (0x03, 0x04, 0x05, 0x06, 0x08, 0x83, 0x93):
        with pytest.raises(bus.ReadError):
            port.writePort(
                b"\xff\xff\xfd\x00\x01\x03\x00" + bytes([opcode, 0, 0])
            )
    port.ser.write.assert_not_called()


def test_sync_uses_real_read_instruction_and_preserves_status():
    """SYNC_READ reaches the wire; an alert is not discarded by the SDK."""
    with mock.patch.object(bus.serial, "Serial") as serial:
        serial.return_value.write.side_effect = len
        with bus.ReadBus("test") as reader:
            with mock.patch.object(
                reader._packet,
                "readRx",
                side_effect=[([0xFF] * 4, 0, 0x80)] + [([0] * 4, 0, 0)] * 6,
            ):
                sample = reader.sync(132, 4)
            assert sample.errors == (0x80, 0, 0, 0, 0, 0, 0)
            assert sample.integers(132, 4, signed=True)[0] == -1
            assert sample.start_ns <= sample.end_ns
            assert reader.traffic() == {"0x82": 1}
        assert serial.call_args.kwargs["exclusive"] is True
        serial.return_value.close.assert_called_once()


def test_failed_open_and_unsupported_baud_do_not_mask_errors():
    """A missing serial handle never replaces the original startup failure."""
    with mock.patch.object(
        bus.serial, "Serial", side_effect=PermissionError("denied")
    ):
        with pytest.raises(PermissionError, match="denied"):
            bus.ReadBus("test")
    with pytest.raises(bus.ReadError, match="unsupported"):
        bus.ReadBus("test", 123)


def test_incomplete_group_never_returns_partial_sample():
    with mock.patch.object(bus.serial, "Serial") as serial:
        serial.return_value.write.side_effect = len
        with bus.ReadBus("test") as reader:
            with mock.patch.object(
                reader._packet, "readRx", return_value=([0], 0, 0)
            ):
                with pytest.raises(bus.ReadError, match="incomplete"):
                    reader.sync(132, 4)


def test_block_rejects_missing_register_and_keeps_signed_branch():
    sample = bus.Block(
        1, 2, 132, ((-4097).to_bytes(4, "little", signed=True),), (0,)
    )
    assert sample.integers(132, 4, signed=True) == (-4097,)
    with pytest.raises(ValueError, match="outside"):
        sample.integers(128, 4)


def test_fast_read_preserves_each_error_and_validates_ids():
    data = []
    for motor in bus.IDS:
        data.extend([0x80 if motor == 2 else 0, motor, motor, 0, 0, 0, 0, 0])
    with mock.patch.object(bus.serial, "Serial") as serial:
        serial.return_value.write.side_effect = len
        with bus.ReadBus("test") as reader:
            with mock.patch.object(
                reader._packet, "fastSyncReadRx", return_value=(data, 0, 0)
            ):
                sample = reader.sync(132, 4, fast=True)
                assert sample.errors == (0, 0x80, 0, 0, 0, 0, 0)
                assert sample.integers(132, 4) == bus.IDS
                assert reader.traffic() == {"0x8a": 1}
                reader._port.is_using = (
                    False  # Mocked receive bypasses SDK cleanup.
                )
                data[9] = 1
                with pytest.raises(bus.ReadError, match="identity"):
                    reader.sync(132, 4, fast=True)

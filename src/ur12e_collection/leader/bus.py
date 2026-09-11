"""Read-only DYNAMIXEL bus with a wire instruction allowlist."""

import collections
import dataclasses
import time

from dynamixel_sdk import Protocol2PacketHandler, PortHandler
import serial

IDS = tuple(range(1, 8))


class ReadError(RuntimeError):
    """A transaction cannot supply complete trustworthy motor feedback."""


class ReadPort(PortHandler):
    """Keep serial ownership exclusive and reject writes before the OS call."""

    def __init__(self, device):
        super().__init__(device)
        self.instructions = collections.Counter()

    def setupPort(self, cflag_baud):  # pylint: disable=invalid-name
        self.ser = serial.Serial(
            self.port_name,
            baudrate=cflag_baud,
            timeout=0,
            write_timeout=1,
            exclusive=True,
        )
        self.is_open = True
        self.tx_time_per_byte = 10_000 / cflag_baud
        self.ser.reset_input_buffer()
        return True

    def getCurrentTime(self):  # pylint: disable=invalid-name
        return time.monotonic_ns() / 1_000_000

    def writePort(self, packet):  # pylint: disable=invalid-name
        # SDK adds header, stuffing and CRC before this final boundary.
        if (
            len(packet) < 10
            or bytes(packet[:4]) != b"\xff\xff\xfd\x00"
            or packet[7] not in (0x01, 0x02, 0x82, 0x8A)
        ):
            raise ReadError(
                "only PING and read instructions may reach the wire"
            )
        self.instructions[packet[7]] += 1
        return self.ser.write(packet)


@dataclasses.dataclass(frozen=True)
class Block:
    """Sequential bus replies in one host acquisition interval, not atomic."""

    start_ns: int
    end_ns: int
    address: int
    values: tuple[bytes, ...]
    errors: tuple[int, ...]

    def integers(self, address: int, size: int, *, signed=False) -> tuple:
        """Decode one register without modulo or implicit missing values."""
        offset = address - self.address
        if offset < 0 or any(offset + size > len(v) for v in self.values):
            raise ValueError("register lies outside the acquired block")
        return tuple(
            int.from_bytes(v[offset : offset + size], "little", signed=signed)
            for v in self.values
        )


class ReadBus:
    """One explicitly opened serial connection; no motor mutation API."""

    _port_type = ReadPort

    def __init__(self, device: str, baudrate: int = 57600):
        self._port = self._port_type(device)
        self._packet = Protocol2PacketHandler()
        try:
            if not self._port.setBaudRate(baudrate):
                raise ReadError(f"unsupported host baudrate: {baudrate}")
        except BaseException:
            self.close()
            raise

    def _check(self, result):
        if result != 0:
            raise ReadError(self._packet.getTxRxResult(result))

    def read(self, motor: int, address: int, size: int) -> Block:
        """Read a block; preserve the motor status error for diagnostics."""
        start = time.monotonic_ns()
        data, result, error = self._packet.readTxRx(
            self._port, motor, address, size
        )
        self._check(result)
        if len(data) != size:
            raise ReadError("incomplete motor block")
        return Block(
            start, time.monotonic_ns(), address, (bytes(data),), (error,)
        )

    def sync(self, address: int, size: int, *, fast: bool = False) -> Block:
        """Read all IDs, retaining status flags discarded by GroupSyncRead."""
        start = time.monotonic_ns()
        self._check(
            self._packet.syncReadTx(
                self._port, address, size, list(IDS), len(IDS), fast
            )
        )
        if fast:
            return self._fast_reply(start, address, size)
        values, errors = [], []
        for motor in IDS:
            data, result, error = self._packet.readRx(self._port, motor, size)
            self._check(result)
            if len(data) != size:
                raise ReadError(f"ID{motor}: incomplete sync reply")
            values.append(bytes(data))
            errors.append(error)
        return Block(
            start, time.monotonic_ns(), address, tuple(values), tuple(errors)
        )

    def _fast_reply(self, start, address, size):
        width = size + 4
        data, result, _ = self._packet.fastSyncReadRx(
            self._port, 254, width * len(IDS)
        )
        self._check(result)
        if len(data) != width * len(IDS):
            raise ReadError("incomplete fast sync reply")
        values, errors = [], []
        for index, motor in enumerate(IDS):
            offset = index * width
            if data[offset + 1] != motor:
                raise ReadError("fast reply identity/order mismatch")
            errors.append(data[offset])
            values.append(bytes(data[offset + 2 : offset + 2 + size]))
        return Block(
            start, time.monotonic_ns(), address, tuple(values), tuple(errors)
        )

    def traffic(self) -> dict:
        """Count transmitted read instructions, including failed reads."""
        return {
            hex(opcode): count
            for opcode, count in sorted(self._port.instructions.items())
        }

    def close(self) -> None:
        """Close once; never alter torque, goals or watchdog registers."""
        if self._port.ser is not None:
            self._port.ser.close()
            self._port.ser = None
            self._port.is_open = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

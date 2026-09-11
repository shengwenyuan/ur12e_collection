"""Baud changes are explicit, addressed, verified and recoverable on failure."""

import json
from unittest import mock

import pytest
from dynamixel_sdk import Protocol2PacketHandler

from ur12e_collection.leader import bus, maintenance as m


class FakeBus:
    """A two-rate bus model; writes take effect even when the ACK is lost."""

    def __init__(self, state, rate):
        self.state, self.rate = state, rate
        self.sent = {}

    def host_baud(self, rate):
        self.rate = rate

    def read(self, motor, address, size):
        if self.state["rates"][motor] != self.rate or motor == self.state.get(
            "missing"
        ):
            raise bus.ReadError("no reply")
        table = bytearray(147)
        table[0:2] = (1060).to_bytes(2, "little")
        table[6] = 50
        table[7] = motor
        table[8] = m.RATES[self.rate]
        table[64] = self.state.get("torque", 0)
        return bus.Block(
            1, 2, address, (bytes(table[address : address + size]),), (0,)
        )

    def write_baud(self, motor, value):
        self.state["writes"].append(motor)
        self.state["rates"][motor] = next(
            rate for rate, register in m.RATES.items() if register == value
        )
        self.sent["0x3"] = self.sent.get("0x3", 0) + 1
        if motor == self.state.get("interrupt"):
            raise KeyboardInterrupt()
        if motor == self.state.get("lose_device"):
            self.state["missing"] = motor
        return "lost ACK" if value == 3 else None

    def traffic(self):
        return self.sent.copy()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.fixture
def setup(tmp_path, monkeypatch):
    state = {"rates": dict.fromkeys(bus.IDS, 57600), "writes": []}
    factory = lambda device, rate=57600: FakeBus(state, rate)
    monkeypatch.setattr(m, "MaintenanceBus", factory)
    monkeypatch.setattr(bus, "ReadBus", factory)
    plan = tmp_path / "plan.json"
    m.prepare("fake", plan)
    assert state["writes"] == []
    return state, plan, tmp_path / "result"


def test_unconfirmed_apply_never_opens_bus(tmp_path):
    with mock.patch.object(m, "MaintenanceBus") as factory:
        with pytest.raises(ValueError, match="confirmation"):
            m.apply(tmp_path / "missing", tmp_path / "result")
        factory.assert_not_called()


def test_migration_reads_back_lost_ack_and_reopens(setup):
    state, plan, result = setup
    value = m.apply(plan, result, confirmed=True)
    assert value["state"] == "completed"
    assert value["motion_ready"] is False
    assert state["writes"] == list(bus.IDS)
    assert set(state["rates"].values()) == {1000000}
    events = [
        json.loads(line)
        for line in (result / "journal.jsonl").read_text().splitlines()
    ]
    assert [e["motor"] for e in events if e["event"] == "verified"] == list(
        bus.IDS
    )
    assert events[-1]["event"] == "completed"
    assert all(e["value"] == 3 for e in events if e["event"] == "write_intent")


@pytest.mark.parametrize("fault", ["interrupt", "lose_device"])
def test_partial_migration_stops_and_classifies_without_more_writes(
    setup, fault
):
    state, plan, output = setup
    state[fault] = 3
    result = m.apply(plan, output, confirmed=True)
    assert result["state"] == "failed"
    assert state["writes"] == [1, 2, 3]
    assert result["classification"]["1"] == [1000000]
    assert result["classification"]["4"] == [57600]
    assert result["classification"]["3"] == (
        [] if fault == "lose_device" else [1000000]
    )
    assert "connection" not in result
    assert (output / "journal.jsonl").read_text().count("write_intent") == 3


@pytest.mark.parametrize("fault", ["torque", "missing", "mixed"])
def test_preflight_rejects_changes_without_motor_writes(setup, fault):
    state, plan, output = setup
    if fault == "mixed":
        state["rates"][4] = 1000000
    else:
        state[fault] = 1
    result = m.apply(plan, output, confirmed=True)
    assert result["state"] == "failed"
    assert state["writes"] == []


def test_prepared_plan_cannot_be_edited(setup):
    state, plan, output = setup
    value = json.loads(plan.read_text())
    value["device"] = "different"
    plan.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="differs"):
        m.apply(plan, output, confirmed=True)
    assert state["writes"] == []


def test_real_encoder_only_allows_one_armed_baud_write():
    port = m._BaudPort("not-opened")
    port.ser = mock.Mock()
    port.ser.write.side_effect = len
    packet = Protocol2PacketHandler()
    for motor, address, value, width in (
        (1, 64, 1, 1),
        (1, 116, 3, 1),
        (254, 8, 3, 1),
        (8, 8, 3, 1),
        (1, 8, 4, 1),
        (1, 8, 3, 2),
    ):
        port.permit = (1, 3)
        port.is_using = False
        with pytest.raises(bus.ReadError):
            packet.writeTxOnly(port, motor, address, width, [value] * width)
    port.ser.write.assert_not_called()
    port.permit = (1, 3)
    port.is_using = False
    assert packet.write1ByteTxOnly(port, 1, 8, 3) == 0
    wire = bytes(port.ser.write.call_args.args[0])
    assert wire[4:11] == bytes((1, 6, 0, 3, 8, 0, 3))
    assert port.permit is None
    with pytest.raises(bus.ReadError):
        packet.write1ByteTxOnly(port, 1, 8, 3)
    assert port.ser.write.call_count == 1


def test_real_maintenance_refuses_torque_without_disabling_it():
    with mock.patch.object(bus.serial, "Serial"):
        with m.MaintenanceBus("fake") as link:
            with mock.patch.object(
                link, "read", return_value=bus.Block(0, 1, 64, (b"\x01",), (0,))
            ):
                with pytest.raises(bus.ReadError, match="torque off"):
                    link.write_baud(1, 3)
                link._port.ser.write.assert_not_called()


def test_journal_failure_prevents_the_next_write(setup, monkeypatch):
    state, plan, output = setup
    original = m._event

    def fail(stream, name, **values):
        if name == "write_intent" and values["motor"] == 2:
            raise OSError("journal unavailable")
        return original(stream, name, **values)

    monkeypatch.setattr(m, "_event", fail)
    result = m.apply(plan, output, confirmed=True)
    assert result["state"] == "failed"
    assert state["writes"] == [1]
    assert result["classification"]["1"] == [1000000]
    assert result["classification"]["2"] == [57600]


def test_final_journal_failure_does_not_report_success(setup, monkeypatch):
    _, plan, output = setup
    original = m._event

    def fail(stream, name, **values):
        if name == "completed":
            raise OSError("completion not durable")
        return original(stream, name, **values)

    monkeypatch.setattr(m, "_event", fail)
    result = m.apply(plan, output, confirmed=True)
    assert result["state"] == "failed"
    assert "connection" not in result
    assert "durable" in result["error"]


def test_torque_off_goal_tracking_is_not_a_static_configuration_change():
    old = {key: 0 for key in m.SETTINGS}
    old.update(goal_position=100, position=100)
    new = old | {"goal_position": 101, "position": 101}
    m._same_settings({"1": old}, {"1": new})
    for bad in (
        new | {"position": 100},
        new | {"torque": 1},
        new | {"position_p_gain": 640},
    ):
        with pytest.raises(bus.ReadError):
            m._same_settings({"1": old}, {"1": bad})
    with pytest.raises(bus.ReadError):
        m._same_settings({"1": old | {"position": 99}}, {"1": new})


@pytest.mark.parametrize("interrupted", [False, True])
def test_3mbps_transition_verifies_new_register_and_only_classifies_its_rates(
    setup, interrupted
):
    state, old_plan, output = setup
    state["rates"] = dict.fromkeys(bus.IDS, 1000000)
    plan = old_plan.with_name("3mbps.json")
    m.prepare("fake", plan, from_baud=1000000, to_baud=3000000)
    if interrupted:
        state["interrupt"] = 3
    result = m.apply(plan, output, confirmed=True)
    if interrupted:
        assert result["state"] == "failed"
        assert state["writes"] == [1, 2, 3]
        assert result["classification"]["1"] == [3000000]
        assert result["classification"]["4"] == [1000000]
    else:
        assert result["state"] == "completed"
        assert result["connection"]["baudrate"] == 3000000
        assert set(state["rates"].values()) == {3000000}
        events = [
            json.loads(l)
            for l in (output / "journal.jsonl").read_text().splitlines()
        ]
        assert all(
            e["value"] == 5 for e in events if e["event"] == "write_intent"
        )


def test_unsupported_transition_never_opens_port(tmp_path):
    with mock.patch.object(m, "MaintenanceBus") as factory:
        with pytest.raises(ValueError, match="unsupported"):
            m.prepare(
                "fake", tmp_path / "plan", from_baud=57600, to_baud=3000000
            )
        factory.assert_not_called()

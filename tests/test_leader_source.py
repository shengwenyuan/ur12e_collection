"""Persistent read ownership, bounded consumers and source fault isolation."""

import dataclasses
import threading
import time
from unittest import mock

import pytest

from ur12e_collection.control import model
from ur12e_collection.leader import bus, episode, source
from test_leader_episode import HOME, calibration


def motion(sequence, *, epoch="test", start=None):
    start = sequence * 16_666_667 if start is None else start
    return source.Motion(
        episode.Sample(
            epoch, sequence, start, start + 1_000_000, (2200,) * 6 + (3200,)
        ),
        (0,) * 7,
    )


def health(start=0, error=0):
    return bus.Block(
        start, start + 1, 64, (bytes([0] * 6 + [error]),) * 7, (0,) * 7
    )


def mailbox(capacity=120):
    value = source.Mailbox(capacity)
    value.health(health())
    for i in range(4):
        value.publish(motion(i))
    return value


def test_independent_consumers_preserve_source_identity_and_episode_anchor():
    value = mailbox()
    now = 52_000_000
    view = value.view(now)
    assert value.view(now + 1) == view
    assert len(value.drain()) == 4
    assert value.drain() == ()
    assert value.view(now) == view
    follower = model.State(HOME, (0.0,) * 6, 1.0, now)
    mapper = episode.EpisodeMapper(
        calibration(),
        model.Limits((-6.0,) * 6, (6.0,) * 6, HOME),
        [m.sample for m in view.recent],
        follower,
        now,
    )
    assert mapper.first().q == HOME
    sample = dataclasses.replace(motion(4).sample, raw=(2210,) * 6 + (3200,))
    target = mapper.target(sample, 69_000_000)
    assert target.q != HOME
    assert mapper.context()["baseline"]["sequence"] == 3


@pytest.mark.parametrize(
    "bad",
    [
        motion(3),
        motion(5),
        motion(4, epoch="new"),
        motion(4, start=160_000_000),
    ],
)
def test_discontinuity_latches_and_retains_existing_evidence(bad):
    value = mailbox()
    with pytest.raises(bus.ReadError, match="discontinuity"):
        value.publish(bad)
    assert len(value.drain()) == 4
    with pytest.raises(bus.ReadError):
        value.publish(motion(4))


def test_overflow_is_not_a_silent_drop_or_recoverable_by_drain():
    value = mailbox(4)
    with pytest.raises(bus.ReadError, match="overflow"):
        value.publish(motion(4))
    assert [m.sample.sequence for m in value.drain()] == [0, 1, 2, 3]
    with pytest.raises(bus.ReadError, match="overflow"):
        value.view(52_000_000)


@pytest.mark.parametrize("failure", ["motion", "health", "motor", "closed"])
def test_stale_or_faulted_source_never_republishes_cached_feedback(failure):
    value = mailbox()
    now = 52_000_000
    if failure == "motion":
        now = 200_000_000
    elif failure == "health":
        value._health = health(-3_000_000_000)
    elif failure == "motor":
        with pytest.raises(bus.ReadError, match="health"):
            value.health(health(error=1))
    else:
        value.fail("closed")
    with pytest.raises(bus.ReadError):
        value.view(now)
    with pytest.raises(bus.ReadError):
        value.publish(motion(4))


class FakeBus:
    """Read-only fake exposes no writes and records its owner thread."""

    def __init__(self, fail=False):
        self.calls = []
        self.closed = False
        self.fail = fail

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True
        self.calls.append(("close", threading.get_ident()))

    def sync(self, address, size):
        self.calls.append(((address, size), threading.get_ident()))
        if self.fail:
            raise bus.ReadError("disconnected")
        now = time.monotonic_ns()
        if address == 64:
            return health(now)
        data = (0).to_bytes(4, "little") + (2200).to_bytes(4, "little")
        return bus.Block(
            now, time.monotonic_ns(), address, (data,) * 7, (0,) * 7
        )

    def traffic(self):
        return {"0x82": len(self.calls) - 1}


@pytest.mark.parametrize("fail", [False, True])
def test_worker_owns_reads_and_close_without_motion_or_reconnect(fail):
    fake = FakeBus(fail)
    with (
        mock.patch.object(source.bus, "ReadBus", return_value=fake) as factory,
        mock.patch.object(source.probe, "inventory", return_value={}),
    ):
        reader = source.Reader("fake", 3000000)
        if fail:
            with pytest.raises(bus.ReadError, match="disconnected"):
                reader.start()
        else:
            reader.start()
            reader.mailbox.view(time.monotonic_ns())
        reader.close()
        reader.close()
        factory.assert_called_once_with("fake", 3000000)
        assert fake.closed
        owners = {owner for _, owner in fake.calls}
        assert len(owners) == 1 and threading.get_ident() not in owners
        assert source.READ_HZ == 60
        with pytest.raises(bus.ReadError):
            reader.mailbox.view(time.monotonic_ns())


def test_stream_evidence_feeds_existing_calibration_entrypoint(tmp_path):
    from ur12e_collection.leader import mapping, probe, stream

    reader = mock.Mock()
    reader.mailbox.drain.return_value = [
        motion(i, start=i * 20_000_000) for i in range(61)
    ]
    path = tmp_path / "samples.jsonl"
    with path.open("w") as trace:
        stream.write_samples(reader, trace, probe.Timing(), [])
    result = mapping.reference(path)
    assert result["home_counts"] == [2200] * 6 + [3200]
    assert result["motion_ready"] is False

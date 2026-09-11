"""Optional twin/policy boundaries cannot affect the motion owner."""

import time

import pytest

from ur12e_collection.extensions import (
    MailboxSink,
    DisabledPolicy,
    HandoverRequest,
)
from test_control_session import make


def test_stalled_twin_consumer_does_not_block_recording(controlled, tmp_path):
    owner, station, recorder = make(controlled, tmp_path)
    sink = MailboxSink(1)
    owner.observer = sink
    owner.key(" ", time.monotonic_ns())
    recorder.replies = [("prepare", None)]
    owner.step()
    count = len(station.transport.sent)
    for _ in range(20):
        owner.step()
    assert owner.state == "recording" and len(station.transport.sent) > count
    assert sink.health()["dropped_records"] > 0
    events = sink.drain()
    assert events[0]["records"][0]["kind"] == "authority_event"
    owner.close()
    assert sink.health()["state"] == "closed"


def test_policy_request_is_not_an_ownership_grant():
    policy = DisabledPolicy()
    request = HandoverRequest("gello", "policy", "future operator request")
    with pytest.raises(RuntimeError, match="disabled"):
        policy.request(request)
    with pytest.raises(RuntimeError, match="disabled"):
        policy.read({})
    with pytest.raises(ValueError):
        HandoverRequest("gello", "gello", "not a transition")

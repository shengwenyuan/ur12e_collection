"""Latest-view publication cannot consume a reader's only current sample."""

import multiprocessing
import time

import pytest

from ur12e_collection.simulation.latest import CAPACITY, Latest


def _publish(view):
    for sequence in range(300):
        view.publish({"sequence": sequence, "values": [sequence] * 128})


def _die_holding_lock(view, ready):
    view.lock.acquire()
    ready.send(True)
    ready.close()


def test_reads_do_not_consume_the_published_view():
    view = Latest(multiprocessing.get_context("spawn"))
    assert view.read(0) is None
    assert view.publish({"start_ns": 10, "sequence": 1})
    first = view.read(0)
    assert first == (1, {"start_ns": 10, "sequence": 1})
    assert view.read(0) == first
    assert view.read(1) is None
    assert view.publish({"start_ns": 20, "sequence": 2})
    assert view.read(1) == (2, {"start_ns": 20, "sequence": 2})


def test_contention_and_oversize_preserve_the_previous_complete_view():
    view = Latest(multiprocessing.get_context("spawn"))
    view.publish({"sequence": 1})
    view.lock.acquire()
    try:
        assert view.read(0) is None
        assert view.publish({"sequence": 2}) is False
    finally:
        view.lock.release()
    with pytest.raises(ValueError, match="capacity"):
        view.publish({"payload": "x" * CAPACITY})
    assert view.read(0) == (1, {"sequence": 1})


def test_concurrent_process_reads_never_observe_partial_payloads():
    context = multiprocessing.get_context("spawn")
    view = Latest(context)
    child = context.Process(target=_publish, args=(view,))
    child.start()
    observed = []
    try:
        deadline = time.monotonic() + 5
        while child.is_alive() and time.monotonic() < deadline:
            result = view.read(0)
            if result:
                _, value = result
                assert value["values"] == [value["sequence"]] * 128
                observed.append(value["sequence"])
        child.join(1)
        assert child.exitcode == 0
        assert observed and observed == sorted(observed)
    finally:
        if child.is_alive():
            child.kill()
        child.join()


def test_dead_writer_lock_never_blocks_control_reads():
    context = multiprocessing.get_context("spawn")
    view = Latest(context)
    parent, child_pipe = context.Pipe(duplex=False)
    child = context.Process(target=_die_holding_lock, args=(view, child_pipe))
    child.start()
    child_pipe.close()
    try:
        assert parent.poll(5) and parent.recv()
        child.join(1)
        assert child.exitcode == 0
        started = time.monotonic()
        assert view.read(0) is None
        assert time.monotonic() - started < 0.1
    finally:
        parent.close()
        if child.is_alive():
            child.kill()
        child.join()

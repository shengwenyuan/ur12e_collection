"""A killed process must not prevent cancellation of the surviving workers."""

import multiprocessing
import time

from ur12e_collection import workers


def _wait(flag, status):
    status.send("waiting")
    status.send(flag.wait(5))
    status.close()


def test_killed_waiter_cannot_block_cancellation_or_surviving_waiter():
    ctx = multiprocessing.get_context("spawn")
    flag = workers.Cancellation(ctx)
    children = []
    try:
        for _ in range(2):
            parent, child = ctx.Pipe()
            process = ctx.Process(target=_wait, args=(flag, child))
            process.start()
            child.close()
            children.append((process, parent))
            assert parent.poll(5) and parent.recv() == "waiting"
        time.sleep(0.02)
        children[0][0].kill()
        children[0][0].join(2)
        started = time.monotonic()
        flag.set()
        assert time.monotonic() - started < 0.1
        assert flag.is_set() and flag.wait(0)
        assert children[1][1].poll(1) and children[1][1].recv() is True
    finally:
        for process, parent in children:
            workers.stop(process)
            parent.close()


def test_cancellation_timeout_and_late_waiter_are_bounded():
    flag = workers.Cancellation(multiprocessing.get_context("spawn"))
    assert not flag.wait(0)
    started = time.monotonic()
    assert not flag.wait(0.01)
    assert 0.01 <= time.monotonic() - started < 0.1
    flag.set()
    flag.set()
    assert flag.wait() and flag.wait(-1)

"""Shared slots preserve pixels, ownership and bounded nonblocking behavior."""

import dataclasses
import multiprocessing
from multiprocessing import shared_memory

import numpy as np
import pytest

from ur12e_collection import shared_frames


def test_slot_reuse_cannot_overwrite_consumed_arrays(group_factory):
    receiver = shared_frames.Slots.create(
        multiprocessing.get_context("spawn"), 2
    )
    sender = shared_frames.Slots.attach(receiver.descriptor())
    name = receiver.memory.name
    try:
        original = group_factory().anchor
        consumed = receiver.unpack(sender.pack(original))
        for index in range(1, 6):
            frame = group_factory(index).anchor
            actual = receiver.unpack(sender.pack(frame))
            assert np.array_equal(actual.payload.rgb, frame.payload.rgb)
            assert np.array_equal(actual.payload.depth, frame.payload.depth)
            assert actual.metadata() == frame.metadata()
        assert np.array_equal(consumed.payload.rgb, original.payload.rgb)
        assert np.array_equal(consumed.payload.depth, original.payload.depth)
    finally:
        sender.close()
        receiver.close()
    with pytest.raises(FileNotFoundError):
        shared_memory.SharedMemory(name=name)


def test_exhaustion_and_repeated_slot_fail(group_factory):
    receiver = shared_frames.Slots.create(
        multiprocessing.get_context("spawn"), 1
    )
    sender = shared_frames.Slots.attach(receiver.descriptor())
    try:
        frame = group_factory().anchor
        header = sender.pack(frame)
        with pytest.raises(RuntimeError, match="exhausted"):
            sender.pack(frame)
        with pytest.raises(ValueError, match="slot"):
            receiver.unpack(dataclasses.replace(header, payload=-1))
        receiver.unpack(header)
        # A duplicate would over-release the bounded availability semaphore.
        with pytest.raises(ValueError):
            receiver.unpack(header)
    finally:
        sender.close()
        receiver.close()

"""Bounded RGB-D slots; only small frame headers travel through IPC queues."""

import dataclasses
from multiprocessing import shared_memory

import numpy as np

from ur12e_collection import codecs

RGB_BYTES = 640 * 480 * 3
FRAME_BYTES = 640 * 480 * 5


class Slots:
    """Copy before returning a slot; downstream arrays own their pixels."""

    def __init__(self, memory, available, capacity, *, owner=False):
        self.memory, self.available, self.capacity = memory, available, capacity
        self.write_index = self.read_index = 0
        self.owner = owner

    @classmethod
    def create(cls, context, capacity: int):
        """Allocate one fixed ring for a single camera's producer/consumer."""
        memory = shared_memory.SharedMemory(
            create=True, size=capacity * FRAME_BYTES
        )
        try:
            available = context.BoundedSemaphore(capacity)
            return cls(memory, available, capacity, owner=True)
        except BaseException:
            memory.close()
            memory.unlink()
            raise

    @classmethod
    def attach(cls, descriptor):
        """Attach a child without taking ownership of storage cleanup."""
        name, available, capacity = descriptor
        return cls(shared_memory.SharedMemory(name=name), available, capacity)

    def descriptor(self) -> tuple:
        """Pass a name and synchronization channel, never an image payload."""
        return self.memory.name, self.available, self.capacity

    def _views(self, index):
        if (
            not isinstance(index, int)
            or isinstance(index, bool)
            or not 0 <= index < self.capacity
        ):
            raise ValueError("invalid shared camera slot")
        offset = index * FRAME_BYTES
        return (
            np.ndarray(
                (480, 640, 3),
                dtype=np.uint8,
                buffer=self.memory.buf,
                offset=offset,
            ),
            np.ndarray(
                (480, 640),
                dtype=np.uint16,
                buffer=self.memory.buf,
                offset=offset + RGB_BYTES,
            ),
        )

    def pack(self, frame):
        """Publish only after both images occupy a uniquely reserved slot."""
        frame.payload.validate()
        if not self.available.acquire(block=False):
            raise RuntimeError("camera shared slots exhausted")
        ticket = self.write_index
        index = ticket % self.capacity
        self.write_index += 1
        rgb, depth = self._views(index)
        np.copyto(rgb, frame.payload.rgb)
        np.copyto(depth, frame.payload.depth)
        return dataclasses.replace(frame, payload=ticket)

    def unpack(self, frame):
        """Return owned pixel copies before allowing this slot to be reused."""
        if (
            not isinstance(frame.payload, int)
            or isinstance(frame.payload, bool)
            or frame.payload != self.read_index
        ):
            raise ValueError("shared camera slot is repeated or out of order")
        rgb, depth = self._views(frame.payload % self.capacity)
        result = dataclasses.replace(
            frame, payload=codecs.Images(rgb.copy(), depth.copy())
        )
        self.read_index += 1
        self.available.release()
        return result

    def close(self) -> None:
        """Children detach; the creating owner unlinks the fixed storage."""
        self.memory.close()
        if self.owner:
            self.memory.unlink()

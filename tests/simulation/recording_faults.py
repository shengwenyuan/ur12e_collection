"""Child-local storage faults; no physical source or global disk mutation."""

import dataclasses
import errno
import time

from ur12e_collection import archive, rig


@dataclasses.dataclass(frozen=True)
class Factory:
    """Install a fault only inside this disposable recorder's process."""

    kind: str
    trigger: object

    def __call__(self, config, context, abort):
        original = archive.ArchiveWriter.group

        def group(writer, value):
            if self.trigger.is_set():
                if self.kind == "disk":
                    raise OSError(errno.ENOSPC, "injected recorder disk full")
                if self.kind == "writer_backlog":
                    time.sleep(2)
                else:
                    raise ValueError("unsupported recording fault")
            return original(writer, value)

        archive.ArchiveWriter.group = group
        return rig.Rig(
            config,
            "synthetic",
            queue_capacity=context["control"]["camera_queue_capacity"],
            stop=abort,
        )

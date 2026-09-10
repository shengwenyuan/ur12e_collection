"""A real Ctrl+C process group has one owner and releases shared camera slots."""

import json
import os
import select
import signal
import subprocess
import sys
import time

import pytest
import ur12e_collection
from pathlib import Path


@pytest.mark.parametrize("delay", [0, 0.002, 0.02])
def test_foreground_group_interrupt_reaps_recording_children(
    tmp_path, controlled, delay
):
    context = dict(controlled)
    context["control"]["camera_transport"] = "shared_memory"
    settings = tmp_path / "context.json"
    settings.write_text(json.dumps(context))
    script = tmp_path / "interrupt.py"
    script.write_text("""
import json
import pathlib
import sys
import time
from multiprocessing import shared_memory
from ur12e_collection import recording, synthetic

if __name__ == "__main__":
    recorder = recording.Recorder(synthetic.configuration(),
                                  json.loads(pathlib.Path(sys.argv[1]).read_text()))
    try:
        recorder.start()
        names = [slots.memory.name for slots in recorder.slots.values()]
        print("ready", flush=True)
        while True:
            recorder.poll()
            time.sleep(0.02)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.close()
    for name in names:
        try:
            memory = shared_memory.SharedMemory(name=name)
        except FileNotFoundError:
            continue
        memory.close()
        raise AssertionError("shared camera memory leaked")
    print("closed", flush=True)
""")
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(
        Path(ur12e_collection.__file__).parent.parent
    )
    process = subprocess.Popen(
        [sys.executable, str(script), str(settings)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
        env=environment,
    )
    try:
        assert select.select([process.stdout], [], [], 35)[
            0
        ], "startup timed out"
        assert process.stdout.readline().strip() == "ready"
        time.sleep(delay)
        os.killpg(process.pid, signal.SIGINT)
        output, error = process.communicate(timeout=10)
        assert process.returncode == 0, error
        assert output.strip() == "closed"
        assert error == ""
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


def test_worker_signal_setup_cannot_change_the_main_process_handler():
    from ur12e_collection import workers

    previous = signal.getsignal(signal.SIGINT)
    workers.ignore_terminal_interrupt()
    assert signal.getsignal(signal.SIGINT) == previous

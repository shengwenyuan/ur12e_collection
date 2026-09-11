"""Exercise exact URCap wire framing and retained-grasp shutdown locally."""

import socket
import threading

import pytest

from ur12e_collection.control.gripper import Client


class Peer:
    def __init__(self, acknowledgement=b"ack", ready=3):
        self.client, self.server = socket.socketpair()
        self.requests = []
        self.values = dict(POS=3, PRE=0, STA=ready, OBJ=3, FLT=0, COU=0)
        self.acknowledgement = acknowledgement
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        try:
            with self.server.makefile("rb") as stream:
                for line in stream:
                    self.requests.append(line)
                    parts = line.decode().split()
                    if parts[0] == "GET":
                        self.server.sendall(
                            f"{parts[1]} {self.values[parts[1]]}\n".encode()
                        )
                    else:
                        for key, value in zip(parts[1::2], parts[2::2]):
                            self.values["PRE" if key == "POS" else key] = int(
                                value
                            )
                        # Split acknowledgement to exercise TCP fragmentation.
                        for value in self.acknowledgement:
                            self.server.sendall(bytes([value]))
        except (OSError, ValueError):
            pass
        finally:
            self.server.close()

    def close(self):
        self.client.close()
        self.thread.join(2)
        assert not self.thread.is_alive()


def test_gripper_request_does_not_fabricate_feedback_or_release():
    peer = Peer()
    owner = Client(peer.client)
    try:
        owner.move(200, 31, 42)
        assert owner.requested == 200
        measured, _ = owner.read()
        assert dict(measured)["POS"] == 3 and dict(measured)["PRE"] == 200
        count = len(peer.requests)
        owner.hold()
        owner.close()
        assert len(peer.requests) == count
        assert b"SET POS 200 SPE 31 FOR 42 GTO 1\n" in peer.requests
        assert not any(b"ACT" in line for line in peer.requests)
    finally:
        peer.close()


@pytest.mark.parametrize("ack", [b"nak", b"bad"])
def test_unacknowledged_request_closes_owner(ack):
    peer = Peer(ack)
    owner = Client(peer.client)
    try:
        with pytest.raises(ValueError, match="acknowledged"):
            owner.move(100, 1, 1)
        assert owner.closed and owner.requested is None
    finally:
        peer.close()


def test_inactive_gripper_never_auto_activates():
    peer = Peer(ready=0)
    owner = Client(peer.client)
    try:
        with pytest.raises(RuntimeError, match="ready"):
            owner.move(100, 1, 1)
        assert all(line.startswith(b"GET") for line in peer.requests)
        owner.close()
    finally:
        peer.close()

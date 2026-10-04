"""Unit tests are offline by construction (P00-T02).

Outbound sockets are blocked for every test in this directory, so a hidden
provider call fails loudly instead of quietly depending on the network. The
block is in-process only; subprocesses started by a test are unaffected and must
make their own guarantees.
"""

from __future__ import annotations

import socket

import pytest


class NetworkAccessDenied(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise NetworkAccessDenied(
            "a unit test attempted a network connection; move it to tests/integration "
            "and mark it `network`, or remove the dependency")

    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr(socket, "create_connection", deny)
    yield

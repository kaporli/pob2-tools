"""Unit tests are offline by construction (P00-T02).

Outbound sockets are blocked for every test in this directory, so a hidden
provider call fails loudly instead of quietly depending on the network.

What this does **not** cover, stated plainly because the guard is easy to
over-read:

* It is an autouse fixture, so it is active during test execution only. Import
  and collection happen before any fixture runs and are not covered.
* It patches this process. A subprocess a test starts is unaffected and must
  make its own guarantee.
* It patches ``socket``. A library reaching the network another way, for example
  through a C extension holding its own socket, would not be stopped.

`tests/unit/test_collection_is_offline.py` checks that collection does not boot
PoB by inspecting the console for PoB's banners. That is not proof that
collection cannot make a network call. Both guards need strengthening when
P03 introduces acquisition modules.
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

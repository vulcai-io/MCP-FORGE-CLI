"""
Test setup for contributors: no API key, no license, no network.

- `src/` is put first on the import path, so the tests run against the
  mirrored sources, not against an installed `vulcai-mcp-forge-cli`.
- Every environment variable that looks like a credential is removed.
- Outgoing network connections are refused (loopback is allowed). A test
  that needs the Internet must be marked `@pytest.mark.network`; run the
  offline suite with `pytest -m "not network"`.
"""
import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

for _name in list(os.environ):
    if any(word in _name.upper() for word in ("KEY", "TOKEN", "SECRET", "PASSWORD", "LICENSE")):
        del os.environ[_name]

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}
_original_connect = socket.socket.connect


def _offline_connect(self, address):
    host = address[0] if isinstance(address, tuple) else str(address)
    if host not in _LOOPBACK:
        raise OSError(f"network access blocked in tests: {address} (mark the test with @pytest.mark.network)")
    return _original_connect(self, address)


@pytest.fixture(autouse=True)
def _block_network(request, monkeypatch):
    if request.node.get_closest_marker("network") is None:
        monkeypatch.setattr(socket.socket, "connect", _offline_connect)


def pytest_configure(config):
    config.addinivalue_line("markers", "network: needs Internet access (excluded with -m \"not network\")")

"""Pytest fixtures for `scripts.ml_training` research tests.

Purpose:
    Provide small shared fixtures/utilities for the ML training research test suite. These tests
    are intended to be lightweight and runnable locally without external services.

Relationships:
    - Used by offload server/client tests that spin up in-process `aiohttp` test servers.
"""

from __future__ import annotations

import socket

import pytest


def _can_bind_localhost_socket() -> tuple[bool, str | None]:
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(("127.0.0.1", 0))
    except OSError as exc:
        return False, str(exc)
    finally:
        if sock is not None:
            sock.close()
    return True, None


@pytest.fixture(scope="session")
def requires_localhost_socket() -> None:
    """Skip tests that require localhost sockets when the environment forbids binding."""

    ok, error = _can_bind_localhost_socket()
    if not ok:
        detail = f": {error}" if error else ""
        pytest.skip(f"Localhost socket binding not permitted in this environment{detail}")

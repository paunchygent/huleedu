"""
Pytest configuration for distributed performance tests.

Provides test utilities and cleanup for distributed testing infrastructure.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest


@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear the global Prometheus registry before each test.
    
    Prevents metric registration conflicts during performance testing.
    This follows the same pattern as the main test conftest.py.
    """
    from prometheus_client import REGISTRY
    
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield
"""Pytest configuration for the Essay Lifecycle Service test suite.

This file provides fixtures that are automatically applied to all tests
within this directory, ensuring a clean and consistent testing environment.

Public API:
    - _clear_prometheus_registry: Fixture to clear the global Prometheus registry.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from prometheus_client import REGISTRY


@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Generator[None, None, None]:
    """Clear the global Prometheus registry before each test.

    This fixture prevents `ValueError: Duplicated timeseries` errors when running
    multiple tests that define the same metrics in the same process. This is the
    standard pattern mandated by rule 070-testing-and-quality-assurance.mdc.

    It is marked with `autouse=True` to be automatically applied to every
    test function within its scope without needing to be explicitly requested.

    Yields:
        None: Yields control back to the test function.
    """
    # Get a list of all collector names currently in the registry
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        # Unregister each collector to ensure a clean state
        REGISTRY.unregister(collector)
    yield
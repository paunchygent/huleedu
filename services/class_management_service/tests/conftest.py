"""Shared test fixtures and configuration for Class Management Service tests."""

from __future__ import annotations

from typing import Any

import pytest
from prometheus_client import REGISTRY


@pytest.fixture(autouse=True)
def _clear_prometheus_registry() -> Any:
    """
    Fixture to clear the default Prometheus registry before each test.

    This prevents "Duplicated timeseries in CollectorRegistry" errors
    when running multiple tests that register metrics.

    REQUIRED by rule 070: Testing and Quality Assurance
    """
    collectors = list(REGISTRY._collector_to_names.keys())
    for collector in collectors:
        REGISTRY.unregister(collector)
    yield

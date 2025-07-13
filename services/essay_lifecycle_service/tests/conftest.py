"""Pytest configuration for the Essay Lifecycle Service test suite.

This file provides fixtures that are automatically applied to all tests
within this directory, ensuring a clean and consistent testing environment.

Public API:
    - _clear_prometheus_registry: Fixture to clear the global Prometheus registry.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
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


@pytest.fixture
def opentelemetry_test_isolation() -> Generator[InMemorySpanExporter, None, None]:
    """
    Provide OpenTelemetry test isolation with InMemorySpanExporter.

    Works with existing TracerProvider by adding a test span processor
    with InMemorySpanExporter for collecting spans during tests.
    Cleans up after each test for proper isolation.
    """
    # Create an in-memory span exporter for test span collection
    span_exporter = InMemorySpanExporter()

    # Get the current tracer provider (may be already set by service initialization)
    current_provider = trace.get_tracer_provider()

    # If no provider is set yet, create one for tests
    if not hasattr(current_provider, 'add_span_processor'):
        test_provider = TracerProvider()
        trace.set_tracer_provider(test_provider)
        current_provider = test_provider

    # Add our test span processor to the existing provider
    test_processor = SimpleSpanProcessor(span_exporter)
    current_provider.add_span_processor(test_processor)

    try:
        # Yield the exporter so tests can access recorded spans
        yield span_exporter
    finally:
        # Clean up: clear spans and remove our processor if possible
        span_exporter.clear()
        # Note: TracerProvider doesn't have remove_span_processor,
        # but clearing the exporter is sufficient for test isolation

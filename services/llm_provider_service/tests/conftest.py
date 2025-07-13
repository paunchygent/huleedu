"""
Pytest configuration and fixtures for LLM Provider Service tests.

This module provides fixtures for testing the LLM provider service
with dependency injection and OpenTelemetry test isolation.
"""

from __future__ import annotations

from typing import Generator

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


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
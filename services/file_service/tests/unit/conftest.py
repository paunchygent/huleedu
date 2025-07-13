"""
Pytest configuration and fixtures for File Service unit tests.

This module provides shared fixtures for testing file service functionality
including mocked dependencies and test constants.
"""

from __future__ import annotations

from typing import Generator
from unittest.mock import AsyncMock

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from services.file_service.validation_models import ValidationResult


@pytest.fixture
def mock_text_extractor() -> AsyncMock:
    """Create mock text extractor."""
    extractor = AsyncMock()
    extractor.extract_text.return_value = (
        "This is a valid essay content with sufficient length for validation."
    )
    return extractor


@pytest.fixture
def mock_content_validator() -> AsyncMock:
    """Create mock content validator."""
    validator = AsyncMock()
    # Default to valid content
    validator.validate_content.return_value = ValidationResult(
        is_valid=True,
        error_code=None,
        error_message=None,
    )
    return validator


@pytest.fixture
def mock_content_client() -> AsyncMock:
    """Create mock content service client."""
    client = AsyncMock()
    client.store_content.return_value = "storage_id_12345"
    return client


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Create mock event publisher."""
    publisher = AsyncMock()
    publisher.publish_essay_content_provisioned.return_value = None
    publisher.publish_essay_validation_failed.return_value = None
    return publisher


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

"""
Pytest configuration and fixtures for NLP service tests.

This module provides fixtures for testing the NLP service
with dependency injection and mocked external dependencies.
"""

from __future__ import annotations

import json
from typing import Generator
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import ConsumerRecord
from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.event_enums import ProcessingEvent

# Import base event models that need rebuilding
from common_core.events.base_event_models import (
    BaseEventData,
    EventTracker,
    ProcessingUpdate,
)

# THEN import the models that depend on these enums
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)

# CRITICAL: Import ALL enum types FIRST to ensure they're available for forward reference resolution
from common_core.status_enums import ProcessingStage
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from prometheus_client import REGISTRY

# NOW rebuild models with all types available - use raise_errors=True to make failures visible
BaseEventData.model_rebuild(raise_errors=True)
ProcessingUpdate.model_rebuild(raise_errors=True)
EventTracker.model_rebuild(raise_errors=True)
EventEnvelope.model_rebuild(raise_errors=True)
SystemProcessingMetadata.model_rebuild(raise_errors=True)
EssayProcessingInputRefV1.model_rebuild(raise_errors=True)
BatchServiceNLPInitiateCommandDataV1.model_rebuild(raise_errors=True)


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
def sample_batch_id() -> str:
    """Provide a sample batch ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_parent_id() -> str:
    """Provide a sample parent ID for testing."""
    return str(uuid4())


@pytest.fixture
def system_metadata(sample_batch_id: str, sample_parent_id: str) -> SystemProcessingMetadata:
    """Provide sample SystemProcessingMetadata for testing."""
    return SystemProcessingMetadata(
        entity_id=sample_batch_id,
        entity_type="batch",
        parent_id=sample_parent_id,
        event=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND,
        processing_stage=ProcessingStage.PENDING,
    )


@pytest.fixture
def nlp_initiate_command(
    sample_batch_id: str,
    sample_parent_id: str,
    system_metadata: SystemProcessingMetadata,
) -> BatchServiceNLPInitiateCommandDataV1:
    """Provide sample BatchServiceNLPInitiateCommandDataV1 for testing."""
    return BatchServiceNLPInitiateCommandDataV1(
        event_name=ProcessingEvent.BATCH_NLP_INITIATE_COMMAND,
        entity_id=sample_batch_id,
        entity_type="batch",
        parent_id=sample_parent_id,
        essays_to_process=[],  # Empty list for testing
        language="en",
    )


@pytest.fixture
def nlp_command_envelope(
    nlp_initiate_command: BatchServiceNLPInitiateCommandDataV1,
) -> EventEnvelope[BatchServiceNLPInitiateCommandDataV1]:
    """Provide sample EventEnvelope with BatchServiceNLPInitiateCommandDataV1 for testing."""
    return EventEnvelope[BatchServiceNLPInitiateCommandDataV1](
        event_type="batch.nlp.initiate.command.v1",
        source_service="test-service",
        correlation_id=uuid4(),
        data=nlp_initiate_command,
    )


@pytest.fixture
def kafka_message(
    nlp_command_envelope: EventEnvelope[BatchServiceNLPInitiateCommandDataV1],
    sample_batch_id: str,
) -> ConsumerRecord:
    """Provide a mock Kafka ConsumerRecord for testing."""
    # Serialize to JSON bytes like Kafka would send
    message_value = json.dumps(nlp_command_envelope.model_dump(mode="json")).encode("utf-8")

    # Create a mock ConsumerRecord
    record = MagicMock(spec=ConsumerRecord)
    record.topic = "test-topic"
    record.partition = 0
    record.offset = 123
    record.key = sample_batch_id.encode("utf-8")
    record.value = message_value

    return record


@pytest.fixture
def mock_kafka_bus() -> AsyncMock:
    """Provide a mock KafkaBus for testing."""
    from huleedu_service_libs.kafka_client import KafkaBus

    kafka_bus = AsyncMock(spec=KafkaBus)
    kafka_bus.publish = AsyncMock()
    return kafka_bus


@pytest.fixture
def mock_http_session() -> AsyncMock:
    """Provide a mock HTTP session for testing."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def invalid_kafka_message() -> ConsumerRecord:
    """Provide an invalid Kafka message for testing validation errors."""
    record = MagicMock(spec=ConsumerRecord)
    record.topic = "test-topic"
    record.partition = 0
    record.offset = 456
    record.key = b"invalid-key"
    # Provide invalid JSON bytes like Kafka would send
    record.value = json.dumps({"invalid": "data"}).encode("utf-8")

    return record


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
    if not hasattr(current_provider, "add_span_processor"):
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

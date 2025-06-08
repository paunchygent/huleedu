"""
Pytest configuration and fixtures for spell checker service tests.

This module provides fixtures for testing the spell checker service
with dependency injection and mocked external dependencies.
"""

from __future__ import annotations

import json
from typing import Optional, Tuple
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import aiohttp
import pytest
from aiokafka import AIOKafkaProducer, ConsumerRecord

# CRITICAL: Import ALL enum types FIRST to ensure they're available for forward reference resolution
# Note: We need BatchStatus even though spell checker doesn't use it directly,
# because ProcessingUpdate has Union["EssayStatus", "BatchStatus"] annotation
from common_core.enums import (
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
)
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1

# Import base event models that also need rebuilding
from common_core.events.base_event_models import (
    BaseEventData,
    EventTracker,
    ProcessingUpdate,
)

# THEN import the models that depend on these enums
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    EntityReference,
    SystemProcessingMetadata,
)

# NOW rebuild models with all types available - use raise_errors=True to make failures visible
# This ensures forward references like "ProcessingEvent", "EssayStatus", "BatchStatus" can be
# resolved
BaseEventData.model_rebuild(raise_errors=True)
ProcessingUpdate.model_rebuild(raise_errors=True)
EventTracker.model_rebuild(raise_errors=True)
SpellcheckResultDataV1.model_rebuild(raise_errors=True)
EssayLifecycleSpellcheckRequestV1.model_rebuild(raise_errors=True)
EventEnvelope.model_rebuild(raise_errors=True)
SystemProcessingMetadata.model_rebuild(raise_errors=True)
EntityReference.model_rebuild(raise_errors=True)

# Configure logging for tests to ensure caplog works properly
# NOTE: Logging now configured globally in root tests/conftest.py to avoid conflicts

@pytest.fixture
def sample_essay_id() -> str:
    """Provide a sample essay ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_storage_id() -> str:
    """Provide a sample storage ID for testing."""
    return str(uuid4())


@pytest.fixture
def sample_text() -> str:
    """Provide sample text with spelling errors for testing."""
    return "This is a tset essay with teh word recieve spelled incorrectly."


@pytest.fixture
def corrected_text() -> str:
    """Provide the corrected version of sample text."""
    return "This is a test essay with the word receive spelled incorrectly."


@pytest.fixture
def entity_reference(sample_essay_id: str) -> EntityReference:
    """Provide a sample EntityReference for testing."""
    return EntityReference(entity_id=sample_essay_id, entity_type="essay", parent_id=str(uuid4()))


@pytest.fixture
def system_metadata(entity_reference: EntityReference) -> SystemProcessingMetadata:
    """Provide sample SystemProcessingMetadata for testing."""
    return SystemProcessingMetadata(
        entity=entity_reference,
        event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
        processing_stage=ProcessingStage.PENDING,
    )


@pytest.fixture
def spellcheck_request_data(
    entity_reference: EntityReference,
    system_metadata: SystemProcessingMetadata,
    sample_storage_id: str,
) -> EssayLifecycleSpellcheckRequestV1:
    """Provide sample EssayLifecycleSpellcheckRequestV1 for testing."""
    return EssayLifecycleSpellcheckRequestV1(
        event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
        entity_ref=entity_reference,
        status=EssayStatus.AWAITING_SPELLCHECK,
        system_metadata=system_metadata,
        text_storage_id=sample_storage_id,
        language="en",  # Add required language field
    )


@pytest.fixture
def spellcheck_request_envelope(
    spellcheck_request_data: EssayLifecycleSpellcheckRequestV1,
) -> EventEnvelope[EssayLifecycleSpellcheckRequestV1]:
    """Provide sample EventEnvelope with EssayLifecycleSpellcheckRequestV1 for testing."""
    return EventEnvelope[EssayLifecycleSpellcheckRequestV1](
        event_type="essay.spellcheck.requested.v1",
        source_service="test-service",
        correlation_id=uuid4(),
        data=spellcheck_request_data,
    )


@pytest.fixture
def kafka_message(
    spellcheck_request_envelope: EventEnvelope[EssayLifecycleSpellcheckRequestV1],
    sample_essay_id: str,
) -> ConsumerRecord:
    """Provide a mock Kafka ConsumerRecord for testing."""
    # Serialize to JSON bytes like Kafka would send
    message_value = json.dumps(spellcheck_request_envelope.model_dump(mode="json")).encode("utf-8")

    # Create a mock ConsumerRecord
    record = MagicMock(spec=ConsumerRecord)
    record.topic = "test-topic"
    record.partition = 0
    record.offset = 123
    record.key = sample_essay_id.encode("utf-8")
    record.value = message_value

    return record


@pytest.fixture
def mock_producer() -> AsyncMock:
    """Provide a mock Kafka producer for testing."""
    producer = AsyncMock(spec=AIOKafkaProducer)
    producer.send_and_wait = AsyncMock()
    return producer


@pytest.fixture
def mock_http_session() -> AsyncMock:
    """Provide a mock HTTP session for testing."""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


@pytest.fixture
def mock_fetch_content_success(sample_text: str) -> AsyncMock:
    """Provide a mock fetch_content function that succeeds."""

    async def fetch_content(
        session: aiohttp.ClientSession, storage_id: str, essay_id: str
    ) -> Optional[str]:
        return sample_text

    return AsyncMock(side_effect=fetch_content)


@pytest.fixture
def mock_fetch_content_failure() -> AsyncMock:
    """Provide a mock fetch_content function that fails."""

    async def fetch_content(
        session: aiohttp.ClientSession, storage_id: str, essay_id: str
    ) -> Optional[str]:
        return None

    return AsyncMock(side_effect=fetch_content)


@pytest.fixture
def mock_store_content_success(sample_storage_id: str) -> AsyncMock:
    """Provide a mock store_content function that succeeds."""

    async def store_content(
        session: aiohttp.ClientSession, text_content: str, essay_id: str
    ) -> Optional[str]:
        return f"corrected_{sample_storage_id}"

    return AsyncMock(side_effect=store_content)


@pytest.fixture
def mock_store_content_failure() -> AsyncMock:
    """Provide a mock store_content function that fails."""

    async def store_content(
        session: aiohttp.ClientSession, text_content: str, essay_id: str
    ) -> Optional[str]:
        return None

    return AsyncMock(side_effect=store_content)


@pytest.fixture
def mock_spell_check_success(corrected_text: str) -> AsyncMock:
    """Provide a mock spell_check function that succeeds."""

    async def spell_check(text: str, essay_id: str) -> Tuple[str, int]:
        # Count corrections made
        corrections = text.count("tset") + text.count("teh") + text.count("recieve")
        return corrected_text, corrections

    return AsyncMock(side_effect=spell_check)


@pytest.fixture
def mock_spell_check_failure() -> AsyncMock:
    """Provide a mock spell_check function that raises an exception."""

    async def spell_check(text: str, essay_id: str) -> Tuple[str, int]:
        raise Exception("Spell check service unavailable")

    return AsyncMock(side_effect=spell_check)


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

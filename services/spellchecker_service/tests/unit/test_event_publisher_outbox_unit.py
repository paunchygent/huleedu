"""
Unit tests for DefaultSpellcheckEventPublisher with outbox pattern integration.

Tests focus on verifying the correct interaction with the outbox manager
for Spellchecker Service event publishing, following the TRUE OUTBOX PATTERN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import SpellcheckResultDataV1
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage

from services.spellchecker_service.config import Settings
from services.spellchecker_service.implementations.event_publisher_impl import DefaultSpellcheckEventPublisher
from services.spellchecker_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with configured topics."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "spell-checker-service"
    return settings


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Mock OutboxManager for testing using protocol-based mocking."""
    return AsyncMock(spec=OutboxManager)


@pytest.fixture
def event_publisher(
    test_settings: Settings,
    mock_outbox_manager: AsyncMock,
) -> DefaultSpellcheckEventPublisher:
    """Create event publisher with mocked dependencies for TRUE OUTBOX PATTERN testing."""
    return DefaultSpellcheckEventPublisher(
        kafka_event_type="huleedu.essay.spellcheck.completed.v1",
        source_service_name="spell-checker-service", 
        kafka_output_topic="huleedu.essay.spellcheck.completed.v1",
        outbox_manager=mock_outbox_manager,
    )


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


@pytest.fixture
def sample_entity_id() -> str:
    """Sample entity ID for testing."""
    return "essay-123"


class TestDefaultSpellcheckEventPublisher:
    """Test DefaultSpellcheckEventPublisher behavior with outbox pattern."""

    async def test_publish_spellcheck_result_success(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify SpellcheckResultDataV1 event calls OutboxManager with correct parameters."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        storage_metadata = StorageReferenceMetadata(
            storage_id="corrected-text-456",
            content_type="text/plain",
            file_name="essay_123_corrected.txt",
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-123",
            storage_metadata=storage_metadata,
            corrections_made=3,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "spellcheck_job"
        assert call_args.kwargs["aggregate_id"] == sample_entity_id
        assert call_args.kwargs["event_type"] == "huleedu.essay.spellcheck.completed.v1"
        assert call_args.kwargs["topic"] == "huleedu.essay.spellcheck.completed.v1"

        # Verify envelope is passed directly with expected structure
        passed_envelope = call_args.kwargs["event_data"]
        assert isinstance(passed_envelope, EventEnvelope)
        assert passed_envelope.event_type == "huleedu.essay.spellcheck.completed.v1"
        assert passed_envelope.source_service == "spell-checker-service"
        assert passed_envelope.correlation_id == sample_correlation_id
        assert passed_envelope.data == event_data

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify that outbox storage failures are propagated as exceptions."""
        # Given
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Database connection lost")

        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-fail",
            storage_metadata=None,
            corrections_made=0,
        )

        # When/Then
        with pytest.raises(Exception) as exc_info:
            await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        assert "Database connection lost" in str(exc_info.value)
        mock_outbox_manager.publish_to_outbox.assert_called_once()

    async def test_envelope_structure_and_metadata_handling(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify envelope structure and metadata are properly handled through DI contract."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-passthrough",
            storage_metadata=None,
            corrections_made=0,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify envelope structure passed to OutboxManager
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        passed_envelope = call_args.kwargs["event_data"]
        assert isinstance(passed_envelope, EventEnvelope)

        # Verify envelope contains expected data structure
        assert passed_envelope.event_type == "huleedu.essay.spellcheck.completed.v1"
        assert passed_envelope.source_service == "spell-checker-service"
        assert passed_envelope.correlation_id == sample_correlation_id
        assert passed_envelope.data == event_data

        # Verify metadata structure (behavior, not implementation details)
        assert passed_envelope.metadata is not None
        assert passed_envelope.metadata["partition_key"] == sample_entity_id

    async def test_event_envelope_serialization(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify event envelope is properly serialized with model_dump(mode='json')."""
        # Given
        timestamp = datetime.now(timezone.utc)

        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=timestamp,
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=timestamp,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-serial",
            storage_metadata=None,
            corrections_made=5,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify OutboxManager was called and extract envelope data
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        passed_envelope = call_args.kwargs["event_data"]

        # Convert envelope to dict to check serialization
        envelope_data = passed_envelope.model_dump(mode="json")

        # Verify timestamps are serialized as ISO strings
        assert isinstance(envelope_data["event_timestamp"], str)
        assert isinstance(envelope_data["data"]["timestamp"], str)

        # Verify UUIDs are serialized as strings
        assert isinstance(envelope_data["correlation_id"], str)
        assert envelope_data["correlation_id"] == str(sample_correlation_id)

        # Verify the entire structure is JSON-serializable
        json_str = json.dumps(envelope_data)
        assert json_str  # Should not raise exception

    async def test_partition_key_added_to_metadata(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify partition key is added to envelope metadata for Kafka routing."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-partition",
            storage_metadata=None,
            corrections_made=2,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify partition key was added to envelope metadata
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        passed_envelope = call_args.kwargs["event_data"]
        assert passed_envelope.metadata is not None
        assert passed_envelope.metadata["partition_key"] == sample_entity_id
"""
Unit tests for DefaultSpellcheckEventPublisher with outbox pattern integration.

Tests focus on verifying the correct interaction with the outbox manager
for Spellchecker Service event publishing, following the TRUE OUTBOX PATTERN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckPhaseCompletedV1,
    SpellcheckResultDataV1,
    SpellcheckResultV1,
)
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage, ProcessingStatus

from services.spellchecker_service.implementations.event_publisher_impl import (
    DefaultSpellcheckEventPublisher,
)
from services.spellchecker_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Mock OutboxManager for testing using protocol-based mocking."""
    return AsyncMock(spec=OutboxManager)


@pytest.fixture
def event_publisher(
    mock_outbox_manager: AsyncMock,
) -> DefaultSpellcheckEventPublisher:
    """Create event publisher with mocked dependencies for TRUE OUTBOX PATTERN testing."""
    return DefaultSpellcheckEventPublisher(
        source_service_name="spell-checker-service",
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
    """Test DefaultSpellcheckEventPublisher behavior with dual event outbox pattern."""

    async def test_publish_spellcheck_result_dual_events(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify SpellcheckResultDataV1 publishes both thin and rich events to outbox."""
        # Given
        from common_core.domain_enums import ContentType
        
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-456",
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        storage_metadata = StorageReferenceMetadata(
            references={
                ContentType.CORRECTED_TEXT: {"default": "corrected-text-456"}
            }
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-456",
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-123",
            storage_metadata=storage_metadata,
            corrections_made=3,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify TWO events were published to outbox
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Check thin event (first call)
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        assert thin_call.kwargs["aggregate_type"] == "spellcheck_job"
        assert thin_call.kwargs["aggregate_id"] == sample_entity_id
        assert thin_call.kwargs["event_type"] == "SpellcheckPhaseCompletedV1"
        assert thin_call.kwargs["topic"] == topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
        
        thin_envelope = thin_call.kwargs["event_data"]
        assert isinstance(thin_envelope, EventEnvelope)
        assert thin_envelope.event_type == "SpellcheckPhaseCompletedV1"
        assert thin_envelope.source_service == "spell-checker-service"
        assert thin_envelope.correlation_id == sample_correlation_id
        assert isinstance(thin_envelope.data, SpellcheckPhaseCompletedV1)
        assert thin_envelope.data.entity_id == sample_entity_id
        assert thin_envelope.data.batch_id == "batch-456"
        assert thin_envelope.data.status == ProcessingStatus.COMPLETED
        assert thin_envelope.data.corrected_text_storage_id == "corrected-text-456"
        
        # Check rich event (second call)
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        assert rich_call.kwargs["aggregate_type"] == "spellcheck_job"
        assert rich_call.kwargs["aggregate_id"] == sample_entity_id
        assert rich_call.kwargs["event_type"] == "SpellcheckResultV1"
        assert rich_call.kwargs["topic"] == topic_name(ProcessingEvent.SPELLCHECK_RESULTS)
        
        rich_envelope = rich_call.kwargs["event_data"]
        assert isinstance(rich_envelope, EventEnvelope)
        assert rich_envelope.event_type == "SpellcheckResultV1"
        assert rich_envelope.source_service == "spell-checker-service"
        assert rich_envelope.correlation_id == sample_correlation_id
        assert isinstance(rich_envelope.data, SpellcheckResultV1)
        assert rich_envelope.data.entity_id == sample_entity_id
        assert rich_envelope.data.corrections_made == 3
        assert rich_envelope.data.corrected_text_storage_id == "corrected-text-456"

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify that outbox storage failures are propagated as exceptions."""
        # Given - first outbox call (thin event) fails
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

        # When/Then - Exception should be raised on first outbox call
        with pytest.raises(Exception) as exc_info:
            await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        assert "Database connection lost" in str(exc_info.value)
        mock_outbox_manager.publish_to_outbox.assert_called_once()  # Only thin event attempted

    async def test_envelope_structure_and_metadata_handling(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify envelope structure and metadata are properly handled for both events."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-789",
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-789",
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-passthrough",
            storage_metadata=None,
            corrections_made=0,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify TWO envelopes were passed to OutboxManager
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Check thin event envelope
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        thin_envelope = thin_call.kwargs["event_data"]
        assert isinstance(thin_envelope, EventEnvelope)
        assert thin_envelope.event_type == "SpellcheckPhaseCompletedV1"
        assert thin_envelope.source_service == "spell-checker-service"
        assert thin_envelope.correlation_id == sample_correlation_id
        assert isinstance(thin_envelope.data, SpellcheckPhaseCompletedV1)
        assert thin_envelope.metadata is not None
        assert thin_envelope.metadata["partition_key"] == sample_entity_id
        
        # Check rich event envelope
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        rich_envelope = rich_call.kwargs["event_data"]
        assert isinstance(rich_envelope, EventEnvelope)
        assert rich_envelope.event_type == "SpellcheckResultV1"
        assert rich_envelope.source_service == "spell-checker-service"
        assert rich_envelope.correlation_id == sample_correlation_id
        assert isinstance(rich_envelope.data, SpellcheckResultV1)
        assert rich_envelope.metadata is not None
        assert rich_envelope.metadata["partition_key"] == sample_entity_id

    async def test_event_envelope_serialization(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify both event envelopes are properly serialized with model_dump(mode='json')."""
        # Given
        timestamp = datetime.now(timezone.utc)

        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-serial",
            timestamp=timestamp,
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-serial",
            timestamp=timestamp,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-serial",
            storage_metadata=None,
            corrections_made=5,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify both envelopes are serializable
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Check thin event serialization
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        thin_envelope = thin_call.kwargs["event_data"]
        thin_envelope_data = thin_envelope.model_dump(mode="json")
        assert isinstance(thin_envelope_data["event_timestamp"], str)
        assert isinstance(thin_envelope_data["data"]["timestamp"], str)
        assert isinstance(thin_envelope_data["correlation_id"], str)
        assert thin_envelope_data["correlation_id"] == str(sample_correlation_id)
        json_thin = json.dumps(thin_envelope_data)
        assert json_thin  # Should not raise exception
        
        # Check rich event serialization
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        rich_envelope = rich_call.kwargs["event_data"]
        rich_envelope_data = rich_envelope.model_dump(mode="json")
        assert isinstance(rich_envelope_data["event_timestamp"], str)
        assert isinstance(rich_envelope_data["data"]["timestamp"], str)
        assert isinstance(rich_envelope_data["correlation_id"], str)
        assert rich_envelope_data["correlation_id"] == str(sample_correlation_id)
        json_rich = json.dumps(rich_envelope_data)
        assert json_rich  # Should not raise exception

    async def test_partition_key_added_to_metadata(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify partition key is added to both event envelope metadata for Kafka routing."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-partition",
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-partition",
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-partition",
            storage_metadata=None,
            corrections_made=2,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify partition key was added to both envelopes
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Check thin event partition key
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        thin_envelope = thin_call.kwargs["event_data"]
        assert thin_envelope.metadata is not None
        assert thin_envelope.metadata["partition_key"] == sample_entity_id
        
        # Check rich event partition key
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        rich_envelope = rich_call.kwargs["event_data"]
        assert rich_envelope.metadata is not None
        assert rich_envelope.metadata["partition_key"] == sample_entity_id

    async def test_failed_spellcheck_dual_events(
        self,
        event_publisher: DefaultSpellcheckEventPublisher,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_entity_id: str,
    ) -> None:
        """Verify failed spellcheck publishes both events with correct failure status."""
        # Given - failed spellcheck with error info
        system_metadata = SystemProcessingMetadata(
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-fail",
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.FAILED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
            error_info={"error_code": "SPELLCHECK_FAILED", "error_message": "Processing failed"}
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=sample_entity_id,
            entity_type="essay",
            parent_id="batch-fail",
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECK_FAILED,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-fail",
            storage_metadata=None,
            corrections_made=0,
        )

        # When
        await event_publisher.publish_spellcheck_result(event_data, sample_correlation_id)

        # Then - Verify both events are published with failure status
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Check thin event has failure status
        thin_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        thin_envelope = thin_call.kwargs["event_data"]
        assert isinstance(thin_envelope.data, SpellcheckPhaseCompletedV1)
        assert thin_envelope.data.status == ProcessingStatus.FAILED
        assert thin_envelope.data.error_code is not None
        assert "SPELLCHECK_FAILED" in thin_envelope.data.error_code
        assert thin_envelope.data.corrected_text_storage_id is None
        
        # Check rich event has failure status
        rich_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        rich_envelope = rich_call.kwargs["event_data"]
        assert isinstance(rich_envelope.data, SpellcheckResultV1)
        assert rich_envelope.data.status == EssayStatus.SPELLCHECK_FAILED
        assert rich_envelope.data.corrections_made == 0
        assert rich_envelope.data.corrected_text_storage_id is None

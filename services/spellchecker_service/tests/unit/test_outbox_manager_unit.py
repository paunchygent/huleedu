"""
Unit tests for OutboxManager error handling scenarios.

Focuses on defensive error handling paths and graceful degradation
following TRUE OUTBOX PATTERN architectural principles.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckPhaseCompletedV1,
    SpellcheckResultDataV1,
    SpellcheckResultV1,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage, ProcessingStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.spellchecker_service.config import Settings
from services.spellchecker_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def test_settings() -> Settings:
    """Test settings."""
    settings: Mock = Mock(spec=Settings)
    settings.SERVICE_NAME = "spell-checker-service"
    return settings


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def sample_event_envelope() -> EventEnvelope:
    """Sample event envelope for testing."""
    correlation_id: UUID = uuid4()
    entity_id: str = "essay-test-123"

    # Create properly typed event data
    system_metadata = SystemProcessingMetadata(
        entity_id=entity_id,
        entity_type="essay",
        parent_id=None,
        timestamp=datetime.now(timezone.utc),
        processing_stage=ProcessingStage.COMPLETED,
        event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
    )

    event_data = SpellcheckResultDataV1(
        event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
        entity_id=entity_id,
        entity_type="essay",
        parent_id=None,
        timestamp=datetime.now(timezone.utc),
        status=EssayStatus.SPELLCHECKED_SUCCESS,
        system_metadata=system_metadata,
        original_text_storage_id="original-text-outbox-test",
        storage_metadata=None,
        corrections_made=2,
    )

    return EventEnvelope(
        event_type="huleedu.essay.spellcheck.completed.v1",
        source_service="spell-checker-service",
        correlation_id=correlation_id,
        data=event_data,
    )


class TestOutboxManagerErrorHandling:
    """Test OutboxManager error handling scenarios."""

    async def test_unconfigured_repository_raises_error(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that None repository raises proper HuleEduError."""
        # Given
        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=None,  # type: ignore
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="spellcheck_job",
                aggregate_id="essay-test-123",
                event_type="huleedu.essay.spellcheck.completed.v1",
                event_data=sample_event_envelope,
                topic="huleedu.essay.spellcheck.completed.v1",
            )

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "spellchecker_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Outbox repository not configured" in error_detail.message
        assert error_detail.correlation_id == sample_event_envelope.correlation_id

    async def test_repository_exception_wrapped_with_correlation_id(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test repository exceptions are wrapped with proper correlation ID."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Database connection lost")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="spellcheck_job",
                aggregate_id="essay-test-456",
                event_type="huleedu.essay.spellcheck.completed.v1",
                event_data=sample_event_envelope,
                topic="huleedu.essay.spellcheck.completed.v1",
            )

        # Verify wrapped error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "spellchecker_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Failed to store event in outbox" in error_detail.message
        assert error_detail.correlation_id == sample_event_envelope.correlation_id

    async def test_correlation_id_extraction_from_dict_event_data(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test correlation ID extraction from dict event data."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Test exception")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        test_correlation_id: UUID = uuid4()
        dict_event_data: dict[str, Any] = {
            "correlation_id": str(test_correlation_id),
            "data": "test",
        }

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="spellcheck_job",
                aggregate_id="essay-test-789",
                event_type="huleedu.essay.spellcheck.completed.v1",
                event_data=dict_event_data,
                topic="huleedu.essay.spellcheck.completed.v1",
            )

        # Verify correlation ID extracted from dict
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.correlation_id == test_correlation_id

    async def test_correlation_id_fallback_for_invalid_data(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test correlation ID fallback when extraction fails."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.side_effect = Exception("Test exception")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        invalid_event_data: dict[str, str] = {"correlation_id": "invalid-uuid-format"}

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="spellcheck_job",
                aggregate_id="essay-test-999",
                event_type="huleedu.essay.spellcheck.completed.v1",
                event_data=invalid_event_data,
                topic="huleedu.essay.spellcheck.completed.v1",
            )

        # Verify fallback to default UUID
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.correlation_id == UUID("00000000-0000-0000-0000-000000000000")

    async def test_redis_notification_failure_graceful_degradation(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that Redis notification failures don't break outbox storage."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        # Make Redis fail
        mock_redis_client.lpush.side_effect = Exception("Redis connection lost")

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When - Should complete successfully despite Redis failure
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id="essay-test-graceful",
            event_type="huleedu.essay.spellcheck.completed.v1",
            event_data=sample_event_envelope,
            topic="huleedu.essay.spellcheck.completed.v1",
        )

        # Then - Verify outbox storage succeeded despite Redis failure
        mock_repository.add_event.assert_called_once()
        mock_redis_client.lpush.assert_called_once()

    async def test_successful_outbox_write_with_redis_notification(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test successful outbox write with Redis notification."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        expected_outbox_id = uuid4()
        mock_repository.add_event.return_value = expected_outbox_id

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id="essay-test-success",
            event_type="huleedu.essay.spellcheck.completed.v1",
            event_data=sample_event_envelope,
            topic="huleedu.essay.spellcheck.completed.v1",
        )

        # Then
        # Verify repository was called with correct parameters
        mock_repository.add_event.assert_called_once()
        call_args = mock_repository.add_event.call_args
        assert call_args.kwargs["aggregate_type"] == "spellcheck_job"
        assert call_args.kwargs["aggregate_id"] == "essay-test-success"
        assert call_args.kwargs["event_type"] == "huleedu.essay.spellcheck.completed.v1"
        assert call_args.kwargs["topic"] == "huleedu.essay.spellcheck.completed.v1"

        # Verify event data was serialized correctly
        event_data = call_args.kwargs["event_data"]
        assert isinstance(event_data, dict)
        assert event_data["event_type"] == "huleedu.essay.spellcheck.completed.v1"
        assert event_data["source_service"] == "spell-checker-service"

        # Verify Redis notification was sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:spell-checker-service", "1")

    async def test_custom_partition_key_handling(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test that custom partition key is properly passed through."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        correlation_id = uuid4()
        entity_id = "essay-test-partition"

        system_metadata = SystemProcessingMetadata(
            entity_id=entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
        )

        event_data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=entity_id,
            entity_type="essay",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=system_metadata,
            original_text_storage_id="original-text-partition",
            storage_metadata=None,
            corrections_made=1,
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="huleedu.essay.spellcheck.completed.v1",
            source_service="spell-checker-service",
            correlation_id=correlation_id,
            data=event_data,
            metadata={"partition_key": "custom-key-123"},
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=entity_id,
            event_type="huleedu.essay.spellcheck.completed.v1",
            event_data=envelope,
            topic="huleedu.essay.spellcheck.completed.v1",
        )

        # Then - Verify custom key was extracted from metadata and passed to repository
        mock_repository.add_event.assert_called_once()
        call_args = mock_repository.add_event.call_args
        # OutboxManager extracts partition_key from envelope.metadata and passes it as event_key
        assert call_args.kwargs["event_key"] == "custom-key-123"

    async def test_event_serialization_with_json_mode(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that event envelopes are properly serialized with model_dump(mode='json')."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id="essay-test-serialization",
            event_type="huleedu.essay.spellcheck.completed.v1",
            event_data=sample_event_envelope,
            topic="huleedu.essay.spellcheck.completed.v1",
        )

        # Then - Verify event was properly serialized
        mock_repository.add_event.assert_called_once()
        call_args = mock_repository.add_event.call_args
        event_data = call_args.kwargs["event_data"]

        # Should be a dict after serialization
        assert isinstance(event_data, dict)

        # Check that timestamps are serialized as strings
        assert isinstance(event_data["event_timestamp"], str)
        assert isinstance(event_data["data"]["timestamp"], str)

        # Check that UUIDs are serialized as strings
        assert isinstance(event_data["correlation_id"], str)

        # Verify structure matches envelope
        assert event_data["event_type"] == sample_event_envelope.event_type
        assert event_data["source_service"] == sample_event_envelope.source_service

    async def test_invalid_event_data_type_raises_error(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test that non-Pydantic event data raises ValueError."""
        # Given
        mock_repository: AsyncMock = AsyncMock()

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        invalid_event_data = "not-a-pydantic-model"

        # When/Then
        with pytest.raises(HuleEduError) as exc_info:
            await outbox_manager.publish_to_outbox(
                aggregate_type="spellcheck_job",
                aggregate_id="essay-test-invalid",
                event_type="huleedu.essay.spellcheck.completed.v1",
                event_data=invalid_event_data,
                topic="huleedu.essay.spellcheck.completed.v1",
            )

        # Verify error details indicate invalid event data
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "spellchecker_service"
        assert error_detail.operation == "publish_to_outbox"
        assert "Failed to store event in outbox" in error_detail.message

    async def test_dual_event_outbox_storage(
        self,
        test_settings: Settings,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test that outbox manager can handle both thin and rich spellcheck events."""
        # Given
        mock_repository: AsyncMock = AsyncMock()
        mock_repository.add_event.return_value = uuid4()

        outbox_manager: OutboxManager = OutboxManager(
            outbox_repository=mock_repository,
            redis_client=mock_redis_client,
            settings=test_settings,
        )

        correlation_id = uuid4()
        entity_id = "essay-dual-test"
        batch_id = "batch-dual-test"
        corrected_storage_id = "corrected-dual-test"

        # Create thin event (SpellcheckPhaseCompletedV1)
        thin_event = SpellcheckPhaseCompletedV1(
            entity_id=entity_id,
            batch_id=batch_id,
            correlation_id=str(correlation_id),
            status=ProcessingStatus.COMPLETED,
            corrected_text_storage_id=corrected_storage_id,
            error_code=None,
            processing_duration_ms=150,
            timestamp=datetime.now(timezone.utc),
        )

        thin_envelope: EventEnvelope = EventEnvelope(
            event_type="SpellcheckPhaseCompletedV1",
            source_service="spell-checker-service",
            correlation_id=correlation_id,
            data=thin_event,
            metadata={"partition_key": entity_id},
        )

        # Create rich event (SpellcheckResultV1)
        from common_core.events.spellcheck_models import SpellcheckMetricsV1

        rich_system_metadata = SystemProcessingMetadata(
            entity_id=entity_id,
            entity_type="essay",
            parent_id=batch_id,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.SPELLCHECK_RESULTS.value,
        )

        rich_event = SpellcheckResultV1(
            event_name=ProcessingEvent.SPELLCHECK_RESULTS,
            entity_id=entity_id,
            entity_type="essay",
            parent_id=batch_id,
            timestamp=datetime.now(timezone.utc),
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=rich_system_metadata,
            correlation_id=str(correlation_id),
            corrections_made=5,
            correction_metrics=SpellcheckMetricsV1(
                total_corrections=5,
                l2_dictionary_corrections=3,
                spellchecker_corrections=2,
                word_count=100,
                correction_density=5.0,
            ),
            original_text_storage_id="original-dual-test",
            corrected_text_storage_id=corrected_storage_id,
            processing_duration_ms=150,
            processor_version="pyspellchecker_1.0_L2_swedish",
        )

        rich_envelope: EventEnvelope = EventEnvelope(
            event_type="SpellcheckResultV1",
            source_service="spell-checker-service",
            correlation_id=correlation_id,
            data=rich_event,
            metadata={"partition_key": entity_id},
        )

        # When - Store thin event
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=entity_id,
            event_type="SpellcheckPhaseCompletedV1",
            event_data=thin_envelope,
            topic=topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
        )

        # Store rich event
        await outbox_manager.publish_to_outbox(
            aggregate_type="spellcheck_job",
            aggregate_id=entity_id,
            event_type="SpellcheckResultV1",
            event_data=rich_envelope,
            topic=topic_name(ProcessingEvent.SPELLCHECK_RESULTS),
        )

        # Then - Verify both events were stored
        assert mock_repository.add_event.call_count == 2

        # Check thin event storage
        thin_call = mock_repository.add_event.call_args_list[0]
        assert thin_call.kwargs["event_type"] == "SpellcheckPhaseCompletedV1"
        assert thin_call.kwargs["topic"] == topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
        assert thin_call.kwargs["aggregate_id"] == entity_id
        assert thin_call.kwargs["event_key"] == entity_id  # From partition_key

        # Check rich event storage
        rich_call = mock_repository.add_event.call_args_list[1]
        assert rich_call.kwargs["event_type"] == "SpellcheckResultV1"
        assert rich_call.kwargs["topic"] == topic_name(ProcessingEvent.SPELLCHECK_RESULTS)
        assert rich_call.kwargs["aggregate_id"] == entity_id
        assert rich_call.kwargs["event_key"] == entity_id  # From partition_key

        # Verify Redis notifications were sent for both events
        assert mock_redis_client.lpush.call_count == 2

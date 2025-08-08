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
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1, GradeProjectionSummary
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.error_handling import HuleEduError

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.outbox_manager import OutboxManager


def create_test_grade_projections(essay_ids: list[str] | None = None) -> GradeProjectionSummary:
    """Create test grade projections for unit tests."""
    if essay_ids is None:
        essay_ids = []

    return GradeProjectionSummary(
        projections_available=True,
        primary_grades={eid: "B" for eid in essay_ids},
        confidence_labels={eid: "HIGH" for eid in essay_ids},
        confidence_scores={eid: 0.85 for eid in essay_ids},
    )


@pytest.fixture
def test_settings() -> Settings:
    """Test settings."""
    settings: Mock = Mock(spec=Settings)
    settings.SERVICE_NAME = "cj_assessment_service"
    return settings


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Mock Redis client."""
    return AsyncMock()


@pytest.fixture
def sample_event_envelope() -> EventEnvelope:
    """Sample event envelope for testing."""
    correlation_id: UUID = uuid4()
    batch_id: UUID = uuid4()

    # Create properly typed event data
    system_metadata = SystemProcessingMetadata(
        entity_id=str(batch_id),
        entity_type="batch",
        parent_id=None,
        timestamp=datetime.now(timezone.utc),
        processing_stage=ProcessingStage.COMPLETED,
        event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
    )

    event_data = CJAssessmentCompletedV1(
        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
        entity_id=str(batch_id),
        entity_type="batch",
        parent_id=None,
        timestamp=datetime.now(timezone.utc),
        status=BatchStatus.COMPLETED_SUCCESSFULLY,
        system_metadata=system_metadata,
        cj_assessment_job_id="cj-job-test-123",
        rankings=[{"els_essay_id": "essay-test-1", "rank": 1, "score": 0.85}],
        grade_projections_summary=create_test_grade_projections(["essay-test-1"]),
    )

    return EventEnvelope(
        event_type="processing.cj.assessment.completed.v1",
        source_service="cj_assessment_service",
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
                aggregate_type="cj_batch",
                aggregate_id="test-123",
                event_type="processing.cj.assessment.completed.v1",
                event_data=sample_event_envelope,
                topic="processing.cj.assessment.completed.v1",
            )

        # Verify error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "cj_assessment_service"
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
                aggregate_type="cj_batch",
                aggregate_id="test-456",
                event_type="processing.cj.assessment.completed.v1",
                event_data=sample_event_envelope,
                topic="processing.cj.assessment.completed.v1",
            )

        # Verify wrapped error details
        error_detail: Any = exc_info.value.error_detail
        assert error_detail.service == "cj_assessment_service"
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
                aggregate_type="cj_batch",
                aggregate_id="test-789",
                event_type="processing.cj.assessment.completed.v1",
                event_data=dict_event_data,
                topic="processing.cj.assessment.completed.v1",
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
                aggregate_type="cj_batch",
                aggregate_id="test-999",
                event_type="processing.cj.assessment.completed.v1",
                event_data=invalid_event_data,
                topic="processing.cj.assessment.completed.v1",
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
        # Note: publish_to_outbox returns None, not the outbox_id
        await outbox_manager.publish_to_outbox(
            aggregate_type="cj_batch",
            aggregate_id="test-graceful",
            event_type="processing.cj.assessment.completed.v1",
            event_data=sample_event_envelope,
            topic="processing.cj.assessment.completed.v1",
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
        # Note: publish_to_outbox returns None, not the outbox_id
        await outbox_manager.publish_to_outbox(
            aggregate_type="cj_batch",
            aggregate_id="test-success",
            event_type="processing.cj.assessment.completed.v1",
            event_data=sample_event_envelope,
            topic="processing.cj.assessment.completed.v1",
        )

        # Then

        # Verify repository was called with correct parameters
        mock_repository.add_event.assert_called_once()
        call_args = mock_repository.add_event.call_args
        assert call_args.kwargs["aggregate_type"] == "cj_batch"
        assert call_args.kwargs["aggregate_id"] == "test-success"
        assert call_args.kwargs["event_type"] == "processing.cj.assessment.completed.v1"
        assert call_args.kwargs["topic"] == "processing.cj.assessment.completed.v1"

        # Verify event data was serialized correctly
        event_data = call_args.kwargs["event_data"]
        assert isinstance(event_data, dict)
        assert event_data["event_type"] == "processing.cj.assessment.completed.v1"
        assert event_data["source_service"] == "cj_assessment_service"

        # Verify Redis notification was sent
        mock_redis_client.lpush.assert_called_once_with("outbox:wake:cj_assessment_service", "1")

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
        batch_id = uuid4()

        system_metadata = SystemProcessingMetadata(
            entity_id=str(batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )

        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id=str(batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-partition",
            rankings=[],
            grade_projections_summary=create_test_grade_projections(),
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=correlation_id,
            data=event_data,
            metadata={"partition_key": "custom-key-123"},
        )

        # When
        await outbox_manager.publish_to_outbox(
            aggregate_type="cj_batch",
            aggregate_id=str(batch_id),
            event_type="processing.cj.assessment.completed.v1",
            event_data=envelope,
            topic="processing.cj.assessment.completed.v1",
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
            aggregate_type="cj_batch",
            aggregate_id="test-serialization",
            event_type="processing.cj.assessment.completed.v1",
            event_data=sample_event_envelope,
            topic="processing.cj.assessment.completed.v1",
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

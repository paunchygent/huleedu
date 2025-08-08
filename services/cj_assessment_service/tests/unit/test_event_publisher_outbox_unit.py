"""
Unit tests for CJEventPublisherImpl with outbox pattern integration.

Tests focus on verifying the correct interaction with the outbox manager
for CJ Assessment event publishing, following the TRUE OUTBOX PATTERN.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1, CJAssessmentFailedV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.event_publisher_impl import CJEventPublisherImpl
from services.cj_assessment_service.implementations.outbox_manager import OutboxManager


@pytest.fixture
def test_settings() -> Settings:
    """Test settings with configured topics."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "cj_assessment_service"
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "processing.cj.assessment.completed.v1"
    settings.CJ_ASSESSMENT_FAILED_TOPIC = "processing.cj.assessment.failed.v1"
    return settings


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Mock OutboxManager for testing using protocol-based mocking."""
    return AsyncMock(spec=OutboxManager)


@pytest.fixture
def event_publisher(
    test_settings: Settings,
    mock_outbox_manager: AsyncMock,
) -> CJEventPublisherImpl:
    """Create event publisher with mocked dependencies for TRUE OUTBOX PATTERN testing."""
    return CJEventPublisherImpl(
        outbox_manager=mock_outbox_manager,
        settings=test_settings,
    )


@pytest.fixture
def sample_correlation_id() -> UUID:
    """Sample correlation ID for testing."""
    return uuid4()


@pytest.fixture
def sample_batch_id() -> UUID:
    """Sample batch ID for testing."""
    return uuid4()


class TestCJEventPublisherImpl:
    """Test CJEventPublisherImpl behavior with outbox pattern."""

    async def test_publish_assessment_completed_success(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify CJAssessmentCompletedV1 event calls OutboxManager with correct parameters."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )

        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-unit-001",
            rankings=[
                {"els_essay_id": "essay-001", "rank": 1, "score": 0.95},
                {"els_essay_id": "essay-002", "rank": 2, "score": 0.88},
                {"els_essay_id": "essay-003", "rank": 3, "score": 0.76},
            ],
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_assessment_completed(envelope, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "cj_batch"
        assert call_args.kwargs["aggregate_id"] == str(sample_batch_id)
        assert call_args.kwargs["event_type"] == "processing.cj.assessment.completed.v1"
        assert call_args.kwargs["topic"] == "processing.cj.assessment.completed.v1"

        # Verify envelope is passed directly (not envelope structure in event_data)
        passed_envelope = call_args.kwargs["event_data"]
        assert passed_envelope == envelope
        assert passed_envelope.event_type == "processing.cj.assessment.completed.v1"
        assert passed_envelope.source_service == "cj_assessment_service"
        assert passed_envelope.correlation_id == sample_correlation_id
        assert passed_envelope.data == event_data

    async def test_publish_assessment_failed_success(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify CJAssessmentFailedV1 event calls OutboxManager with correct parameters."""
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.FAILED,
            event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
            error_info={
                "error": "LLM provider timeout",
                "timeout_seconds": 60,
                "provider": "openai",
                "batch_size": 10,
            },
        )

        event_data = CJAssessmentFailedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.FAILED_CRITICALLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-unit-fail",
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.failed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_assessment_failed(envelope, sample_correlation_id)

        # Then - Verify OutboxManager.publish_to_outbox was called with correct parameters
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "cj_batch"
        assert call_args.kwargs["aggregate_id"] == str(sample_batch_id)
        assert call_args.kwargs["event_type"] == "processing.cj.assessment.failed.v1"
        assert call_args.kwargs["topic"] == "processing.cj.assessment.failed.v1"

        # Verify envelope is passed directly
        passed_envelope = call_args.kwargs["event_data"]
        assert passed_envelope == envelope
        assert passed_envelope.event_type == "processing.cj.assessment.failed.v1"
        assert passed_envelope.source_service == "cj_assessment_service"
        assert passed_envelope.correlation_id == sample_correlation_id
        assert passed_envelope.data == event_data

    async def test_outbox_failure_propagates_exception(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify that outbox storage failures are propagated as exceptions."""
        # Given
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Database connection lost")

        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )

        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-fail",
            rankings=[],
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
        )

        # When/Then
        with pytest.raises(Exception) as exc_info:
            await event_publisher.publish_assessment_completed(envelope, sample_correlation_id)

        assert "Database connection lost" in str(exc_info.value)
        mock_outbox_manager.publish_to_outbox.assert_called_once()

    async def test_envelope_passed_to_outbox_without_modification(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify that envelopes are passed to outbox manager without modification.

        Note: CJ Assessment Service receives pre-built envelopes from event processor,
        so trace context injection happens at event creation, not in the publisher.
        """
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )

        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-passthrough",
            rankings=[],
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
            metadata={"test_metadata": "preserved"},
        )

        # When
        await event_publisher.publish_assessment_completed(envelope, sample_correlation_id)

        # Then - Verify envelope passed directly to OutboxManager without modification
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify the exact same envelope object was passed
        passed_envelope = call_args.kwargs["event_data"]
        assert passed_envelope is envelope

        # Verify metadata was preserved
        assert passed_envelope.metadata == {"test_metadata": "preserved"}

    async def test_event_envelope_serialization(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify event envelope is properly serialized with model_dump(mode='json')."""
        # Given
        timestamp = datetime.now(timezone.utc)

        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=timestamp,
            processing_stage=ProcessingStage.FAILED,
            event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
            error_info={"error": "Invalid data format"},
        )

        event_data = CJAssessmentFailedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=timestamp,
            status=BatchStatus.FAILED_CRITICALLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-serial",
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.failed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
        )

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            await event_publisher.publish_assessment_failed(envelope, sample_correlation_id)

        # Then - Verify OutboxManager was called and extract envelope data
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        passed_envelope = call_args.kwargs["event_data"]

        # Convert envelope to dict to check serialization (envelope has model_dump method)
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

    async def test_both_event_types_use_consistent_patterns(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify all event publishing methods follow consistent patterns."""
        # Given
        timestamp = datetime.now(timezone.utc)

        # Type annotation for heterogeneous list of event publishing methods
        from typing import Callable

        events_to_test: list[tuple[Callable[..., Any], Any, str, str]] = [
            (
                event_publisher.publish_assessment_completed,
                EventEnvelope(
                    event_type="processing.cj.assessment.completed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=sample_correlation_id,
                    data=CJAssessmentCompletedV1(
                        event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                        entity_id=str(sample_batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=timestamp,
                        status=BatchStatus.COMPLETED_SUCCESSFULLY,
                        system_metadata=SystemProcessingMetadata(
                            entity_id=str(sample_batch_id),
                            entity_type="batch",
                            parent_id=None,
                            timestamp=timestamp,
                            processing_stage=ProcessingStage.COMPLETED,
                            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                        ),
                        cj_assessment_job_id="cj-job-1",
                        rankings=[{"els_essay_id": "essay-1", "rank": 1, "score": 0.90}],
                    ),
                ),
                "processing.cj.assessment.completed.v1",
                "cj_batch",
            ),
            (
                event_publisher.publish_assessment_failed,
                EventEnvelope(
                    event_type="processing.cj.assessment.failed.v1",
                    source_service="cj_assessment_service",
                    correlation_id=sample_correlation_id,
                    data=CJAssessmentFailedV1(
                        event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                        entity_id=str(sample_batch_id),
                        entity_type="batch",
                        parent_id=None,
                        timestamp=timestamp,
                        status=BatchStatus.FAILED_CRITICALLY,
                        system_metadata=SystemProcessingMetadata(
                            entity_id=str(sample_batch_id),
                            entity_type="batch",
                            parent_id=None,
                            timestamp=timestamp,
                            processing_stage=ProcessingStage.FAILED,
                            event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                        ),
                        cj_assessment_job_id="cj-job-2",
                    ),
                ),
                "processing.cj.assessment.failed.v1",
                "cj_batch",
            ),
        ]

        # When
        with patch("huleedu_service_libs.observability.inject_trace_context"):
            for (
                publish_method,
                envelope,
                expected_topic,
                expected_aggregate_type,
            ) in events_to_test:
                await publish_method(envelope, sample_correlation_id)

        # Then - Verify OutboxManager was called 2 times (once for each event)
        assert mock_outbox_manager.publish_to_outbox.call_count == 2

        # Get all call args to verify each call's consistency
        call_args_list = mock_outbox_manager.publish_to_outbox.call_args_list

        for i, (_, envelope, expected_topic, expected_aggregate_type) in enumerate(events_to_test):
            call_args = call_args_list[i]

            # All events should follow the same pattern
            assert call_args.kwargs["topic"] == expected_topic
            assert call_args.kwargs["event_type"] == expected_topic
            assert call_args.kwargs["aggregate_type"] == expected_aggregate_type
            assert call_args.kwargs["aggregate_id"] == str(sample_batch_id)

            # Verify envelope passed directly
            passed_envelope = call_args.kwargs["event_data"]
            assert passed_envelope == envelope
            assert passed_envelope.event_type == expected_topic
            assert passed_envelope.source_service == "cj_assessment_service"
            assert passed_envelope.correlation_id == sample_correlation_id

    async def test_custom_partition_key_from_metadata(
        self,
        event_publisher: CJEventPublisherImpl,
        mock_outbox_manager: AsyncMock,
        sample_correlation_id: UUID,
        sample_batch_id: UUID,
    ) -> None:
        """Verify envelope with custom partition key metadata is passed correctly.

        Note: The CJ Assessment Service publisher doesn't extract partition keys;
        that's handled by the OutboxManager which reads from envelope.metadata.
        """
        # Given
        system_metadata = SystemProcessingMetadata(
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )

        event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id=str(sample_batch_id),
            entity_type="batch",
            parent_id=None,
            timestamp=datetime.now(timezone.utc),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="cj-job-partition",
            rankings=[],
        )

        envelope: EventEnvelope = EventEnvelope(
            event_type="processing.cj.assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=sample_correlation_id,
            data=event_data,
            metadata={"partition_key": "custom-partition-key"},
        )

        # When
        await event_publisher.publish_assessment_completed(envelope, sample_correlation_id)

        # Then - Verify envelope with metadata was passed to OutboxManager
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify the envelope with partition_key metadata was passed
        passed_envelope = call_args.kwargs["event_data"]
        assert passed_envelope == envelope
        assert passed_envelope.metadata == {"partition_key": "custom-partition-key"}

        # The publisher doesn't extract event_key; OutboxManager handles that
        assert "event_key" not in call_args.kwargs

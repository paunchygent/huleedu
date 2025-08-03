"""
Unit tests for dual-event publishing pattern in BatchLifecyclePublisher.

Tests the clean separation of success (BatchEssaysReady) and error
(BatchValidationErrorsV1) events following structured error handling.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import (
    BatchErrorSummary,
    BatchEssaysReady,
    BatchValidationErrorsV1,
    EssayValidationError,
)
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail

from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)

# Rebuild models to resolve forward references
BatchValidationErrorsV1.model_rebuild()
EssayValidationError.model_rebuild()


@pytest.fixture
def mock_settings() -> Settings:
    """Provide mock settings."""
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "essay-lifecycle-service"
    return settings


@pytest.fixture
def mock_outbox_manager() -> AsyncMock:
    """Provide mock outbox manager."""
    return AsyncMock()


@pytest.fixture
def batch_lifecycle_publisher(
    mock_settings: Settings,
    mock_outbox_manager: AsyncMock,
) -> BatchLifecyclePublisher:
    """Provide BatchLifecyclePublisher instance."""
    return BatchLifecyclePublisher(
        settings=mock_settings,
        outbox_manager=mock_outbox_manager,
    )


class TestDualEventPublishing:
    """Test dual-event publishing pattern for clean separation of concerns."""

    async def test_publish_batch_essays_ready_success_only(
        self,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test publishing BatchEssaysReady event with only successful essays."""
        # Arrange
        batch_id = "test-batch-123"
        correlation_id = uuid4()

        ready_essays = [
            EssayProcessingInputRefV1(
                essay_id="essay-1",
                text_storage_id="storage-1",
                student_name="Student One",
            ),
            EssayProcessingInputRefV1(
                essay_id="essay-2",
                text_storage_id="storage-2",
                student_name="Student Two",
            ),
        ]

        event_data = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=ready_essays,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Write an essay",
            class_type="REGULAR",
            teacher_first_name="John",
            teacher_last_name="Doe",
        )

        # Act
        await batch_lifecycle_publisher.publish_batch_essays_ready(
            event_data=event_data,
            correlation_id=correlation_id,
        )

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["aggregate_id"] == batch_id
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        assert call_args.kwargs["topic"] == topic_name(ProcessingEvent.BATCH_ESSAYS_READY)

        # Verify event envelope contains correct data
        envelope = call_args.kwargs["event_data"]
        assert envelope.data == event_data
        assert envelope.source_service == "essay-lifecycle-service"
        assert envelope.correlation_id == correlation_id

    async def test_publish_batch_validation_errors_only(
        self,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test publishing BatchValidationErrorsV1 event for validation failures."""
        # Arrange
        batch_id = "test-batch-456"
        correlation_id = uuid4()

        failed_essays = [
            EssayValidationError(
                essay_id="essay-3",
                file_name="essay3.pdf",
                error_detail=ErrorDetail(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Invalid PDF format",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="file-service",
                    operation="validate_pdf",
                ),
            ),
            EssayValidationError(
                essay_id="essay-4",
                file_name="essay4.txt",
                error_detail=ErrorDetail(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="File too large",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="file-service",
                    operation="validate_size",
                ),
            ),
        ]

        event_data = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=failed_essays,
            error_summary=BatchErrorSummary(
                total_errors=2,
                error_categories={"validation": 2},
                critical_failure=False,
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        # Act
        await batch_lifecycle_publisher.publish_batch_validation_errors(
            event_data=event_data,
            correlation_id=correlation_id,
        )

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        assert call_args.kwargs["aggregate_type"] == "batch"
        assert call_args.kwargs["aggregate_id"] == batch_id
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)
        assert call_args.kwargs["topic"] == topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)

        # Verify event envelope contains correct data
        envelope = call_args.kwargs["event_data"]
        assert envelope.data == event_data
        assert envelope.source_service == "essay-lifecycle-service"
        assert envelope.correlation_id == correlation_id

    async def test_dual_event_publishing_separation(
        self,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that success and error events are published separately."""
        # Arrange
        batch_id = "test-batch-789"
        correlation_id = uuid4()

        # Success event data
        ready_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id="essay-5",
                    text_storage_id="storage-5",
                )
            ],
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Write an essay",
            class_type="GUEST",
        )

        # Error event data
        error_event = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-6",
                    file_name="essay6.doc",
                    error_detail=ErrorDetail(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Unsupported format",
                        correlation_id=correlation_id,
                        timestamp=datetime.now(UTC),
                        service="file-service",
                        operation="validate_format",
                    ),
                )
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=False,
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        # Act - Publish both events
        await batch_lifecycle_publisher.publish_batch_essays_ready(
            event_data=ready_event,
            correlation_id=correlation_id,
        )
        await batch_lifecycle_publisher.publish_batch_validation_errors(
            event_data=error_event,
            correlation_id=correlation_id,
        )

        # Assert - Both events published separately
        assert mock_outbox_manager.publish_to_outbox.call_count == 2

        # Verify first call (success event)
        first_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        assert first_call.kwargs["event_type"] == topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        assert first_call.kwargs["topic"] == topic_name(ProcessingEvent.BATCH_ESSAYS_READY)

        # Verify second call (error event)
        second_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        assert second_call.kwargs["event_type"] == topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)
        assert second_call.kwargs["topic"] == topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)

    async def test_critical_failure_flag_in_error_summary(
        self,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test critical failure flag when all essays fail validation."""
        # Arrange
        batch_id = "test-batch-critical"
        correlation_id = uuid4()

        # All essays failed - critical failure
        event_data = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=[
                EssayValidationError(
                    essay_id=f"essay-{i}",
                    file_name=f"essay{i}.pdf",
                    error_detail=ErrorDetail(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Corrupted file",
                        correlation_id=correlation_id,
                        timestamp=datetime.now(UTC),
                        service="file-service",
                        operation="validate_content",
                    ),
                )
                for i in range(5)
            ],
            error_summary=BatchErrorSummary(
                total_errors=5,
                error_categories={"validation": 5},
                critical_failure=True,  # All essays failed
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        # Act
        await batch_lifecycle_publisher.publish_batch_validation_errors(
            event_data=event_data,
            correlation_id=correlation_id,
        )

        # Assert
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args.kwargs["event_data"]

        # Verify critical failure flag is preserved
        assert envelope.data.error_summary.critical_failure is True
        assert envelope.data.error_summary.total_errors == 5

    @patch("common_core.event_enums.topic_name")
    async def test_uses_topic_name_function(
        self,
        mock_topic_name: Mock,
        batch_lifecycle_publisher: BatchLifecyclePublisher,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that topic_name() function is used instead of hardcoded strings."""
        # Arrange
        from common_core.event_enums import ProcessingEvent, topic_name

        mock_topic_name.return_value = topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)

        event_data = BatchValidationErrorsV1(
            batch_id="test-batch",
            failed_essays=[],
            error_summary=BatchErrorSummary(
                total_errors=0,
                error_categories={},
                critical_failure=False,
            ),
            correlation_id=uuid4(),
            metadata=SystemProcessingMetadata(
                entity_id="test-batch",
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        # Act
        await batch_lifecycle_publisher.publish_batch_validation_errors(
            event_data=event_data,
            correlation_id=uuid4(),
        )

        # Assert
        # topic_name is called twice: once for event_type in envelope, once for topic
        assert mock_topic_name.call_count == 2
        mock_topic_name.assert_any_call(ProcessingEvent.BATCH_VALIDATION_ERRORS)

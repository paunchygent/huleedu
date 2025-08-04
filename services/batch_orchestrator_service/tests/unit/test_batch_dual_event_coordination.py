"""
Unit tests for batch coordination with dual-event pattern.

Tests the clean separation of success (BatchEssaysReady) and error
(BatchValidationErrorsV1) event handling in BOS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
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
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import BatchStatus

from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.batch_validation_errors_handler import (
    BatchValidationErrorsHandler,
)

# Rebuild models to resolve forward references
BatchValidationErrorsV1.model_rebuild()
EssayValidationError.model_rebuild()


class TestBatchDualEventCoordination:
    """Test batch coordination with dual-event pattern."""

    @pytest.fixture
    def mock_batch_repo(self) -> AsyncMock:
        """Mock batch repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_event_publisher(self) -> AsyncMock:
        """Mock event publisher."""
        return AsyncMock()

    @pytest.fixture
    def batch_essays_ready_handler(
        self, mock_event_publisher: AsyncMock, mock_batch_repo: AsyncMock
    ) -> BatchEssaysReadyHandler:
        """Create batch essays ready handler."""
        return BatchEssaysReadyHandler(
            event_publisher=mock_event_publisher,
            batch_repo=mock_batch_repo,
        )

    @pytest.fixture
    def batch_validation_errors_handler(
        self, mock_event_publisher: AsyncMock, mock_batch_repo: AsyncMock
    ) -> BatchValidationErrorsHandler:
        """Create batch validation errors handler."""
        return BatchValidationErrorsHandler(
            event_publisher=mock_event_publisher,
            batch_repo=mock_batch_repo,
        )

    async def test_batch_essays_ready_stores_only_essays(
        self,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test that handler stores only what it needs: essays for processing."""
        # Arrange
        batch_id = "test-batch-456"
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

        # Event includes context for observability, but handler only needs essays
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
            essay_instructions="Essay prompt",
            class_type="GUEST",
        )

        envelope = EventEnvelope[BatchEssaysReady](
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Create mock message
        import json

        mock_msg = AsyncMock()
        mock_msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await batch_essays_ready_handler.handle_batch_essays_ready(mock_msg)

        # Assert - handler stores ONLY what it needs: batch_id and essays
        # The educational context is already stored during batch registration
        mock_batch_repo.store_batch_essays.assert_called_once_with(batch_id, ready_essays)

    async def test_validation_errors_updates_status_on_critical_failure(
        self,
        batch_validation_errors_handler: BatchValidationErrorsHandler,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test that handler updates batch status only on critical failure."""
        # Arrange
        batch_id = "test-batch-789"
        correlation_id = uuid4()

        failed_essays = [
            EssayValidationError(
                essay_id="essay-1",
                file_name="essay1.pdf",
                error_detail=ErrorDetail(
                    error_code=ErrorCode.VALIDATION_ERROR,
                    message="Invalid format",
                    correlation_id=correlation_id,
                    timestamp=datetime.now(UTC),
                    service="file-service",
                    operation="validate",
                ),
            ),
        ]

        # Critical failure - no essays succeeded
        event_data = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=failed_essays,
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=True,  # This is what matters for the handler
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type=topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS),
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Create mock message
        import json

        mock_msg = AsyncMock()
        mock_msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await batch_validation_errors_handler.handle_batch_validation_errors(mock_msg)

        # Assert - handler updates status ONLY because critical_failure=True
        mock_batch_repo.update_batch_status.assert_called_once_with(
            batch_id, BatchStatus.FAILED_CRITICALLY
        )

    async def test_validation_errors_no_action_on_partial_failure(
        self,
        batch_validation_errors_handler: BatchValidationErrorsHandler,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test that handler takes no action on partial failures."""
        # Arrange
        batch_id = "test-batch-partial"
        correlation_id = uuid4()

        # Partial failure - some essays failed but not all
        event_data = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-3",
                    file_name="essay3.pdf",
                    error_detail=ErrorDetail(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="File too large",
                        correlation_id=correlation_id,
                        timestamp=datetime.now(UTC),
                        service="file-service",
                        operation="validate",
                    ),
                ),
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=False,  # Partial failure - batch continues
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type=topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS),
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=event_data,
        )

        # Create mock message
        import json

        mock_msg = AsyncMock()
        mock_msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")

        # Act
        await batch_validation_errors_handler.handle_batch_validation_errors(mock_msg)

        # Assert - handler takes NO action for partial failures
        # The event is logged for observability but batch continues processing
        mock_batch_repo.update_batch_status.assert_not_called()

    async def test_dual_event_independence(
        self,
        batch_essays_ready_handler: BatchEssaysReadyHandler,
        batch_validation_errors_handler: BatchValidationErrorsHandler,
        mock_batch_repo: AsyncMock,
    ) -> None:
        """Test that success and error handlers operate independently."""
        batch_id = "test-batch-dual"
        correlation_id = uuid4()

        # Process success event
        success_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(
                    essay_id="essay-1",
                    text_storage_id="storage-1",
                ),
            ],
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Write",
            class_type="REGULAR",
            teacher_first_name="Bob",
            teacher_last_name="Jones",
        )

        success_envelope = EventEnvelope[BatchEssaysReady](
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=success_event,
        )

        import json

        success_msg = AsyncMock()
        success_msg.value = json.dumps(success_envelope.model_dump(mode="json")).encode("utf-8")

        await batch_essays_ready_handler.handle_batch_essays_ready(success_msg)

        # Process error event for the same batch
        error_event = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-2",
                    file_name="essay2.pdf",
                    error_detail=ErrorDetail(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Failed",
                        correlation_id=correlation_id,
                        timestamp=datetime.now(UTC),
                        service="file-service",
                        operation="validate",
                    ),
                ),
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=False,  # Partial failure
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                timestamp=datetime.now(UTC),
            ),
        )

        error_envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type=topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS),
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=error_event,
        )

        error_msg = AsyncMock()
        error_msg.value = json.dumps(error_envelope.model_dump(mode="json")).encode("utf-8")

        await batch_validation_errors_handler.handle_batch_validation_errors(error_msg)

        # Assert both handlers performed their specific responsibilities
        # Success handler stored essays
        mock_batch_repo.store_batch_essays.assert_called_once_with(
            batch_id, success_event.ready_essays
        )

        # Error handler took no action (partial failure)
        mock_batch_repo.update_batch_status.assert_not_called()

        # No cross-contamination between handlers
        assert mock_batch_repo.store_batch_essays.call_count == 1
        assert mock_batch_repo.update_batch_status.call_count == 0

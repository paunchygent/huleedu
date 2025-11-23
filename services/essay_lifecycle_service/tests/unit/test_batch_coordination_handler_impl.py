"""Unit tests for DefaultBatchCoordinationHandler.

Focus on handle_essay_validation_failed transactional behavior, ensuring
that BatchContentProvisioningCompletedV1 publishing and guest batch
completion both use the same database session.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from services.essay_lifecycle_service.implementations.batch_coordination_handler_impl import (
    DefaultBatchCoordinationHandler,
)
from services.essay_lifecycle_service.implementations.batch_lifecycle_publisher import (
    BatchLifecyclePublisher,
)
from services.essay_lifecycle_service.implementations.db_pending_content_ops import (
    DBPendingContentOperations,
)
from services.essay_lifecycle_service.protocols import (
    BatchEssayTracker,
    ContentAssignmentProtocol,
    EssayRepositoryProtocol,
)


class TestBatchCoordinationHandler:
    """Tests for DefaultBatchCoordinationHandler domain logic."""

    @pytest.mark.asyncio
    async def test_handle_essay_validation_failed_guest_uses_session_for_outbox_and_completion(
        self,
        mock_session_factory: Any,  # provided by services.essay_lifecycle_service.tests.conftest
    ) -> None:
        """Guest batch path should use the same session for outbox and completion.

        When validation failure completes a GUEST batch, the handler should:
        - Publish BatchContentProvisioningCompletedV1 with session
        - Call mark_batch_completed with the same session
        """

        # Arrange
        batch_id = "test-batch-guest-validation"
        correlation_id = uuid4()

        # Mocks for dependencies
        mock_batch_tracker: AsyncMock = AsyncMock(spec=BatchEssayTracker)
        mock_repository: AsyncMock = AsyncMock(spec=EssayRepositoryProtocol)
        mock_publisher: AsyncMock = AsyncMock(spec=BatchLifecyclePublisher)
        mock_pending_content_ops: AsyncMock = AsyncMock(spec=DBPendingContentOperations)
        mock_content_assignment: AsyncMock = AsyncMock(spec=ContentAssignmentProtocol)

        handler = DefaultBatchCoordinationHandler(
            batch_tracker=mock_batch_tracker,
            repository=mock_repository,
            batch_lifecycle_publisher=mock_publisher,
            pending_content_ops=mock_pending_content_ops,
            content_assignment_service=mock_content_assignment,
            session_factory=mock_session_factory,
        )

        # Validation failure event data (only attributes used by handler/logging)
        event_data = AsyncMock()
        event_data.entity_id = batch_id
        event_data.original_file_name = "invalid-file.txt"
        event_data.validation_error_code = "INVALID_CONTENT"

        # BatchReady event returned by tracker when batch becomes complete
        batch_ready_event = AsyncMock()
        batch_ready_event.batch_id = batch_id
        batch_ready_event.ready_essays = [
            {
                "essay_id": "essay-1",
                "text_storage_id": "storage-1",
                "batch_id": batch_id,
            }
        ]
        batch_ready_event.course_code = "ENG5"
        batch_ready_event.class_type = "GUEST"

        original_correlation_id = uuid4()

        # Tracker returns completion result from validation failure
        mock_batch_tracker.handle_validation_failure.return_value = (
            batch_ready_event,
            original_correlation_id,
        )
        mock_batch_tracker.get_batch_status.return_value = {"user_id": "test-user"}

        # Act
        result = await handler.handle_essay_validation_failed(event_data, correlation_id)

        # Assert
        assert result is True

        # Access the session created by mock_session_factory
        session = mock_session_factory._test_session

        # Outbox publish should use the same session
        mock_publisher.publish_batch_content_provisioning_completed.assert_awaited_once()
        pub_call = mock_publisher.publish_batch_content_provisioning_completed.await_args
        assert pub_call.kwargs["session"] is session
        # Correlation ID should use the original one from batch registration
        assert pub_call.kwargs["correlation_id"] == original_correlation_id

        # Guest batch completion should also use the same session
        mock_batch_tracker.mark_batch_completed.assert_awaited_once_with(batch_id, session)

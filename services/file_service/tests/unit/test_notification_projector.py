"""
Unit tests for the FileServiceNotificationProjector class.

Tests the projection of internal file management events to teacher notifications
following the notification projection pattern.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.error_enums import FileValidationErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.file_events import EssayValidationFailedV1
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from common_core.models.error_models import ErrorDetail
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

if TYPE_CHECKING:
    from services.file_service.notification_projector import FileServiceNotificationProjector


@pytest.fixture
def mock_kafka_publisher() -> AsyncMock:
    """Mock Kafka publisher for tests."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    return publisher


@pytest.fixture
def notification_projector(
    mock_kafka_publisher: AsyncMock,
) -> FileServiceNotificationProjector:
    """Create notification projector with mocked dependencies."""
    from services.file_service.notification_projector import FileServiceNotificationProjector

    return FileServiceNotificationProjector(
        kafka_publisher=mock_kafka_publisher,
    )


class TestBatchFileAddedProjection:
    """Tests for projecting BatchFileAddedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_batch_file_added_projects_to_standard_notification(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that file addition projects to STANDARD priority notification."""
        # Arrange
        batch_id = str(uuid4())
        file_upload_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchFileAddedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            filename="essay1.docx",
            user_id="teacher-123",
            correlation_id=correlation_id,
        )

        # Act
        await notification_projector.handle_batch_file_added(event)

        # Assert - verify Kafka publish was called
        mock_kafka_publisher.publish.assert_called_once()

        # Extract the call arguments
        call_args = mock_kafka_publisher.publish.call_args
        assert call_args.kwargs["topic"] == topic_name(
            ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED
        )
        assert call_args.kwargs["key"] == "teacher-123"

        # Get the envelope that was published
        envelope = call_args.kwargs["envelope"]

        # Verify envelope structure
        assert envelope.event_type == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        assert envelope.source_service == "file_service"

        # Extract and verify the notification data
        notification_data = envelope.data
        assert notification_data.teacher_id == "teacher-123"
        assert notification_data.notification_type == "batch_files_uploaded"
        assert notification_data.category == WebSocketEventCategory.FILE_OPERATIONS
        assert notification_data.priority == NotificationPriority.STANDARD
        assert notification_data.action_required is False
        assert notification_data.batch_id == batch_id

        # Verify payload content
        payload = notification_data.payload
        assert payload["batch_id"] == batch_id
        assert payload["file_upload_id"] == file_upload_id
        assert payload["filename"] == "essay1.docx"
        assert "uploaded successfully" in payload["message"]
        assert payload["upload_status"] == "completed"


class TestBatchFileRemovedProjection:
    """Tests for projecting BatchFileRemovedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_batch_file_removed_projects_to_standard_notification(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that file removal projects to STANDARD priority notification."""
        # Arrange
        batch_id = str(uuid4())
        file_upload_id = str(uuid4())
        correlation_id = uuid4()

        event = BatchFileRemovedV1(
            batch_id=batch_id,
            file_upload_id=file_upload_id,
            filename="essay2.pdf",
            user_id="teacher-456",
            correlation_id=correlation_id,
        )

        # Act
        await notification_projector.handle_batch_file_removed(event)

        # Assert - verify Kafka publish was called
        mock_kafka_publisher.publish.assert_called_once()

        # Extract the call arguments
        call_args = mock_kafka_publisher.publish.call_args
        assert call_args.kwargs["topic"] == topic_name(
            ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED
        )
        assert call_args.kwargs["key"] == "teacher-456"

        # Get the envelope that was published
        envelope = call_args.kwargs["envelope"]

        # Extract and verify the notification data
        notification_data = envelope.data
        assert notification_data.teacher_id == "teacher-456"
        assert notification_data.notification_type == "batch_file_removed"
        assert notification_data.category == WebSocketEventCategory.FILE_OPERATIONS
        assert notification_data.priority == NotificationPriority.STANDARD
        assert notification_data.action_required is False

        # Verify payload content
        payload = notification_data.payload
        assert payload["batch_id"] == batch_id
        assert payload["file_upload_id"] == file_upload_id
        assert payload["filename"] == "essay2.pdf"
        assert "removed from batch" in payload["message"]


class TestEssayValidationFailedProjection:
    """Tests for projecting EssayValidationFailedV1 events to teacher notifications."""

    @pytest.mark.asyncio
    async def test_validation_failed_projects_to_immediate_priority_notification(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that validation failure projects to IMMEDIATE priority notification."""
        # Arrange
        batch_id = str(uuid4())
        file_upload_id = str(uuid4())
        correlation_id = uuid4()

        from datetime import UTC, datetime

        error_detail = ErrorDetail(
            error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            message="File content is below minimum length requirement",
            service="file_service",
            operation="validate_content",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
        )

        event = EssayValidationFailedV1(
            entity_id=batch_id,  # batch_id stored as entity_id
            file_upload_id=file_upload_id,
            original_file_name="short_essay.txt",
            raw_file_storage_id="storage-123",
            validation_error_code=FileValidationErrorCode.CONTENT_TOO_SHORT,
            validation_error_detail=error_detail,
            file_size_bytes=100,
            correlation_id=correlation_id,
        )

        # Provide user_id since EssayValidationFailedV1 doesn't have it
        user_id = "teacher-789"

        # Act
        await notification_projector.handle_essay_validation_failed(event, user_id)

        # Assert - verify Kafka publish was called
        mock_kafka_publisher.publish.assert_called_once()

        # Extract the call arguments
        call_args = mock_kafka_publisher.publish.call_args
        assert call_args.kwargs["topic"] == topic_name(
            ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED
        )
        assert call_args.kwargs["key"] == "teacher-789"

        # Get the envelope that was published
        envelope = call_args.kwargs["envelope"]

        # Extract and verify the notification data
        notification_data = envelope.data
        assert notification_data.teacher_id == "teacher-789"
        assert notification_data.notification_type == "batch_validation_failed"
        assert notification_data.category == WebSocketEventCategory.SYSTEM_ALERTS
        assert notification_data.priority == NotificationPriority.IMMEDIATE
        assert notification_data.action_required is True
        assert notification_data.batch_id == batch_id

        # Verify payload content
        payload = notification_data.payload
        assert payload["batch_id"] == batch_id
        assert payload["file_upload_id"] == file_upload_id
        assert payload["filename"] == "short_essay.txt"
        assert payload["validation_error"] == "CONTENT_TOO_SHORT"
        assert payload["error_message"] == "File content is below minimum length requirement"
        assert "failed validation" in payload["message"]


class TestMultipleFileAggregation:
    """Tests for aggregating multiple file events into batch notifications."""

    @pytest.mark.asyncio
    async def test_multiple_file_additions_create_separate_notifications(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that multiple file additions create separate notifications (not aggregated)."""
        # Arrange
        batch_id = str(uuid4())
        files = [
            {"id": str(uuid4()), "name": "essay1.docx"},
            {"id": str(uuid4()), "name": "essay2.pdf"},
            {"id": str(uuid4()), "name": "essay3.txt"},
        ]

        events = [
            BatchFileAddedV1(
                batch_id=batch_id,
                file_upload_id=file_info["id"],
                filename=file_info["name"],
                user_id="teacher-123",
                correlation_id=uuid4(),
            )
            for file_info in files
        ]

        # Act - process each event
        for event in events:
            await notification_projector.handle_batch_file_added(event)

        # Assert - verify separate notifications were published
        assert mock_kafka_publisher.publish.call_count == 3

        # Verify each notification
        for i, call_obj in enumerate(mock_kafka_publisher.publish.call_args_list):
            call_args = call_obj.kwargs

            # Get the envelope
            envelope = call_args["envelope"]
            notification_data = envelope.data

            # Verify notification details
            assert notification_data.teacher_id == "teacher-123"
            assert notification_data.notification_type == "batch_files_uploaded"
            assert notification_data.batch_id == batch_id

            # Verify individual file info
            payload = notification_data.payload
            assert payload["file_upload_id"] == files[i]["id"]
            assert payload["filename"] == files[i]["name"]


class TestNotificationPublishingError:
    """Tests for error handling in notification publishing."""

    @pytest.mark.asyncio
    async def test_publishing_error_propagates_exception(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that publishing errors are propagated for proper error handling."""
        # Arrange
        mock_kafka_publisher.publish.side_effect = Exception("Kafka connection failed")

        event = BatchFileAddedV1(
            batch_id=str(uuid4()),
            file_upload_id=str(uuid4()),
            filename="test.docx",
            user_id="teacher-999",
            correlation_id=uuid4(),
        )

        # Act & Assert
        with pytest.raises(Exception, match="Kafka connection failed"):
            await notification_projector.handle_batch_file_added(event)

    @pytest.mark.asyncio
    async def test_validation_failed_without_user_id_requires_explicit_parameter(
        self,
        notification_projector: FileServiceNotificationProjector,
        mock_kafka_publisher: AsyncMock,
    ) -> None:
        """Test that validation failure handler requires explicit user_id parameter."""
        # Arrange
        from datetime import UTC, datetime

        error_detail = ErrorDetail(
            error_code=FileValidationErrorCode.EMPTY_CONTENT,
            message="File has no content",
            service="file_service",
            operation="validate_content",
            correlation_id=uuid4(),
            timestamp=datetime.now(UTC),
        )

        event = EssayValidationFailedV1(
            entity_id=str(uuid4()),
            file_upload_id=str(uuid4()),
            original_file_name="empty.txt",
            raw_file_storage_id="storage-456",
            validation_error_code=FileValidationErrorCode.EMPTY_CONTENT,
            validation_error_detail=error_detail,
            file_size_bytes=0,
            correlation_id=uuid4(),
        )

        # Act - call with explicit user_id
        await notification_projector.handle_essay_validation_failed(event, "teacher-explicit")

        # Assert - verify notification was published with provided user_id
        mock_kafka_publisher.publish.assert_called_once()

        call_args = mock_kafka_publisher.publish.call_args
        envelope = call_args.kwargs["envelope"]
        notification_data = envelope.data

        assert notification_data.teacher_id == "teacher-explicit"
        assert notification_data.notification_type == "batch_validation_failed"

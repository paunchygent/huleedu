"""
Integration tests for File Service notification handling in WebSocket Service.

Tests that File Service notification types are properly processed through
the WebSocket service notification pipeline according to Rule 075 behavioral
testing methodology.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

from services.websocket_service.config import Settings
from services.websocket_service.implementations.notification_event_consumer import (
    NotificationEventConsumer,
)
from services.websocket_service.implementations.notification_handler import NotificationHandler


class TestFileServiceNotifications:
    """Test suite for File Service specific notifications."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for tests."""
        return Settings(
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            KAFKA_CONSUMER_GROUP="test-websocket-consumer",
            KAFKA_CONSUMER_CLIENT_ID="test-websocket-client",
        )

    @pytest.fixture
    def create_file_notification_message(self) -> Callable[[dict], MagicMock]:
        """Factory for creating File Service notification messages."""

        def _create_message(notification_data: dict) -> MagicMock:
            message_data = {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
                "event_timestamp": datetime.now(UTC).isoformat(),
                "source_service": "file_service",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
                "data": notification_data,
                "metadata": {},
            }

            msg = MagicMock(spec=ConsumerRecord)
            msg.value = json.dumps(message_data).encode("utf-8")
            msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
            msg.partition = 0
            msg.offset = 100
            return msg

        return _create_message

    @pytest.mark.asyncio
    async def test_batch_files_uploaded_notification_standard_priority(self) -> None:
        """Test that batch file upload notifications are forwarded with STANDARD priority."""
        # Arrange
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-test-123",
            notification_type="batch_files_uploaded",
            category=WebSocketEventCategory.FILE_OPERATIONS,
            priority=NotificationPriority.STANDARD,
            payload={
                "batch_id": "batch-456",
                "file_upload_id": "file-789",
                "filename": "test_essay.txt",
                "message": "File 'test_essay.txt' uploaded successfully",
                "upload_status": "completed",
            },
            action_required=False,
            correlation_id="corr-file-upload",
            batch_id="batch-456",
        )

        # Act
        await handler.handle_teacher_notification(event)

        # Assert - Verify behavioral outcome
        redis_client.publish_user_notification.assert_called_once_with(
            user_id="teacher-test-123",
            event_type="batch_files_uploaded",
            data={
                "batch_id": "batch-456",
                "file_upload_id": "file-789",
                "filename": "test_essay.txt",
                "message": "File 'test_essay.txt' uploaded successfully",
                "upload_status": "completed",
                "category": "file_operations",
                "priority": "standard",
                "action_required": False,
                "deadline": None,
                "class_id": None,
                "correlation_id": "corr-file-upload",
                "timestamp": event.timestamp.isoformat(),
            },
        )

    @pytest.mark.asyncio
    async def test_batch_validation_failed_notification_immediate_priority(self) -> None:
        """Test that validation failure notifications have IMMEDIATE priority and require action."""
        # Arrange
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-test-456",
            notification_type="batch_validation_failed",
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
            payload={
                "batch_id": "batch-789",
                "file_upload_id": "file-012",
                "filename": "invalid_essay.txt",
                "validation_error": "INVALID_FORMAT",
                "error_message": "File format is not supported. Expected: TXT, DOCX, PDF",
                "message": (
                    "File 'invalid_essay.txt' failed validation: File format is not supported"
                ),
            },
            action_required=True,
            correlation_id="corr-validation-fail",
            batch_id="batch-789",
        )

        # Act
        await handler.handle_teacher_notification(event)

        # Assert - Verify behavioral outcome with action required
        redis_client.publish_user_notification.assert_called_once()
        call_args = redis_client.publish_user_notification.call_args

        assert call_args[1]["user_id"] == "teacher-test-456"
        assert call_args[1]["event_type"] == "batch_validation_failed"
        assert call_args[1]["data"]["priority"] == "immediate"
        assert call_args[1]["data"]["action_required"] is True
        assert call_args[1]["data"]["validation_error"] == "INVALID_FORMAT"

    @pytest.mark.asyncio
    async def test_batch_file_removed_notification_standard_priority(self) -> None:
        """Test that file removal notifications are forwarded with STANDARD priority."""
        # Arrange
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-test-789",
            notification_type="batch_file_removed",
            category=WebSocketEventCategory.FILE_OPERATIONS,
            priority=NotificationPriority.STANDARD,
            payload={
                "batch_id": "batch-345",
                "file_upload_id": "file-678",
                "filename": "removed_essay.txt",
                "message": "File 'removed_essay.txt' removed from batch",
            },
            action_required=False,
            correlation_id="corr-file-remove",
            batch_id="batch-345",
        )

        # Act
        await handler.handle_teacher_notification(event)

        # Assert - Verify behavioral outcome
        redis_client.publish_user_notification.assert_called_once()
        call_args = redis_client.publish_user_notification.call_args

        assert call_args[1]["user_id"] == "teacher-test-789"
        assert call_args[1]["event_type"] == "batch_file_removed"
        assert call_args[1]["data"]["priority"] == "standard"
        assert call_args[1]["data"]["action_required"] is False

    @pytest.mark.asyncio
    async def test_file_service_notification_via_consumer_pipeline(
        self, mock_settings: Settings, create_file_notification_message: Callable[[dict], MagicMock]
    ) -> None:
        """Test end-to-end processing of File Service notification through consumer pipeline."""
        # Arrange
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a File Service notification message
        msg = create_file_notification_message(
            {
                "teacher_id": "teacher-integration-123",
                "notification_type": "batch_files_uploaded",
                "category": "file_operations",
                "priority": "standard",
                "payload": {
                    "batch_id": "batch-integration-456",
                    "file_upload_id": "file-integration-789",
                    "filename": "integration_test.txt",
                    "message": "File 'integration_test.txt' uploaded successfully",
                    "upload_status": "completed",
                },
                "action_required": False,
                "correlation_id": "corr-integration",
                "batch_id": "batch-integration-456",
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )

        # Act
        result = await consumer.process_message(msg)

        # Assert - Verify behavioral outcome through pipeline
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

        # Verify the event was properly constructed from File Service notification
        call_args = notification_handler.handle_teacher_notification.call_args[0][0]
        assert isinstance(call_args, TeacherNotificationRequestedV1)
        assert call_args.teacher_id == "teacher-integration-123"
        assert call_args.notification_type == "batch_files_uploaded"
        assert call_args.category == WebSocketEventCategory.FILE_OPERATIONS
        assert call_args.priority == NotificationPriority.STANDARD
        assert call_args.batch_id == "batch-integration-456"
        assert call_args.payload["filename"] == "integration_test.txt"

    @pytest.mark.asyncio
    async def test_file_service_validation_error_blocks_workflow(self) -> None:
        """Test that validation errors properly block workflow with IMMEDIATE priority."""
        # Arrange
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-workflow-123",
            notification_type="batch_validation_failed",
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
            payload={
                "batch_id": "batch-workflow-456",
                "file_upload_id": "file-workflow-789",
                "filename": "corrupted.pdf",
                "validation_error": "FILE_CORRUPTED",
                "error_message": "File cannot be read/processed",
                "message": "File 'corrupted.pdf' failed validation: File cannot be read/processed",
            },
            action_required=True,
            correlation_id="corr-workflow-block",
            batch_id="batch-workflow-456",
        )

        # Act
        await handler.handle_teacher_notification(event)

        # Assert - Verify IMMEDIATE priority blocks workflow
        call_args = redis_client.publish_user_notification.call_args
        notification_data = call_args[1]["data"]

        # Behavioral assertions per Rule 075
        assert notification_data["priority"] == "immediate", (
            "Validation failures must have IMMEDIATE priority"
        )
        assert notification_data["action_required"] is True, (
            "Validation failures must require teacher action"
        )
        assert notification_data["category"] == "system_alerts", (
            "Validation failures are system alerts"
        )
        assert "validation_error" in notification_data, "Error code must be included for debugging"
        assert "error_message" in notification_data, "Human-readable error must be included"

    @pytest.mark.parametrize(
        "notification_type,priority,action_required",
        [
            ("batch_files_uploaded", NotificationPriority.STANDARD, False),
            ("batch_file_removed", NotificationPriority.STANDARD, False),
            ("batch_validation_failed", NotificationPriority.IMMEDIATE, True),
            ("batch_file_corrupted", NotificationPriority.IMMEDIATE, True),
        ],
    )
    @pytest.mark.asyncio
    async def test_file_service_notification_priorities(
        self, notification_type: str, priority: NotificationPriority, action_required: bool
    ) -> None:
        """Test that File Service notifications have correct priorities and action flags."""
        # Arrange
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-priority-test",
            notification_type=notification_type,
            category=(
                WebSocketEventCategory.SYSTEM_ALERTS
                if priority == NotificationPriority.IMMEDIATE
                else WebSocketEventCategory.FILE_OPERATIONS
            ),
            priority=priority,
            payload={
                "batch_id": "batch-priority-test",
                "file_upload_id": "file-priority-test",
                "filename": "test.txt",
                "message": f"Testing {notification_type}",
            },
            action_required=action_required,
            correlation_id="corr-priority-test",
            batch_id="batch-priority-test",
        )

        # Act
        await handler.handle_teacher_notification(event)

        # Assert - Verify behavioral compliance with task specification
        call_args = redis_client.publish_user_notification.call_args
        notification_data = call_args[1]["data"]

        assert notification_data["priority"] == priority.value
        assert notification_data["action_required"] == action_required

        # Verify category mapping
        if priority == NotificationPriority.IMMEDIATE:
            assert notification_data["category"] == "system_alerts"
        else:
            assert notification_data["category"] == "file_operations"

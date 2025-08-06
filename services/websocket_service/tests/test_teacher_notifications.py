"""
Unit tests for WebSocket Service teacher notification features.

Tests the notification event consumer and handler components that process
TeacherNotificationRequestedV1 events and forward them to Redis.
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


class TestNotificationHandler:
    """Test suite for teacher notification handler."""

    @pytest.mark.asyncio
    async def test_handle_teacher_notification_critical_priority(self) -> None:
        """Test handling of CRITICAL priority teacher notification."""
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        deadline = datetime.now(UTC)
        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-123",
            notification_type="student_matching_confirmation_required",
            category=WebSocketEventCategory.STUDENT_WORKFLOW,
            priority=NotificationPriority.CRITICAL,
            payload={
                "batch_id": "batch-456",
                "unmatched_count": 5,
                "message": "5 students require manual confirmation",
            },
            action_required=True,
            deadline_timestamp=deadline,
            correlation_id="corr-789",
            batch_id="batch-456",
            class_id="class-012",
        )

        await handler.handle_teacher_notification(event)

        redis_client.publish_user_notification.assert_called_once_with(
            user_id="teacher-123",
            event_type="student_matching_confirmation_required",
            data={
                "batch_id": "batch-456",
                "unmatched_count": 5,
                "message": "5 students require manual confirmation",
                "category": "student_workflow",
                "priority": "critical",
                "action_required": True,
                "deadline": deadline.isoformat(),
                "class_id": "class-012",
                "correlation_id": "corr-789",
                "timestamp": event.timestamp.isoformat(),
            },
        )

    @pytest.mark.asyncio
    async def test_handle_teacher_notification_high_priority(self) -> None:
        """Test handling of HIGH priority teacher notification."""
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-456",
            notification_type="batch_processing_completed",
            category=WebSocketEventCategory.BATCH_PROGRESS,
            priority=NotificationPriority.HIGH,
            payload={
                "batch_id": "batch-789",
                "batch_name": "Essay Batch 1",
                "status": "completed",
                "processed_count": 25,
            },
            action_required=False,
            correlation_id="corr-012",
            batch_id="batch-789",
        )

        await handler.handle_teacher_notification(event)

        redis_client.publish_user_notification.assert_called_once_with(
            user_id="teacher-456",
            event_type="batch_processing_completed",
            data={
                "batch_id": "batch-789",
                "batch_name": "Essay Batch 1",
                "status": "completed",
                "processed_count": 25,
                "category": "batch_progress",
                "priority": "high",
                "action_required": False,
                "deadline": None,
                "class_id": None,
                "correlation_id": "corr-012",
                "timestamp": event.timestamp.isoformat(),
            },
        )

    @pytest.mark.asyncio
    async def test_handle_teacher_notification_standard_priority(self) -> None:
        """Test handling of STANDARD priority teacher notification."""
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-789",
            notification_type="class_created",
            category=WebSocketEventCategory.CLASS_MANAGEMENT,
            priority=NotificationPriority.STANDARD,
            payload={
                "class_id": "class-345",
                "class_name": "Grade 9 English",
                "student_count": 30,
            },
            action_required=False,
            correlation_id="corr-345",
            class_id="class-345",
        )

        await handler.handle_teacher_notification(event)

        redis_client.publish_user_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_teacher_notification_low_priority(self) -> None:
        """Test handling of LOW priority teacher notification."""
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-012",
            notification_type="batch_spellcheck_completed",
            category=WebSocketEventCategory.PROCESSING_RESULTS,
            priority=NotificationPriority.LOW,
            payload={
                "batch_id": "batch-567",
                "errors_found": 42,
            },
            action_required=False,
            correlation_id="corr-678",
            batch_id="batch-567",
        )

        await handler.handle_teacher_notification(event)

        redis_client.publish_user_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_teacher_notification_error(self) -> None:
        """Test error handling in teacher notification."""
        redis_client = AsyncMock()
        redis_client.publish_user_notification.side_effect = Exception("Redis connection failed")
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-123",
            notification_type="batch_processing_failed",
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=NotificationPriority.IMMEDIATE,
            payload={"batch_id": "batch-999", "error": "Processing pipeline failed"},
            action_required=True,
            correlation_id="corr-999",
            batch_id="batch-999",
        )

        with pytest.raises(Exception, match="Redis connection failed"):
            await handler.handle_teacher_notification(event)


class TestNotificationEventConsumer:
    """Test suite for teacher notification event consumer."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for tests."""
        return Settings(
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            KAFKA_CONSUMER_GROUP="test-websocket-consumer",
            KAFKA_CONSUMER_CLIENT_ID="test-websocket-client",
        )

    @pytest.fixture
    def create_kafka_message(self) -> Callable[[str, dict], MagicMock]:
        """Factory for creating mock Kafka messages with EventEnvelope structure."""

        def _create_message(event_type: str, data: dict) -> MagicMock:
            message_data = {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": event_type,
                "event_timestamp": "2024-01-01T12:00:00Z",
                "source_service": "class_management_service",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
                "data": data,
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
    async def test_process_teacher_notification_message(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test processing of teacher notification event from Kafka."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a mock Kafka message with teacher notification
        deadline = datetime.now(UTC).isoformat()
        msg = create_kafka_message(
            topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            {
                "teacher_id": "teacher-123",
                "notification_type": "batch_processing_completed",
                "category": "batch_progress",
                "priority": "high",
                "payload": {
                    "batch_id": "batch-456",
                    "batch_name": "Essay Batch 1",
                    "status": "completed",
                },
                "action_required": False,
                "deadline_timestamp": deadline,
                "correlation_id": "corr-789",
                "batch_id": "batch-456",
                "class_id": "class-012",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        result = await consumer.process_message(msg)

        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

        # Verify the event was properly constructed
        call_args = notification_handler.handle_teacher_notification.call_args[0][0]
        assert isinstance(call_args, TeacherNotificationRequestedV1)
        assert call_args.teacher_id == "teacher-123"
        assert call_args.notification_type == "batch_processing_completed"
        assert call_args.category == WebSocketEventCategory.BATCH_PROGRESS
        assert call_args.priority == NotificationPriority.HIGH
        assert call_args.batch_id == "batch-456"
        assert call_args.class_id == "class-012"

    @pytest.mark.asyncio
    async def test_process_wrong_event_type(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test that consumer rejects non-notification events."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a message with wrong event type
        msg = create_kafka_message(
            "huleedu.file.batch.file.added.v1",  # Wrong event type
            {"some": "data"},
        )

        result = await consumer.process_message(msg)

        assert result is False
        notification_handler.handle_teacher_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_with_trace_context(self, mock_settings: Settings) -> None:
        """Test that trace context is extracted from event metadata."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create message with trace context
        message_data = {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            "event_timestamp": "2024-01-01T12:00:00Z",
            "source_service": "class_management_service",
            "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
            "data": {
                "teacher_id": "teacher-123",
                "notification_type": "class_created",
                "category": "class_management",
                "priority": "standard",
                "payload": {"class_id": "class-123"},
                "action_required": False,
                "correlation_id": "corr-123",
                "timestamp": datetime.now(UTC).isoformat(),
            },
            "metadata": {"traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"},
        }

        msg = MagicMock(spec=ConsumerRecord)
        msg.value = json.dumps(message_data).encode("utf-8")
        msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        msg.partition = 0
        msg.offset = 100

        result = await consumer.process_message(msg)

        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_handles_handler_error(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test that process_message handles errors from notification handler."""
        notification_handler = AsyncMock()
        notification_handler.handle_teacher_notification.side_effect = Exception("Handler error")
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        msg = create_kafka_message(
            topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
            {
                "teacher_id": "teacher-123",
                "notification_type": "batch_processing_failed",
                "category": "system_alerts",
                "priority": "immediate",
                "payload": {"batch_id": "batch-999", "error": "Processing failed"},
                "action_required": True,
                "correlation_id": "corr-999",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        result = await consumer.process_message(msg)

        assert result is False
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_consumer(self, mock_settings: Settings) -> None:
        """Test stopping the consumer gracefully."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Set initial state
        consumer.should_stop = False
        consumer.consumer = AsyncMock()

        await consumer.stop_consumer()

        assert consumer.should_stop is True
        consumer.consumer.stop.assert_called_once()

    @pytest.mark.parametrize(
        "priority,expected_priority",
        [
            (NotificationPriority.CRITICAL, "critical"),
            (NotificationPriority.IMMEDIATE, "immediate"),
            (NotificationPriority.HIGH, "high"),
            (NotificationPriority.STANDARD, "standard"),
            (NotificationPriority.LOW, "low"),
        ],
    )
    @pytest.mark.asyncio
    async def test_all_priority_levels(
        self, priority: NotificationPriority, expected_priority: str
    ) -> None:
        """Test that all 5 priority levels are handled correctly."""
        redis_client = AsyncMock()
        handler = NotificationHandler(redis_client=redis_client)

        event = TeacherNotificationRequestedV1(
            teacher_id="teacher-123",
            notification_type="test_notification",
            category=WebSocketEventCategory.SYSTEM_ALERTS,
            priority=priority,
            payload={"test": "data"},
            action_required=False,
            correlation_id="corr-123",
        )

        await handler.handle_teacher_notification(event)

        call_args = redis_client.publish_user_notification.call_args
        assert call_args[1]["data"]["priority"] == expected_priority

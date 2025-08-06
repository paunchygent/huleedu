"""Integration tests for WebSocket Service Kafka Consumer."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.config import Settings
from services.websocket_service.implementations.notification_event_consumer import (
    NotificationEventConsumer,
)
from services.websocket_service.implementations.notification_handler import NotificationHandler


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    settings.KAFKA_CONSUMER_GROUP = "test-websocket-consumer-group"
    settings.KAFKA_CONSUMER_CLIENT_ID = "test-websocket-client"
    return settings


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client."""
    return AsyncMock(spec=AtomicRedisClientProtocol)


@pytest.fixture
def notification_handler(mock_redis_client: AsyncMock) -> NotificationHandler:
    """Create teacher notification handler."""
    return NotificationHandler(redis_client=mock_redis_client)


@pytest.fixture
def notification_event_consumer(
    mock_settings: Settings,
    notification_handler: NotificationHandler,
    mock_redis_client: AsyncMock,
) -> NotificationEventConsumer:
    """Create notification event consumer."""
    return NotificationEventConsumer(
        settings=mock_settings,
        notification_handler=notification_handler,
        redis_client=mock_redis_client,
    )


def create_teacher_notification_envelope(
    notification_data: dict[str, Any],
) -> EventEnvelope[TeacherNotificationRequestedV1]:
    """Create a teacher notification event envelope."""
    event_data = TeacherNotificationRequestedV1(**notification_data)

    return EventEnvelope(
        event_id=uuid4(),
        event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
        event_timestamp=datetime.now(UTC),
        source_service="class_management_service",
        correlation_id=uuid4(),
        data=event_data,
    )


@pytest.mark.asyncio
class TestNotificationEventConsumerIntegration:
    """Integration tests for notification event consumer."""

    async def test_process_critical_notification(
        self,
        notification_event_consumer: NotificationEventConsumer,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test processing of CRITICAL priority notification."""
        # Create critical notification event
        deadline = datetime.now(UTC)
        notification_data = {
            "teacher_id": "teacher-123",
            "notification_type": "student_matching_confirmation_required",
            "category": WebSocketEventCategory.STUDENT_WORKFLOW,
            "priority": NotificationPriority.CRITICAL,
            "payload": {
                "batch_id": "batch-456",
                "unmatched_count": 5,
                "message": "5 students require manual confirmation",
            },
            "action_required": True,
            "deadline_timestamp": deadline,
            "correlation_id": "corr-789",
            "batch_id": "batch-456",
            "class_id": "class-012",
        }

        envelope = create_teacher_notification_envelope(notification_data)

        # Create mock Kafka message
        msg = MagicMock()
        msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        msg.partition = 0
        msg.offset = 100

        # Process the message
        result = await notification_event_consumer.process_message(msg)

        assert result is True
        mock_redis_client.publish_user_notification.assert_called_once()

        # Verify the notification was published correctly
        call_args = mock_redis_client.publish_user_notification.call_args
        assert call_args[1]["user_id"] == "teacher-123"
        assert call_args[1]["event_type"] == "student_matching_confirmation_required"
        assert call_args[1]["data"]["priority"] == "critical"
        assert call_args[1]["data"]["action_required"] is True

    async def test_process_immediate_notification(
        self,
        notification_event_consumer: NotificationEventConsumer,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test processing of IMMEDIATE priority notification (errors/failures)."""
        notification_data = {
            "teacher_id": "teacher-456",
            "notification_type": "batch_processing_failed",
            "category": WebSocketEventCategory.SYSTEM_ALERTS,
            "priority": NotificationPriority.IMMEDIATE,
            "payload": {
                "batch_id": "batch-789",
                "error": "Processing pipeline failed",
                "failed_at": "spellcheck",
            },
            "action_required": True,
            "correlation_id": "corr-012",
            "batch_id": "batch-789",
        }

        envelope = create_teacher_notification_envelope(notification_data)

        # Create mock Kafka message
        msg = MagicMock()
        msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        msg.partition = 0
        msg.offset = 200

        # Process the message
        result = await notification_event_consumer.process_message(msg)

        assert result is True
        mock_redis_client.publish_user_notification.assert_called_once()

        # Verify error notification details
        call_args = mock_redis_client.publish_user_notification.call_args
        assert call_args[1]["user_id"] == "teacher-456"
        assert call_args[1]["data"]["priority"] == "immediate"
        assert call_args[1]["data"]["action_required"] is True

    async def test_process_high_priority_batch_complete(
        self,
        notification_event_consumer: NotificationEventConsumer,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test processing of HIGH priority batch completion notification."""
        notification_data = {
            "teacher_id": "teacher-789",
            "notification_type": "batch_processing_completed",
            "category": WebSocketEventCategory.BATCH_PROGRESS,
            "priority": NotificationPriority.HIGH,
            "payload": {
                "batch_id": "batch-012",
                "batch_name": "Essay Batch Q1",
                "status": "completed",
                "processed_count": 30,
                "duration_seconds": 245,
            },
            "action_required": False,
            "correlation_id": "corr-345",
            "batch_id": "batch-012",
            "class_id": "class-567",
        }

        envelope = create_teacher_notification_envelope(notification_data)

        # Create mock Kafka message
        msg = MagicMock()
        msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        msg.partition = 1
        msg.offset = 300

        # Process the message
        result = await notification_event_consumer.process_message(msg)

        assert result is True
        mock_redis_client.publish_user_notification.assert_called_once()

        # Verify batch completion details
        call_args = mock_redis_client.publish_user_notification.call_args
        assert call_args[1]["data"]["priority"] == "high"
        assert call_args[1]["data"]["processed_count"] == 30
        assert call_args[1]["data"]["action_required"] is False

    async def test_error_handling_in_notification_chain(
        self,
        notification_event_consumer: NotificationEventConsumer,
        mock_redis_client: AsyncMock,
    ) -> None:
        """Test that errors in the notification chain are handled properly."""
        # Make Redis fail
        mock_redis_client.publish_user_notification.side_effect = Exception("Redis unavailable")

        notification_data = {
            "teacher_id": "teacher-error",
            "notification_type": "batch_processing_started",
            "category": WebSocketEventCategory.BATCH_PROGRESS,
            "priority": NotificationPriority.LOW,
            "payload": {"batch_id": "batch-error"},
            "action_required": False,
            "correlation_id": "corr-error",
        }

        envelope = create_teacher_notification_envelope(notification_data)

        # Create mock Kafka message
        msg = MagicMock()
        msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
        msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        msg.partition = 0
        msg.offset = 500

        # Process should handle the error gracefully
        result = await notification_event_consumer.process_message(msg)

        assert result is False  # Processing failed
        mock_redis_client.publish_user_notification.assert_called_once()

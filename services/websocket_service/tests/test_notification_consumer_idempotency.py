"""
Comprehensive tests for idempotency behavior in NotificationEventConsumer.

Tests both happy path (Redis working correctly) and resilience path (Redis failures).
The idempotency system is designed to gracefully degrade when Redis fails.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

from services.websocket_service.config import Settings
from services.websocket_service.implementations.notification_event_consumer import (
    NotificationEventConsumer,
)
from services.websocket_service.implementations.notification_handler import NotificationHandler


def create_test_message(test_id: str = "test") -> MagicMock:
    """Create a standard test Kafka message with TeacherNotificationRequestedV1."""
    correlation_id = uuid4()  # Proper UUID for EventEnvelope
    event_id = uuid4()  # Proper UUID for EventEnvelope

    notification_data = {
        "teacher_id": "teacher-123",
        "notification_type": "batch_processing_completed",
        "category": WebSocketEventCategory.BATCH_PROGRESS,
        "priority": NotificationPriority.HIGH,
        "payload": {"batch_id": "batch-456", "status": "completed"},
        "action_required": False,
        "correlation_id": str(correlation_id),  # String for notification data
        "batch_id": "batch-456",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    envelope: EventEnvelope[TeacherNotificationRequestedV1] = EventEnvelope(
        event_id=event_id,  # UUID object
        event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
        event_timestamp=datetime.now(UTC),
        source_service="class_management_service",
        correlation_id=correlation_id,  # UUID object
        data=TeacherNotificationRequestedV1(**notification_data),
    )

    msg = MagicMock()
    msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
    msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    msg.partition = 0
    msg.offset = 100
    return msg


def create_test_message_with_id(correlation_id: UUID) -> MagicMock:
    """Create a test message with specific correlation_id for consistency testing."""
    event_id = uuid4()  # Proper UUID for EventEnvelope

    notification_data = {
        "teacher_id": "teacher-123",
        "notification_type": "batch_processing_completed",
        "category": WebSocketEventCategory.BATCH_PROGRESS,
        "priority": NotificationPriority.HIGH,
        "payload": {"batch_id": "batch-456", "status": "completed"},
        "action_required": False,
        "correlation_id": str(correlation_id),  # String for notification data
        "batch_id": "batch-456",
        "timestamp": datetime.now(UTC).isoformat(),
    }

    envelope: EventEnvelope[TeacherNotificationRequestedV1] = EventEnvelope(
        event_id=event_id,  # UUID object
        event_type=topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED),
        event_timestamp=datetime.now(UTC),
        source_service="class_management_service",
        correlation_id=correlation_id,  # UUID object (from parameter)
        data=TeacherNotificationRequestedV1(**notification_data),
    )

    msg = MagicMock()
    msg.value = json.dumps(envelope.model_dump(mode="json")).encode("utf-8")
    msg.topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    msg.partition = 0
    msg.offset = 100
    return msg


class TestNotificationConsumerIdempotency:
    """Test suite for idempotency behavior in notification consumer."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for testing."""
        settings = MagicMock(spec=Settings)
        settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
        settings.KAFKA_CONSUMER_GROUP = "test-websocket-consumer"
        settings.KAFKA_CONSUMER_CLIENT_ID = "test-websocket-client"
        return settings

    @pytest.mark.asyncio
    async def test_happy_path_new_message_processes_normally(self, mock_settings: Settings) -> None:
        """Test that new messages (no duplicate) are processed normally when Redis works."""
        # Set up Redis to work correctly and indicate this is NOT a duplicate
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.return_value = True  # Key was set (not duplicate)
        mock_redis_client.get.return_value = None  # No existing result
        mock_redis_client.set.return_value = True
        mock_redis_client.expire.return_value = True
        mock_redis_client.delete.return_value = True

        # Set up notification handler
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("new-message-123")

        # Process the message through idempotent wrapper
        result = await consumer.process_message_idempotently(msg)

        # New message should be processed normally
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

        # Verify Redis operations for idempotency were attempted
        mock_redis_client.set_if_not_exists.assert_called()

    @pytest.mark.asyncio
    async def test_happy_path_duplicate_message_skipped(self, mock_settings: Settings) -> None:
        """Test that duplicate messages are skipped when Redis detects them."""
        # Set up Redis to correctly detect duplicate
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.return_value = False  # Key exists (duplicate)
        mock_redis_client.get.return_value = (
            '{"status": "completed", "result": true}'  # Cached result
        )
        mock_redis_client.expire.return_value = True

        # Set up notification handler
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("duplicate-message-456")

        # Process the duplicate message
        result = await consumer.process_message_idempotently(msg)

        # Duplicate should be skipped (returns cached result or None)
        assert result in [None, True]  # Depending on cached result parsing

        # Handler should NOT be called for duplicates - this is the key behavior
        notification_handler.handle_teacher_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_resilience_path_redis_connection_failure(self, mock_settings: Settings) -> None:
        """Test graceful fallback when Redis connection fails."""
        # Set up Redis to fail on operations
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.side_effect = ConnectionError("Redis connection failed")
        mock_redis_client.get.side_effect = ConnectionError("Redis connection failed")

        # Set up notification handler to work normally
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("redis-failure-789")

        # Process message when Redis fails
        result = await consumer.process_message_idempotently(msg)

        # Should fall back to normal processing despite Redis failure
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_resilience_path_redis_json_parsing_error(self, mock_settings: Settings) -> None:
        """Test graceful fallback when Redis returns non-JSON data."""
        # Set up Redis to return invalid JSON (like AsyncMock objects)
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.return_value = False  # Indicates duplicate
        mock_redis_client.get.return_value = AsyncMock()  # This will fail JSON parsing
        mock_redis_client.expire.return_value = True

        # Set up notification handler
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("json-parse-error-012")

        # Process message when Redis returns unparseable data
        result = await consumer.process_message_idempotently(msg)

        # Should fall back to normal processing despite "duplicate" indication
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_resilience_path_redis_timeout(self, mock_settings: Settings) -> None:
        """Test graceful fallback when Redis operations timeout."""
        # Set up Redis to timeout on operations
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.side_effect = TimeoutError("Redis operation timed out")
        mock_redis_client.get.side_effect = TimeoutError("Redis operation timed out")

        # Set up notification handler
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("timeout-345")

        # Process message when Redis times out
        result = await consumer.process_message_idempotently(msg)

        # Should fall back to normal processing
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_resilience_path_partial_redis_failure(self, mock_settings: Settings) -> None:
        """Test behavior when some Redis operations succeed but others fail."""
        # Set up Redis with mixed success/failure
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.return_value = True  # Success: not duplicate
        mock_redis_client.set.side_effect = ConnectionError(
            "Failed to cache result"
        )  # Fail on caching
        mock_redis_client.expire.side_effect = ConnectionError("Failed to set expiry")

        # Set up notification handler
        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        msg = create_test_message("partial-failure-678")

        # Process message with partial Redis failures
        result = await consumer.process_message_idempotently(msg)

        # Should still process the message (Redis indicated not duplicate)
        assert result is True
        notification_handler.handle_teacher_notification.assert_called_once()

    @pytest.mark.asyncio
    async def test_idempotency_key_generation_consistency(self, mock_settings: Settings) -> None:
        """Test that identical messages are processed only once (duplicate detection works)."""
        # Set up Redis to work correctly - first call succeeds, second detects duplicate
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.side_effect = [
            True,
            False,
        ]  # First new, second duplicate
        # Second call gets cached result
        mock_redis_client.get.side_effect = [None, '{"status": "completed", "result": true}']
        mock_redis_client.set.return_value = True
        mock_redis_client.expire.return_value = True

        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        # Use fixed correlation_id to ensure identical messages
        correlation_id = uuid4()
        msg1 = create_test_message_with_id(correlation_id)
        msg2 = create_test_message_with_id(correlation_id)  # Identical message

        # Process first message
        result1 = await consumer.process_message_idempotently(msg1)

        # Process identical message (should be detected as duplicate)
        result2 = await consumer.process_message_idempotently(msg2)

        # First message should be processed normally
        assert result1 is True

        # Second identical message should be skipped (duplicate detection)
        assert result2 in [None, True]  # Depends on cached result

        # Handler should be called only once (for the first message, not the duplicate)
        assert notification_handler.handle_teacher_notification.call_count == 1

    @pytest.mark.asyncio
    async def test_different_messages_different_idempotency_keys(
        self, mock_settings: Settings
    ) -> None:
        """Test that different messages are both processed (no false duplicate detection)."""
        mock_redis_client = AsyncMock()
        mock_redis_client.set_if_not_exists.return_value = True  # Both are new messages
        mock_redis_client.get.return_value = None  # No cached results
        mock_redis_client.set.return_value = True
        mock_redis_client.expire.return_value = True

        notification_handler = AsyncMock(spec=NotificationHandler)

        consumer = NotificationEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=mock_redis_client,
        )

        # Process different messages with different correlation_ids
        msg1 = create_test_message("message-1")
        msg2 = create_test_message("message-2")  # Different correlation_id

        result1 = await consumer.process_message_idempotently(msg1)
        result2 = await consumer.process_message_idempotently(msg2)

        # Both different messages should be processed normally
        assert result1 is True
        assert result2 is True

        # Handler should be called for both different messages
        assert notification_handler.handle_teacher_notification.call_count == 2

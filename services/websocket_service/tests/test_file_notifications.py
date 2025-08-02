"""
Unit tests for WebSocket Service file notification features.

Tests the file event consumer and notification handler components.
"""

from __future__ import annotations

from typing import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1

from services.websocket_service.config import Settings
from services.websocket_service.implementations.file_event_consumer import FileEventConsumer
from services.websocket_service.implementations.file_notification_handler import (
    FileNotificationHandler,
)


class TestFileNotificationHandler:
    """Test suite for file notification handler."""

    @pytest.mark.asyncio
    async def test_handle_batch_file_added(self) -> None:
        """Test handling of BatchFileAddedV1 event."""
        redis_client = AsyncMock()
        handler = FileNotificationHandler(redis_client=redis_client)

        event = BatchFileAddedV1(
            batch_id="batch-123",
            file_upload_id="file-456",
            filename="test.pdf",
            user_id="user-789",
        )

        await handler.handle_batch_file_added(event)

        redis_client.publish_user_notification.assert_called_once_with(
            user_id="user-789",
            event_type="batch_file_added",
            data={
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "timestamp": event.timestamp.isoformat(),
            },
        )

    @pytest.mark.asyncio
    async def test_handle_batch_file_removed(self) -> None:
        """Test handling of BatchFileRemovedV1 event."""
        redis_client = AsyncMock()
        handler = FileNotificationHandler(redis_client=redis_client)

        event = BatchFileRemovedV1(
            batch_id="batch-123",
            file_upload_id="file-456",
            filename="test.pdf",
            user_id="user-789",
        )

        await handler.handle_batch_file_removed(event)

        redis_client.publish_user_notification.assert_called_once_with(
            user_id="user-789",
            event_type="batch_file_removed",
            data={
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "timestamp": event.timestamp.isoformat(),
            },
        )

    @pytest.mark.asyncio
    async def test_handle_batch_file_added_error(self) -> None:
        """Test error handling in batch file added notification."""
        redis_client = AsyncMock()
        redis_client.publish_user_notification.side_effect = Exception("Redis error")
        handler = FileNotificationHandler(redis_client=redis_client)

        event = BatchFileAddedV1(
            batch_id="batch-123",
            file_upload_id="file-456",
            filename="test.pdf",
            user_id="user-789",
        )

        with pytest.raises(Exception, match="Redis error"):
            await handler.handle_batch_file_added(event)

    @pytest.mark.asyncio
    async def test_handle_batch_file_removed_error(self) -> None:
        """Test error handling in batch file removed notification."""
        redis_client = AsyncMock()
        redis_client.publish_user_notification.side_effect = Exception("Redis error")
        handler = FileNotificationHandler(redis_client=redis_client)

        event = BatchFileRemovedV1(
            batch_id="batch-123",
            file_upload_id="file-456",
            filename="test.pdf",
            user_id="user-789",
        )

        with pytest.raises(Exception, match="Redis error"):
            await handler.handle_batch_file_removed(event)


class TestFileEventConsumer:
    """Test suite for file event consumer."""

    @pytest.fixture
    def mock_settings(self) -> Settings:
        """Create mock settings for tests."""
        return Settings(
            BATCH_FILE_ADDED_TOPIC="file.batch.file.added.v1",
            BATCH_FILE_REMOVED_TOPIC="file.batch.file.removed.v1",
            KAFKA_BOOTSTRAP_SERVERS="localhost:9092",
            KAFKA_CONSUMER_GROUP="test-consumer",
            KAFKA_CONSUMER_CLIENT_ID="test-client",
        )

    @pytest.fixture
    def create_kafka_message(self) -> Callable[[str, dict], MagicMock]:
        """Factory for creating mock Kafka messages."""

        def _create_message(event_type: str, data: dict) -> MagicMock:
            import json
            
            message_data = {
                "event_id": "550e8400-e29b-41d4-a716-446655440000",
                "event_type": f"huleedu.{event_type}",  # Add huleedu prefix for proper routing
                "event_timestamp": "2024-01-01T12:00:00Z",
                "source_service": "file_service",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
                "data": data,
                "metadata": {},
            }

            msg = MagicMock(spec=ConsumerRecord)
            msg.value = json.dumps(message_data).encode("utf-8")  # Convert to bytes like real Kafka
            msg.topic = event_type
            msg.partition = 0
            msg.offset = 100
            return msg

        return _create_message

    @pytest.mark.asyncio
    async def test_process_batch_file_added_message(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test processing of batch file added event from Kafka."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a mock Kafka message
        msg = create_kafka_message(
            "file.batch.file.added.v1",
            {
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "user_id": "user-789",
                "timestamp": "2024-01-01T12:00:00Z",
            },
        )

        result = await consumer.process_message(msg)

        assert result is True
        notification_handler.handle_batch_file_added.assert_called_once()
        # Verify the event was properly constructed
        call_args = notification_handler.handle_batch_file_added.call_args[0][0]
        assert isinstance(call_args, BatchFileAddedV1)
        assert call_args.batch_id == "batch-123"
        assert call_args.file_upload_id == "file-456"
        assert call_args.filename == "test.pdf"
        assert call_args.user_id == "user-789"

    @pytest.mark.asyncio
    async def test_process_batch_file_removed_message(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test processing of batch file removed event from Kafka."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a mock Kafka message
        msg = create_kafka_message(
            "file.batch.file.removed.v1",
            {
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "user_id": "user-789",
                "timestamp": "2024-01-01T12:00:00Z",
            },
        )

        result = await consumer.process_message(msg)

        assert result is True
        notification_handler.handle_batch_file_removed.assert_called_once()
        # Verify the event was properly constructed
        call_args = notification_handler.handle_batch_file_removed.call_args[0][0]
        assert isinstance(call_args, BatchFileRemovedV1)
        assert call_args.batch_id == "batch-123"
        assert call_args.file_upload_id == "file-456"
        assert call_args.filename == "test.pdf"
        assert call_args.user_id == "user-789"

    @pytest.mark.asyncio
    async def test_process_unknown_event_type(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test processing of unknown event type."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create a mock Kafka message with unknown event type
        msg = create_kafka_message("unknown.event.v1", {})

        result = await consumer.process_message(msg)

        assert result is False
        notification_handler.handle_batch_file_added.assert_not_called()
        notification_handler.handle_batch_file_removed.assert_not_called()

    @pytest.mark.asyncio
    async def test_process_message_with_trace_context(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test that trace context is extracted from event metadata."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        # Create message data with trace context metadata
        import json
        message_data = {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": "huleedu.file.batch.file.added.v1",
            "event_timestamp": "2024-01-01T12:00:00Z",
            "source_service": "file_service",
            "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
            "data": {
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "user_id": "user-789",
                "timestamp": "2024-01-01T12:00:00Z",
            },
            "metadata": {
                "traceparent": "00-1234567890abcdef1234567890abcdef-1234567890abcdef-01"
            },
        }
        
        msg = MagicMock(spec=ConsumerRecord)
        msg.value = json.dumps(message_data).encode("utf-8")
        msg.topic = "file.batch.file.added.v1"
        msg.partition = 0
        msg.offset = 100

        result = await consumer.process_message(msg)

        assert result is True
        notification_handler.handle_batch_file_added.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_message_handles_notification_error(
        self, mock_settings: Settings, create_kafka_message: Callable[[str, dict], MagicMock]
    ) -> None:
        """Test that process_message handles errors from notification handler."""
        notification_handler = AsyncMock()
        notification_handler.handle_batch_file_added.side_effect = Exception("Handler error")
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
            settings=mock_settings,
            notification_handler=notification_handler,
            redis_client=redis_client,
        )

        msg = create_kafka_message(
            "file.batch.file.added.v1",
            {
                "batch_id": "batch-123",
                "file_upload_id": "file-456",
                "filename": "test.pdf",
                "user_id": "user-789",
                "timestamp": "2024-01-01T12:00:00Z",
            },
        )

        result = await consumer.process_message(msg)

        assert result is False
        notification_handler.handle_batch_file_added.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_consumer(self, mock_settings: Settings) -> None:
        """Test stopping the consumer gracefully."""
        notification_handler = AsyncMock()
        redis_client = AsyncMock()

        consumer = FileEventConsumer(
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

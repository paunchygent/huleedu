"""Integration tests for WebSocket Service Kafka Consumer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.file_management_events import BatchFileAddedV1, BatchFileRemovedV1
from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.websocket_service.config import Settings
from services.websocket_service.implementations.file_event_consumer import FileEventConsumer
from services.websocket_service.implementations.file_notification_handler import (
    FileNotificationHandler,
)


@pytest.fixture
def mock_settings() -> Settings:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    settings.KAFKA_CONSUMER_GROUP = "test-consumer-group"
    settings.KAFKA_CONSUMER_CLIENT_ID = "test-client"
    settings.BATCH_FILE_ADDED_TOPIC = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    settings.BATCH_FILE_REMOVED_TOPIC = topic_name(ProcessingEvent.BATCH_FILE_REMOVED)
    return settings


@pytest.fixture
def mock_redis_client() -> AsyncMock:
    """Create mock Redis client."""
    return AsyncMock(spec=AtomicRedisClientProtocol)


@pytest.fixture
def notification_handler(mock_redis_client: AsyncMock) -> FileNotificationHandler:
    """Create file notification handler."""
    return FileNotificationHandler(redis_client=mock_redis_client)


@pytest.fixture
def file_event_consumer(
    mock_settings: Settings,
    notification_handler: FileNotificationHandler,
    mock_redis_client: AsyncMock,
) -> FileEventConsumer:
    """Create file event consumer."""
    return FileEventConsumer(
        settings=mock_settings,
        notification_handler=notification_handler,
        redis_client=mock_redis_client,
    )


def create_batch_file_added_event(
    batch_id: str = "batch-123",
    user_id: str = "user-456",
    file_upload_id: str = "file-789",
    filename: str = "essay.pdf",
) -> EventEnvelope[BatchFileAddedV1]:
    """Create a batch file added event for testing."""
    return EventEnvelope[BatchFileAddedV1](
        event_id=uuid4(),
        event_type="huleedu.file.batch.file.added.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file_service",
        data=BatchFileAddedV1(
            batch_id=batch_id,
            user_id=user_id,
            file_upload_id=file_upload_id,
            filename=filename,
        ),
    )


def create_batch_file_removed_event(
    batch_id: str = "batch-123",
    user_id: str = "user-456",
    file_upload_id: str = "file-789",
    filename: str = "essay.pdf",
) -> EventEnvelope[BatchFileRemovedV1]:
    """Create a batch file removed event for testing."""
    return EventEnvelope[BatchFileRemovedV1](
        event_id=uuid4(),
        event_type="huleedu.file.batch.file.removed.v1",
        event_timestamp=datetime.now(timezone.utc),
        source_service="file_service",
        data=BatchFileRemovedV1(
            batch_id=batch_id,
            user_id=user_id,
            file_upload_id=file_upload_id,
            filename=filename,
        ),
    )


@pytest.mark.asyncio
async def test_process_batch_file_added_message(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test processing batch file added messages."""
    # Create test event
    event = create_batch_file_added_event()

    # Create mock Kafka message
    mock_message = MagicMock()
    mock_message.value = event.model_dump_json().encode("utf-8")  # Convert to bytes
    mock_message.topic = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    mock_message.partition = 0
    mock_message.offset = 100

    # Process the message
    result = await file_event_consumer.process_message(mock_message)

    assert result is True

    # Verify Redis publish was called with correct notification
    mock_redis_client.publish_user_notification.assert_called_once()

    # Check the call arguments
    call_kwargs = mock_redis_client.publish_user_notification.call_args.kwargs
    assert call_kwargs["user_id"] == "user-456"
    assert call_kwargs["event_type"] == "batch_file_added"

    notification_data = call_kwargs["data"]
    assert notification_data["batch_id"] == "batch-123"
    assert notification_data["file_upload_id"] == "file-789"
    assert notification_data["filename"] == "essay.pdf"


@pytest.mark.asyncio
async def test_process_batch_file_removed_message(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test processing batch file removed messages."""
    # Create test event
    event = create_batch_file_removed_event()

    # Create mock Kafka message
    mock_message = MagicMock()
    mock_message.value = event.model_dump_json().encode("utf-8")  # Convert to bytes
    mock_message.topic = topic_name(ProcessingEvent.BATCH_FILE_REMOVED)
    mock_message.partition = 0
    mock_message.offset = 100

    # Process the message
    result = await file_event_consumer.process_message(mock_message)

    assert result is True

    # Verify Redis publish was called with correct notification
    mock_redis_client.publish_user_notification.assert_called_once()

    # Check the call arguments
    call_kwargs = mock_redis_client.publish_user_notification.call_args.kwargs
    assert call_kwargs["user_id"] == "user-456"
    assert call_kwargs["event_type"] == "batch_file_removed"

    notification_data = call_kwargs["data"]
    assert notification_data["batch_id"] == "batch-123"
    assert notification_data["file_upload_id"] == "file-789"
    assert notification_data["filename"] == "essay.pdf"


@pytest.mark.asyncio
async def test_process_message_with_invalid_event_structure(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test handling messages with invalid event structure."""
    # Create mock message with invalid structure (missing required fields)
    mock_message = MagicMock()
    mock_message.value = {
        "event_type": "file.batch.file.added.v1",
        "event_id": str(uuid4()),
        # Missing "data" field which is required
    }
    mock_message.topic = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    mock_message.partition = 0
    mock_message.offset = 100

    # Process should return False and not raise exception
    result = await file_event_consumer.process_message(mock_message)

    assert result is False

    # Verify Redis publish was not called
    mock_redis_client.publish_user_notification.assert_not_called()


@pytest.mark.asyncio
async def test_process_message_with_unknown_event_type(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test handling messages with unknown event types."""
    # Create test event but with unknown event type
    event = create_batch_file_added_event()
    envelope_dict = json.loads(event.model_dump_json())
    envelope_dict["event_type"] = "unknown.event.type.v1"

    # Create mock message
    mock_message = MagicMock()
    mock_message.value = json.dumps(envelope_dict).encode("utf-8")  # Convert to bytes
    mock_message.topic = "unknown.topic"
    mock_message.partition = 0
    mock_message.offset = 100

    # Process should return False
    result = await file_event_consumer.process_message(mock_message)

    assert result is False

    # Verify Redis publish was not called
    mock_redis_client.publish_user_notification.assert_not_called()


@pytest.mark.asyncio
async def test_process_message_with_trace_context(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test processing messages with trace context metadata."""
    # Create test event with trace context
    event = create_batch_file_added_event()
    envelope_dict = json.loads(event.model_dump_json())
    envelope_dict["metadata"] = {
        "trace_id": "abc123",
        "span_id": "def456",
        "trace_flags": "01",
    }

    # Create mock message
    mock_message = MagicMock()
    mock_message.value = json.dumps(envelope_dict).encode("utf-8")  # Convert to bytes
    mock_message.topic = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    mock_message.partition = 0
    mock_message.offset = 100

    # Process the message
    result = await file_event_consumer.process_message(mock_message)

    assert result is True

    # Verify Redis publish was called
    mock_redis_client.publish_user_notification.assert_called_once()


@pytest.mark.asyncio
async def test_process_message_with_notification_handler_error(
    file_event_consumer: FileEventConsumer,
    mock_redis_client: AsyncMock,
) -> None:
    """Test handling when notification handler raises an error."""
    # Create test event
    event = create_batch_file_added_event()

    # Create mock message
    mock_message = MagicMock()
    mock_message.value = event.model_dump_json().encode("utf-8")  # Convert to bytes
    mock_message.topic = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    mock_message.partition = 0
    mock_message.offset = 100

    # Set up Redis to fail on publish
    mock_redis_client.publish_user_notification.side_effect = Exception("Redis error")

    # Process should return False due to error
    result = await file_event_consumer.process_message(mock_message)

    assert result is False

    # Verify publish was attempted
    mock_redis_client.publish_user_notification.assert_called_once()


@pytest.mark.asyncio
async def test_consumer_lifecycle_with_mock_factory() -> None:
    """Test consumer start and stop lifecycle using proper DI."""
    # Create mock consumer
    mock_consumer = AsyncMock()
    mock_consumer.start = AsyncMock()
    mock_consumer.stop = AsyncMock()

    # Create a mock consumer factory that returns our mock consumer
    def mock_kafka_consumer_factory(*args: Any, **kwargs: Any) -> AsyncMock:
        return mock_consumer

    # Create settings and dependencies
    settings = MagicMock(spec=Settings)
    settings.KAFKA_BOOTSTRAP_SERVERS = "localhost:9092"
    settings.KAFKA_CONSUMER_GROUP = "test-consumer-group"
    settings.KAFKA_CONSUMER_CLIENT_ID = "test-client"
    settings.BATCH_FILE_ADDED_TOPIC = topic_name(ProcessingEvent.BATCH_FILE_ADDED)
    settings.BATCH_FILE_REMOVED_TOPIC = topic_name(ProcessingEvent.BATCH_FILE_REMOVED)

    mock_redis_client = AsyncMock(spec=AtomicRedisClientProtocol)
    notification_handler = FileNotificationHandler(redis_client=mock_redis_client)

    # Create file event consumer with mock factory
    file_event_consumer = FileEventConsumer(
        settings=settings,
        notification_handler=notification_handler,
        redis_client=mock_redis_client,
        kafka_consumer_factory=mock_kafka_consumer_factory,
    )

    # Make the consumer async iterable but immediately stop
    async def mock_anext() -> None:
        # Set should_stop to True so the loop exits
        file_event_consumer.should_stop = True
        # Raise StopAsyncIteration to end the iteration
        raise StopAsyncIteration

    # Make mock_consumer an async iterable
    mock_consumer.__aiter__.return_value = mock_consumer
    mock_consumer.__anext__ = mock_anext

    # Start the consumer
    await file_event_consumer.start_consumer()

    # Verify consumer was started
    mock_consumer.start.assert_called_once()

    # Stop the consumer
    await file_event_consumer.stop_consumer()

    # Verify consumer was stopped
    mock_consumer.stop.assert_called()
    assert file_event_consumer.should_stop is True

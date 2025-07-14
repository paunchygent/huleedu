"""
Unit tests for the idempotency decorator.

Tests duplicate event detection, error handling, and Redis key management.
Uses real handler functions instead of mocks to follow testing best practices.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer_v2


# Real handler functions for testing (not mocks)
class HandlerCallTracker:
    """Track handler calls for test verification without mocking business logic."""

    def __init__(self) -> None:
        self.call_count = 0
        self.last_call_args: tuple = ()
        self.last_call_kwargs: dict = {}

    def reset(self) -> None:
        """Reset call tracking."""
        self.call_count = 0
        self.last_call_args = ()
        self.last_call_kwargs = {}


async def successful_handler(msg: ConsumerRecord, *args, **kwargs) -> str:
    """Real handler that simulates successful message processing."""
    return f"processed_offset_{msg.offset}"


async def failing_handler(msg: ConsumerRecord, *args, **kwargs) -> str:
    """Real handler that simulates processing failure."""
    raise Exception("Processing failed")


async def tracked_handler(msg: ConsumerRecord, tracker: HandlerCallTracker, *args, **kwargs) -> str:
    """Real handler that tracks calls for test verification."""
    tracker.call_count += 1
    tracker.last_call_args = (msg,) + args
    tracker.last_call_kwargs = kwargs
    return f"tracked_result_{msg.offset}"


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False
        self.should_fail_delete = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, value, ttl_seconds))

        if self.should_fail_set:
            raise RuntimeError("Mock Redis SET failure")

        if key in self.keys:
            return False  # Key already exists (duplicate)

        self.keys[key] = value
        return True  # Key was set (first time)

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
        self.delete_calls.append(key)

        if self.should_fail_delete:
            raise RuntimeError("Mock Redis DELETE failure")

        if key in self.keys:
            del self.keys[key]
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        """Mock GET operation that retrieves values."""
        return self.keys.get(key)

    async def setex(self, key: str, ttl_seconds: int, value: str) -> bool:
        """Mock SETEX operation that sets values with TTL."""
        self.keys[key] = value
        return True

    async def ping(self) -> bool:
        """Mock PING operation required by RedisClientProtocol."""
        return True


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    # Ensure event_data has required fields for v2 API
    if "event_type" not in event_data:
        event_data["event_type"] = "test.event.v1"
    if "event_id" not in event_data:
        event_data["event_id"] = str(uuid.uuid4())
    if "source_service" not in event_data:
        event_data["source_service"] = "test-service"

    message_json = json.dumps(event_data)
    return ConsumerRecord(
        topic="test-topic",
        partition=0,
        offset=123,
        timestamp=int(datetime.now(UTC).timestamp() * 1000),
        timestamp_type=1,
        key=b"test-key",
        value=message_json.encode("utf-8"),
        headers=[],
        checksum=None,
        serialized_key_size=8,
        serialized_value_size=len(message_json),
    )


@pytest.fixture
def mock_redis_client() -> MockRedisClient:
    """Provide a mock Redis client for tests."""
    return MockRedisClient()


@pytest.fixture
def sample_event_data() -> dict:
    """Provide sample Kafka event data for testing."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "test.event.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "test-service",
        "correlation_id": str(uuid.uuid4()),
        "data": {"test_field": "test_value", "batch_id": "test-batch-123"},
    }


@pytest.mark.asyncio
async def test_first_time_event_processing(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that first-time events are processed normally."""
    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create call tracker for verification
    tracker = HandlerCallTracker()

    # Create idempotency config for v2 API
    config = IdempotencyConfig(
        service_name="test-service", default_ttl=3600, enable_debug_logging=True
    )

    # Apply decorator to real handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord, *args, **kwargs) -> str:
        return await tracked_handler(msg, tracker, *args, **kwargs)

    # Process message
    result = await handler(kafka_msg, "extra_arg", keyword_arg="test")

    # Assertions
    assert result == f"tracked_result_{kafka_msg.offset}"
    assert len(mock_redis_client.set_calls) == 1
    assert len(mock_redis_client.delete_calls) == 0

    # Verify Redis key format (v2 format: huleedu:idempotency:v2:{service}:{event_type}:{hash})
    set_call = mock_redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:idempotency:v2:test-service:test_event_v1:")
    # Verify the value is JSON metadata (not just "1")
    import json

    value_data = json.loads(set_call[1])
    assert "processed_at" in value_data
    assert value_data["processed_by"] == "test-service"
    assert set_call[2] == 3600

    # Verify handler was called with correct arguments
    assert tracker.call_count == 1
    assert tracker.last_call_args[0] == kafka_msg
    assert tracker.last_call_args[1] == "extra_arg"
    assert tracker.last_call_kwargs == {"keyword_arg": "test"}


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that duplicate events are skipped without processing."""
    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Pre-populate Redis with the event key to simulate duplicate
    from huleedu_service_libs.event_utils import generate_deterministic_event_id

    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    # Use v2 key format: huleedu:idempotency:v2:{service}:{event_type}:{hash}
    redis_key = config.generate_redis_key(
        "test.event.v1", sample_event_data["event_id"], deterministic_id
    )
    mock_redis_client.keys[redis_key] = '{"processed_at": 1234567890}'

    # Create call tracker for verification
    tracker = HandlerCallTracker()

    # Apply decorator to real handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await tracked_handler(msg, tracker)

    # Process message
    result = await handler(kafka_msg)

    # Assertions
    assert result is None  # Should return None for duplicates
    assert len(mock_redis_client.set_calls) == 1  # SETNX was attempted
    assert len(mock_redis_client.delete_calls) == 0  # No cleanup needed

    # Handler should NOT have been called
    assert tracker.call_count == 0


@pytest.mark.asyncio
async def test_processing_failure_releases_lock(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that processing failures release the idempotency lock for retry."""
    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Apply decorator to real failing handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await failing_handler(msg)

    # Process message and expect exception
    with pytest.raises(Exception, match="Processing failed"):
        await handler(kafka_msg)

    # Assertions
    assert len(mock_redis_client.set_calls) == 1  # SETNX was attempted
    assert len(mock_redis_client.delete_calls) == 1  # Key was deleted for retry

    # Verify Redis key was deleted (v2 format)
    delete_call = mock_redis_client.delete_calls[0]
    assert delete_call.startswith("huleedu:idempotency:v2:test-service:test_event_v1:")


@pytest.mark.asyncio
async def test_redis_set_failure_fallback(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that Redis SET failures fall back to processing without idempotency."""
    # Configure Redis client to fail on SET
    mock_redis_client.should_fail_set = True

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Apply decorator to real handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await successful_handler(msg)

    # Process message - should succeed despite Redis failure
    result = await handler(kafka_msg)

    # Assertions
    assert result == f"processed_offset_{kafka_msg.offset}"
    assert len(mock_redis_client.set_calls) == 1  # SETNX was attempted
    assert len(mock_redis_client.delete_calls) == 0  # No cleanup needed


@pytest.mark.asyncio
async def test_redis_delete_failure_logged(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that Redis DELETE failures are logged but don't prevent exception propagation."""
    # Configure Redis client to fail on DELETE
    mock_redis_client.should_fail_delete = True

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Apply decorator to real failing handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await failing_handler(msg)

    # Process message and expect original exception
    with pytest.raises(Exception, match="Processing failed"):
        await handler(kafka_msg)

    # Assertions
    assert len(mock_redis_client.set_calls) == 1  # SETNX was attempted
    assert len(mock_redis_client.delete_calls) == 1  # DELETE was attempted


@pytest.mark.asyncio
async def test_default_ttl_applied(
    mock_redis_client: MockRedisClient,
    sample_event_data: dict,
) -> None:
    """Test that default TTL (24 hours) is applied when not specified."""
    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_event_data)

    # Create idempotency config without specifying TTL (uses default)
    config = IdempotencyConfig(
        service_name="test-service"
        # default_ttl not specified, should use DEFAULT_TTL_SECONDS (86400)
    )

    # Apply decorator
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await successful_handler(msg)

    # Process message
    result = await handler(kafka_msg)

    # Assertions
    assert result == f"processed_offset_{kafka_msg.offset}"
    assert len(mock_redis_client.set_calls) == 1

    # Verify default TTL (86400 seconds = 24 hours)
    set_call = mock_redis_client.set_calls[0]
    assert set_call[2] == 86400


@pytest.mark.asyncio
async def test_deterministic_key_generation(mock_redis_client: MockRedisClient) -> None:
    """Test that identical message content generates identical Redis keys."""
    # Create identical event payload (same event_id and data for true duplicate)
    fixed_event_id = str(uuid.uuid4())
    event_data = {
        "event_id": fixed_event_id,  # Same UUID for true duplicate
        "event_type": "test.event.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "test-service",
        "correlation_id": str(uuid.uuid4()),
        "data": {"test_field": "identical_value", "batch_id": "same-batch-123"},
    }

    # Create two messages with identical event_id and data (true duplicates)
    msg1 = create_mock_kafka_message(event_data.copy())
    msg2 = create_mock_kafka_message(event_data.copy())

    # Create call tracker for verification
    tracker = HandlerCallTracker()

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Apply decorator to real handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await tracked_handler(msg, tracker)

    # Process first message
    result1 = await handler(msg1)
    assert result1 == f"tracked_result_{msg1.offset}"

    # Process second message (should be detected as duplicate)
    result2 = await handler(msg2)
    assert result2 is None  # Should be None for duplicate

    # Verify both messages generated the same Redis key
    assert len(mock_redis_client.set_calls) == 2
    key1 = mock_redis_client.set_calls[0][0]
    key2 = mock_redis_client.set_calls[1][0]
    assert key1 == key2
    # Verify v2 key format
    assert key1.startswith("huleedu:idempotency:v2:test-service:test_event_v1:")

    # Handler should only be called once
    assert tracker.call_count == 1


@pytest.mark.asyncio
async def test_different_data_generates_different_keys(mock_redis_client: MockRedisClient) -> None:
    """Test that different message data generates different Redis keys."""
    # Create two different event payloads with different event_ids and data
    event_data_1 = {
        "event_id": str(uuid.uuid4()),
        "data": {"batch_id": "batch-1", "value": "different"},
    }
    event_data_2 = {
        "event_id": str(uuid.uuid4()),
        "data": {"batch_id": "batch-2", "value": "content"},
    }

    # Create messages
    msg1 = create_mock_kafka_message(event_data_1)
    msg2 = create_mock_kafka_message(event_data_2)

    # Create call tracker for verification
    tracker = HandlerCallTracker()

    # Create idempotency config for v2 API
    config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

    # Apply decorator to real handler
    @idempotent_consumer_v2(redis_client=mock_redis_client, config=config)
    async def handler(msg: ConsumerRecord) -> str:
        return await tracked_handler(msg, tracker)

    # Process both messages
    result1 = await handler(msg1)
    result2 = await handler(msg2)

    # Both should be processed (not duplicates)
    assert result1 == f"tracked_result_{msg1.offset}"
    assert result2 == f"tracked_result_{msg2.offset}"

    # Verify different Redis keys were generated
    assert len(mock_redis_client.set_calls) == 2
    key1 = mock_redis_client.set_calls[0][0]
    key2 = mock_redis_client.set_calls[1][0]
    assert key1 != key2
    # Both should use v2 key format
    assert key1.startswith("huleedu:idempotency:v2:test-service:test_event_v1:")
    assert key2.startswith("huleedu:idempotency:v2:test-service:test_event_v1:")

    # Handler should be called twice
    assert tracker.call_count == 2

"""
Unit tests for Essay Lifecycle Service idempotency integration.

Tests the idempotency decorator applied to ELS message processing.
Follows testing patterns: mock boundaries (Redis), not business logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord

from services.essay_lifecycle_service.batch_command_handlers import process_single_message
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    ServiceResultHandler,
)


class MockRedisClient:
    """Mock Redis client for testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int]] = []
        self.delete_calls: list[str] = []
        self.should_fail_set = False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock SETNX operation."""
        self.set_calls.append((key, value, ttl_seconds or 0))

        if self.should_fail_set:
            raise Exception("Redis connection failed")

        if key in self.keys:
            return False  # Key already exists

        self.keys[key] = value
        return True  # Key set successfully

    async def delete_key(self, key: str) -> int:
        """Mock DELETE operation."""
        self.delete_calls.append(key)
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


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    return ConsumerRecord(
        topic="test-topic",
        partition=0,
        offset=12345,
        timestamp=None,
        timestamp_type=None,
        key=None,
        value=json.dumps(event_data).encode("utf-8"),
        checksum=None,
        serialized_key_size=None,
        serialized_value_size=None,
        headers=[],
    )


@pytest.fixture
def sample_batch_registered_event() -> dict:
    """Sample batch registered event data."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.batch.essays.registered.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "batch_orchestrator_service",
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "event": "batch.essays.registered",
            "batch_id": "test-batch-001",
            "expected_essay_count": 3,
            "essay_ids": ["essay-1", "essay-2", "essay-3"],
            "metadata": {
                "entity": {"entity_id": "test-batch-001", "entity_type": "batch"},
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "batch.essays.registered",
            },
        },
    }


@pytest.fixture
def mock_handlers() -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    """Create mock handlers for testing (boundaries only)."""
    batch_coordination_handler = AsyncMock(spec=BatchCoordinationHandler)
    batch_command_handler = AsyncMock(spec=BatchCommandHandler)
    service_result_handler = AsyncMock(spec=ServiceResultHandler)

    # Configure successful business logic responses
    batch_coordination_handler.handle_batch_essays_registered.return_value = True
    batch_command_handler.process_initiate_spellcheck_command.return_value = None
    service_result_handler.handle_spellcheck_result.return_value = True

    return batch_coordination_handler, batch_command_handler, service_result_handler


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that first-time events are processed successfully with idempotency."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Apply idempotency decorator to real message processor
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is True  # Business logic succeeded
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Verify Redis key format
    set_call = redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:events:seen:")
    assert set_call[1] == "1"
    assert set_call[2] == 3600

    # Verify business logic was called
    batch_coordination_handler.handle_batch_essays_registered.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from common_core.events.utils import generate_deterministic_event_id
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Pre-populate Redis with the event key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is None  # Should return None for duplicates
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should NOT have been called
    batch_coordination_handler.handle_batch_essays_registered.assert_not_called()


@pytest.mark.asyncio
async def test_processing_failure_keeps_lock(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that business logic failures keep the idempotency lock (no retry)."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Configure business logic to fail
    batch_coordination_handler.handle_batch_essays_registered.side_effect = Exception(
        "Processing failed"
    )

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
        )

    # Process message - should return False for processing failure
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is False  # Processing failed, should return False
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # Key was NOT deleted (business logic failure)


@pytest.mark.asyncio
async def test_exception_failure_releases_lock(
    sample_batch_registered_event: dict,
) -> None:
    """Test that unhandled exceptions release the idempotency lock for retry."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Apply idempotency decorator to a function that raises an exception
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_with_exception(msg: ConsumerRecord) -> bool:
        raise RuntimeError("Unhandled exception (e.g., network failure)")

    # Process message - should raise exception
    with pytest.raises(RuntimeError, match="Unhandled exception"):
        await handle_message_with_exception(kafka_msg)

    # Assertions
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 1  # Key was deleted for retry

    # Verify Redis key was deleted
    delete_call = redis_client.delete_calls[0]
    assert delete_call.startswith("huleedu:events:seen:")


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that Redis failures fall back to processing without idempotency."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    redis_client.should_fail_set = True  # Force Redis failure
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
        )

    # Process message - should succeed despite Redis failure
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is True  # Business logic succeeded
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic was still called (fail-open)
    batch_coordination_handler.handle_batch_essays_registered.assert_called_once()


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock],
) -> None:
    """Test that identical message content generates identical Redis keys."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create two identical event payloads (same data content)
    event_data = {
        "event_id": str(uuid.uuid4()),  # Different UUID each time
        "event_type": "huleedu.batch.essays.registered.v1",  # Fixed: correct event type
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "batch_orchestrator_service",
        "correlation_id": str(uuid.uuid4()),  # Different UUID each time
        "data": {
            "event": "batch.essays.registered",
            "batch_id": "same-batch-123",  # Same data content
            "expected_essay_count": 2,
            "essay_ids": ["essay-1", "essay-2"],
            "metadata": {
                "entity": {"entity_id": "same-batch-123", "entity_type": "batch"},
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "batch.essays.registered",
            },
        },
    }

    # Create two messages with identical data content
    msg1 = create_mock_kafka_message(event_data)
    msg2 = create_mock_kafka_message(event_data)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=3600)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
        )

    # Process first message
    result1 = await handle_message_idempotently(msg1)
    assert result1 is True  # Should succeed

    # Process second message (should be detected as duplicate)
    result2 = await handle_message_idempotently(msg2)
    assert result2 is None  # Should be None for duplicate

    # Verify both messages generated the same Redis key
    assert len(redis_client.set_calls) == 2
    key1 = redis_client.set_calls[0][0]
    key2 = redis_client.set_calls[1][0]
    assert key1 == key2

    # Business logic should only be called once
    assert batch_coordination_handler.handle_batch_essays_registered.call_count == 1

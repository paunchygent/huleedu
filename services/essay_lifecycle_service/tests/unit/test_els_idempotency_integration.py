"""
Unit tests for Essay Lifecycle Service idempotency integration with v2 API.

Tests the v2 idempotency decorator applied to ELS message processing.
Follows testing patterns: mock boundaries (Redis), not business logic.
Migrated to v2 API with service namespacing and enhanced error handling.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.metadata_models import StorageReferenceMetadata

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

    async def delete(self, *keys: str) -> int:
        """Mock multi-key DELETE operation required by RedisClientProtocol."""
        total_deleted = 0
        for key in keys:
            deleted_count = await self.delete_key(key)
            total_deleted += deleted_count
        return total_deleted

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


def prompt_ref_json(storage_id: str) -> dict[str, Any]:
    """Create serialized StorageReferenceMetadata for prompts."""
    metadata = StorageReferenceMetadata()
    metadata.add_reference(ContentType.STUDENT_PROMPT_TEXT, storage_id)
    return metadata.model_dump(mode="json")


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
        "event_type": topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "batch_orchestrator_service",
        "correlation_id": str(uuid.uuid4()),
        "data": {
            "event": "batch.essays.registered",
            "entity_id": "test-batch-001",
            "expected_essay_count": 3,
            "essay_ids": ["essay-1", "essay-2", "essay-3"],
            "course_code": CourseCode.ENG5.value,
            "student_prompt_ref": prompt_ref_json("prompt-idempotency-fixture"),
            "user_id": "test_user_idempotency",
            "metadata": {
                "entity_id": "test-batch-001",
                "entity_type": "batch",
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

    return batch_coordination_handler, batch_command_handler, service_result_handler


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that first-time events are processed successfully with v2 idempotency."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Configure v2 idempotency with ELS service name
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator to real message processor
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=None,
            confirm_idempotency=confirm_idempotency,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is True  # Business logic succeeded
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Verify v2 Redis key format with service namespacing
    set_call = redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:idempotency:v2:essay-lifecycle-service:")
    # V2 stores JSON metadata instead of "1"
    import json

    stored_data = json.loads(set_call[1])
    # Transaction-aware v2: initial lock has 'started_at' and 'status': 'processing'
    assert "started_at" in stored_data
    assert "processed_by" in stored_data
    assert stored_data["processed_by"] == "essay-lifecycle-service"
    assert stored_data["status"] == "processing"
    # V2 uses TTL for processing lock phase (typically shorter than completion TTL)
    assert set_call[2] > 0  # TTL should be positive

    # Verify business logic was called
    batch_coordination_handler.handle_batch_essays_registered.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from huleedu_service_libs.event_utils import generate_deterministic_event_id
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Pre-populate Redis with the event key to simulate duplicate using v2 format
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    event_type = sample_batch_registered_event["event_type"]
    safe_event_type = event_type.replace(".", "_")
    # Store with transaction-aware format indicating completed status
    redis_client.keys[
        f"huleedu:idempotency:v2:essay-lifecycle-service:{safe_event_type}:{deterministic_id}"
    ] = json.dumps(
        {
            "status": "completed",
            "processed_at": 1640995200.0,
            "processed_by": "essay-lifecycle-service",
        }
    )

    # Configure v2 idempotency
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=None,
            confirm_idempotency=confirm_idempotency,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is None  # Should return None for duplicates
    # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
    assert len(redis_client.set_calls) == 0  # No SET attempted for duplicates
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should NOT have been called
    batch_coordination_handler.handle_batch_essays_registered.assert_not_called()


@pytest.mark.asyncio
async def test_processing_failure_keeps_lock(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that business logic failures keep the idempotency lock in v2 (ELS returns False)."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Configure business logic to fail (ELS catches exceptions and returns False)
    batch_coordination_handler.handle_batch_essays_registered.side_effect = Exception(
        "Processing failed"
    )

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Configure v2 idempotency
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=None,
            confirm_idempotency=confirm_idempotency,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    # Process message - ELS returns False for processing failures
    result = await handle_message_idempotently(kafka_msg)

    # Assertions - v2 preserves lock when function returns False (no exception)
    assert result is False  # Processing failed, ELS returns False
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # Key was NOT deleted (no exception raised)


@pytest.mark.asyncio
async def test_exception_failure_releases_lock(
    sample_batch_registered_event: dict,
) -> None:
    """Test that unhandled exceptions release the idempotency lock for retry in v2."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Configure v2 idempotency
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator to a function that raises an exception
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_with_exception(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool:
        raise RuntimeError("Unhandled exception (e.g., network failure)")

    # Process message - should raise exception
    with pytest.raises(RuntimeError, match="Unhandled exception"):
        await handle_message_with_exception(kafka_msg)

    # Assertions
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 1  # Key was deleted for retry

    # Verify v2 Redis key format was deleted
    delete_call = redis_client.delete_calls[0]
    assert delete_call.startswith("huleedu:idempotency:v2:essay-lifecycle-service:")


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_batch_registered_event: dict, mock_handlers: tuple[AsyncMock, AsyncMock, AsyncMock]
) -> None:
    """Test that Redis failures fall back to processing without idempotency in v2."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()
    redis_client.should_fail_set = True  # Force Redis failure
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_batch_registered_event)

    # Configure v2 idempotency
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=None,
            confirm_idempotency=confirm_idempotency,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

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
    """Test that identical message content generates identical Redis keys in v2."""
    from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

    redis_client = MockRedisClient()
    batch_coordination_handler, batch_command_handler, service_result_handler = mock_handlers

    # Create two identical event payloads (same data content)
    event_data = {
        "event_id": str(uuid.uuid4()),  # Different UUID each time
        "event_type": topic_name(
            ProcessingEvent.BATCH_ESSAYS_REGISTERED
        ),  # Fixed: correct event type
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "batch_orchestrator_service",
        "correlation_id": str(uuid.uuid4()),  # Different UUID each time
        "data": {
            "event": "batch.essays.registered",
            "entity_id": "same-batch-123",  # Same data content
            "expected_essay_count": 2,
            "essay_ids": ["essay-1", "essay-2"],
            "course_code": CourseCode.ENG5.value,
            "student_prompt_ref": prompt_ref_json("prompt-deterministic"),
            "user_id": "test_user_deterministic",
            "metadata": {
                "entity_id": "same-batch-123",
                "entity_type": "batch",
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "batch.essays.registered",
            },
        },
    }

    # Create two messages with identical data content
    msg1 = create_mock_kafka_message(event_data)
    msg2 = create_mock_kafka_message(event_data)

    # Configure v2 idempotency
    config = IdempotencyConfig(
        service_name="essay-lifecycle-service",
        default_ttl=3600,
        enable_debug_logging=True,
    )

    # Apply v2 idempotency decorator
    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Any]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=None,
            confirm_idempotency=confirm_idempotency,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    # Process first message
    result1 = await handle_message_idempotently(msg1)
    assert result1 is True  # Should succeed

    # Process second message (should be detected as duplicate)
    result2 = await handle_message_idempotently(msg2)
    assert result2 is None  # Should be None for duplicate

    # With transaction-aware pattern, only first message attempts SETNX
    # Second message detects duplicate via GET and doesn't attempt SETNX
    assert len(redis_client.set_calls) == 1  # Only first message sets key
    key1 = redis_client.set_calls[0][0]
    assert key1.startswith("huleedu:idempotency:v2:essay-lifecycle-service:")
    # V2 key format: huleedu:idempotency:v2:service:event_type:hash
    key_parts = key1.split(":")
    assert len(key_parts) == 6  # prefix:idempotency:v2:service:event_type:hash
    assert len(key_parts[5]) == 64  # SHA-256 hash is 64 chars

    # Business logic should only be called once
    assert batch_coordination_handler.handle_batch_essays_registered.call_count == 1

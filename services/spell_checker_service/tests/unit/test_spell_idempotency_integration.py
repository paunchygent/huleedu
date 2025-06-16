"""
Integration tests for idempotency in Spell Checker Service.

Tests the idempotency decorator applied to spell checking message processing.
Follows testing patterns: mock boundaries (Redis, HTTP, Kafka), not business logic.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord

from services.spell_checker_service.event_processor import process_single_message
from services.spell_checker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)


class MockRedisClient:
    """Mock Redis client for idempotency testing."""

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


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord for testing."""
    return ConsumerRecord(
        topic="huleedu.essay.spellcheck.requested.v1",
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
def sample_spellcheck_request_event() -> dict:
    """Sample spell check request event data."""
    essay_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event_name": "essay.spellcheck.requested",  # Required field
            "entity_ref": {
                "entity_id": essay_id,
                "entity_type": "essay"
            },
            "status": "awaiting_spellcheck",  # Required field
            "system_metadata": {
                "entity": {
                    "entity_id": essay_id,
                    "entity_type": "essay"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_stage": "pending",
                "event": "essay.spellcheck.requested"
            },
            "text_storage_id": "storage-123",
            "language": "en"
        }
    }


@pytest.fixture
def mock_boundary_services() -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock]:
    """Create mock boundary services (external dependencies only)."""
    # Mock HTTP session (infrastructure boundary)
    http_session = AsyncMock()

    # Mock content client (HTTP boundary)
    content_client = AsyncMock(spec=ContentClientProtocol)
    content_client.fetch_content.return_value = "This is a sample essay text "
    "with some misspelled words"

    # Mock result store (HTTP boundary)
    result_store = AsyncMock(spec=ResultStoreProtocol)
    result_store.store_content.return_value = "corrected-storage-456"

    # Mock event publisher (Kafka boundary)
    event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
    event_publisher.publish_spellcheck_result.return_value = None

    # Mock Kafka bus (Kafka boundary)
    kafka_bus = AsyncMock()

    return http_session, content_client, result_store, event_publisher, kafka_bus


@pytest.fixture
def real_spell_logic(
    mock_boundary_services:
    tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock]
    ) -> SpellLogicProtocol:
    """Create real spell logic implementation for testing business logic."""
    _, _, result_store, _, _ = mock_boundary_services

    # Import and use the real spell logic implementation
    from services.spell_checker_service.protocol_implementations.spell_logic_impl import (
        DefaultSpellLogic,
    )

    return DefaultSpellLogic(
        result_store=result_store,
        http_session=mock_boundary_services[0]  # http_session
    )


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol
) -> None:
    """Test that first-time spell check events are processed successfully with idempotency."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    # Apply idempotency decorator to real message processor
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,  # Real business logic
            kafka_bus=kafka_bus,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
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
    assert set_call[2] == 86400

    # Verify boundary services were called (real business logic executed)
    content_client.fetch_content.assert_called_once()  # Content was fetched
    result_store.store_content.assert_called_once()  # Corrected text was stored
    event_publisher.publish_spellcheck_result.assert_called_once()  # Success event published


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    from common_core.events.utils import generate_deterministic_event_id

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    # Pre-populate Redis with the event key to simulate duplicate
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            kafka_bus=kafka_bus,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is None  # Should return None for duplicates
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should NOT have been called
    content_client.fetch_content.assert_not_called()
    result_store.store_content.assert_not_called()
    event_publisher.publish_spellcheck_result.assert_not_called()


@pytest.mark.asyncio
async def test_processing_failure_keeps_lock(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol
) -> None:
    """Test that business logic failures keep Redis lock to prevent infinite retries."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services

    # Configure content client to fail (business logic failure)
    content_client.fetch_content.side_effect = Exception("Content service unavailable")

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            kafka_bus=kafka_bus,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions
    assert result is True  # Business logic handles failure gracefully
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 0  # Lock should be kept (no cleanup)

    # Failure event should be published
    event_publisher.publish_spellcheck_result.assert_called_once()


@pytest.mark.asyncio
async def test_exception_failure_releases_lock(
    sample_spellcheck_request_event: dict,
) -> None:
    """Test that unhandled exceptions release Redis lock to allow retry."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    # Create a handler that raises an exception (infrastructure failure)
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_with_exception(msg: ConsumerRecord) -> bool:
        raise RuntimeError("Unexpected infrastructure failure")

    # Process message and expect exception
    with pytest.raises(RuntimeError, match="Unexpected infrastructure failure"):
        await handle_message_with_exception(kafka_msg)

    # Assertions
    assert len(redis_client.set_calls) == 1  # SETNX was called
    assert len(redis_client.delete_calls) == 1  # Lock should be released for retry


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol
) -> None:
    """Test that Redis failures result in fail-open behavior."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services

    # Configure Redis to fail
    redis_client.should_fail_set = True

    # Create Kafka message
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            kafka_bus=kafka_bus,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

    # Process message
    result = await handle_message_idempotently(kafka_msg)

    # Assertions - Should process without idempotency protection
    assert result is True  # Business logic succeeded despite Redis failure
    assert len(redis_client.set_calls) == 1  # SETNX was attempted
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Business logic should have executed (fail-open)
    content_client.fetch_content.assert_called_once()
    result_store.store_content.assert_called_once()
    event_publisher.publish_spellcheck_result.assert_called_once()


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol
) -> None:
    """Test that deterministic event IDs are generated correctly for spell check events."""
    from huleedu_service_libs.idempotency import idempotent_consumer

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services

    # Create two identical events with same data but different envelope metadata
    base_event_data = {
        "event_name": "essay.spellcheck.requested",  # Required field
        "entity_ref": {"entity_id": "test-essay-123", "entity_type": "essay"},
        "status": "awaiting_spellcheck",  # Required field
        "system_metadata": {
            "entity": {"entity_id": "test-essay-123", "entity_type": "essay"},
            "timestamp": "2024-01-01T12:00:00Z",
            "processing_stage": "pending",
            "event": "essay.spellcheck.requested"
        },
        "text_storage_id": "storage-123",
        "language": "en"
    }

    # Event 1 - different envelope metadata
    event1 = {
        "event_id": str(uuid.uuid4()),  # Different
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",  # Different
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),  # Different
        "data": base_event_data  # Same data
    }

    # Event 2 - different envelope metadata but same data
    event2 = {
        "event_id": str(uuid.uuid4()),  # Different
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": "2024-01-01T13:00:00Z",  # Different
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),  # Different
        "data": base_event_data  # Same data
    }

    # Create Kafka messages
    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

    # Apply idempotency decorator
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
        return await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            kafka_bus=kafka_bus,
            consumer_group_id="test-group",
            kafka_queue_latency_metric=None,
        )

    # Process first message
    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True  # First message processed

    # Process second message (should be detected as duplicate)
    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None  # Second message skipped as duplicate

    # Verify Redis calls
    assert len(redis_client.set_calls) == 2  # Both attempted SETNX
    assert len(redis_client.delete_calls) == 0  # No cleanup needed

    # Verify same deterministic key was used for both
    key1 = redis_client.set_calls[0][0]
    key2 = redis_client.set_calls[1][0]
    assert key1 == key2  # Same deterministic key despite different envelope metadata
    assert key1.startswith("huleedu:events:seen:")
    assert len(key1.split(":")[3]) == 64  # SHA256 hash length

    # Business logic should only have been called once
    assert content_client.fetch_content.call_count == 1
    assert result_store.store_content.call_count == 1
    assert event_publisher.publish_spellcheck_result.call_count == 1

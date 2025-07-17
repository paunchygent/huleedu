"""
Integration tests for SpellCheckerKafkaConsumer with idempotency.

Tests the actual service class with idempotency decorator applied through DI.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiokafka import ConsumerRecord
from common_core.status_enums import EssayStatus

from services.spellchecker_service.kafka_consumer import SpellCheckerKafkaConsumer
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)


class MockRedisClient:
    """Mock Redis client for integration testing."""

    def __init__(self) -> None:
        self.keys: dict[str, str] = {}
        self.set_calls: list[tuple[str, str, int | None]] = []

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Mock Redis SETNX operation."""
        self.set_calls.append((key, value, ttl_seconds))
        if key in self.keys:
            return False
        self.keys[key] = value
        return True

    async def delete_key(self, key: str) -> int:
        """Mock Redis DELETE operation."""
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


def create_sample_spellcheck_event() -> dict:
    """Create sample spell check request event."""
    essay_id = str(uuid.uuid4())
    correlation_id = str(uuid.uuid4())

    return {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": datetime.now(UTC).isoformat(),
        "source_service": "essay_lifecycle_service",
        "correlation_id": correlation_id,
        "data": {
            "event_name": "essay.spellcheck.requested",
            "entity_ref": {"entity_id": essay_id, "entity_type": "essay"},
            "status": EssayStatus.AWAITING_SPELLCHECK.value,
            "text_storage_id": "storage-123",
            "language": "en",
            "system_metadata": {
                "entity": {"entity_id": essay_id, "entity_type": "essay"},
                "timestamp": datetime.now(UTC).isoformat(),
                "processing_stage": "pending",
                "event": "essay.spellcheck.requested",
            },
        },
    }


def create_mock_kafka_message(event_data: dict) -> ConsumerRecord:
    """Create a mock Kafka ConsumerRecord."""
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
def mock_dependencies() -> tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock]:
    """Create mock dependencies for SpellCheckerKafkaConsumer."""
    # Mock content client
    content_client = AsyncMock(spec=ContentClientProtocol)
    content_client.fetch_content.return_value = "This is a sampel essay with spelling erors."

    # Mock result store
    result_store = AsyncMock(spec=ResultStoreProtocol)
    result_store.store_content.return_value = "storage-result-123"  # Correct method name

    # Mock spell logic
    spell_logic = AsyncMock(spec=SpellLogicProtocol)
    # Use a MagicMock for the return value since it's a complex Pydantic model
    spell_result = MagicMock()
    spell_result.corrected_text_storage_id = "storage-corrected-123"
    spell_result.total_corrections_made = 2
    spell_logic.perform_spell_check.return_value = spell_result  # Correct method name

    # Mock event publisher
    event_publisher = AsyncMock(spec=SpellcheckEventPublisherProtocol)
    event_publisher.publish_spellcheck_result.return_value = None  # Correct method name

    # Mock Kafka bus
    kafka_bus = AsyncMock()

    # Mock HTTP session
    http_session = AsyncMock()

    return content_client, result_store, spell_logic, event_publisher, kafka_bus, http_session


@pytest.mark.asyncio
async def test_kafka_consumer_with_idempotency_first_time_processing(
    mock_dependencies: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test SpellCheckerKafkaConsumer processes first-time events with idempotency."""
    (
        content_client,
        result_store,
        spell_logic,
        event_publisher,
        kafka_bus,
        http_session,
    ) = mock_dependencies
    redis_client = MockRedisClient()

    # Create consumer instance with real DI integration
    consumer = SpellCheckerKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-group",
        consumer_client_id="test-client",
        content_client=content_client,
        result_store=result_store,
        spell_logic=spell_logic,
        event_publisher=event_publisher,
        kafka_bus=kafka_bus,
        http_session=http_session,
        redis_client=redis_client,  # Real Redis client integration
    )

    # Create test message
    event_data = create_sample_spellcheck_event()
    kafka_msg = create_mock_kafka_message(event_data)

    # Process message through the actual consumer's idempotent decorator
    result = await consumer._process_message_idempotently(kafka_msg)

    # Verify idempotency worked
    assert result is True  # Should return True for successful processing
    assert len(redis_client.set_calls) == 1  # Redis SETNX was called

    # Verify business logic was executed
    content_client.fetch_content.assert_called_once()
    spell_logic.perform_spell_check.assert_called_once()
    event_publisher.publish_spellcheck_result.assert_called_once()


@pytest.mark.asyncio
async def test_kafka_consumer_with_idempotency_duplicate_detection(
    mock_dependencies: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test SpellCheckerKafkaConsumer skips duplicate events."""
    (
        content_client,
        result_store,
        spell_logic,
        event_publisher,
        kafka_bus,
        http_session,
    ) = mock_dependencies
    redis_client = MockRedisClient()

    # Create consumer instance
    consumer = SpellCheckerKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-group",
        consumer_client_id="test-client",
        content_client=content_client,
        result_store=result_store,
        spell_logic=spell_logic,
        event_publisher=event_publisher,
        kafka_bus=kafka_bus,
        http_session=http_session,
        redis_client=redis_client,
    )

    # Create test message
    event_data = create_sample_spellcheck_event()
    kafka_msg = create_mock_kafka_message(event_data)

    # Process message first time
    result1 = await consumer._process_message_idempotently(kafka_msg)
    assert result1 is True  # First time should succeed

    # Process same message again (duplicate)
    result2 = await consumer._process_message_idempotently(kafka_msg)
    assert result2 is None  # Duplicate should return None

    # Verify Redis calls
    assert len(redis_client.set_calls) == 2  # Two SETNX attempts

    # Verify business logic was only called once
    assert content_client.fetch_content.call_count == 1
    assert spell_logic.perform_spell_check.call_count == 1
    assert event_publisher.publish_spellcheck_result.call_count == 1


@pytest.mark.asyncio
async def test_kafka_consumer_di_integration(
    mock_dependencies: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test that SpellCheckerKafkaConsumer correctly integrates with DI system."""
    (
        content_client,
        result_store,
        spell_logic,
        event_publisher,
        kafka_bus,
        http_session,
    ) = mock_dependencies
    redis_client = MockRedisClient()

    # Test that consumer can be instantiated with all dependencies
    consumer = SpellCheckerKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-group",
        consumer_client_id="test-client",
        content_client=content_client,
        result_store=result_store,
        spell_logic=spell_logic,
        event_publisher=event_publisher,
        kafka_bus=kafka_bus,
        http_session=http_session,
        redis_client=redis_client,
    )

    # Verify all dependencies are properly assigned
    assert consumer.content_client is content_client
    assert consumer.result_store is result_store
    assert consumer.spell_logic is spell_logic
    assert consumer.event_publisher is event_publisher
    assert consumer.kafka_bus is kafka_bus
    assert consumer.http_session is http_session
    assert consumer.redis_client is redis_client

    # Verify idempotent decorator was created
    assert hasattr(consumer, "_process_message_idempotently")
    assert callable(consumer._process_message_idempotently)


@pytest.mark.asyncio
async def test_kafka_consumer_business_failure_handling(
    mock_dependencies: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock, MagicMock],
) -> None:
    """Test SpellCheckerKafkaConsumer handles business failures correctly with idempotency."""
    (
        content_client,
        result_store,
        spell_logic,
        event_publisher,
        kafka_bus,
        http_session,
    ) = mock_dependencies
    redis_client = MockRedisClient()

    # Configure content client to fail (business logic failure)
    content_client.fetch_content.side_effect = Exception("Content service unavailable")

    # Create consumer instance
    consumer = SpellCheckerKafkaConsumer(
        kafka_bootstrap_servers="localhost:9092",
        consumer_group="test-group",
        consumer_client_id="test-client",
        content_client=content_client,
        result_store=result_store,
        spell_logic=spell_logic,
        event_publisher=event_publisher,
        kafka_bus=kafka_bus,
        http_session=http_session,
        redis_client=redis_client,
    )

    # Create test message
    event_data = create_sample_spellcheck_event()
    kafka_msg = create_mock_kafka_message(event_data)

    # Process message (should handle failure gracefully)
    result = await consumer._process_message_idempotently(kafka_msg)

    # Spell Checker Service returns True even for business failures
    # because it publishes failure events and considers the message "processed"
    assert result is True
    assert len(redis_client.set_calls) == 1  # Redis lock should be kept

    # Content client should have been called and failed
    content_client.fetch_content.assert_called_once()
    # Other components should not have been called due to early failure
    spell_logic.perform_spell_check.assert_not_called()
    # But failure event should have been published
    event_publisher.publish_spellcheck_result.assert_called_once()

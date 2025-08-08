"""
Basic idempotency tests for the Spell Checker Service.

- Tests successful first-time processing.
- Tests duplicate event skipping.
- Tests graceful handling of business logic failures.
- Tests deterministic key generation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.status_enums import EssayStatus
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.protocols import SpellLogicProtocol

from .spell_idempotency_test_utils import (
    MockRedisClient,
    create_mock_kafka_message,
)


@pytest.mark.asyncio
async def test_first_time_event_processing_success(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol,
) -> None:
    """Test that first-time spell check events are processed successfully with idempotency."""
    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    config = IdempotencyConfig(service_name="spell-checker-service")

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            consumer_group_id="test-group",
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result = await handle_message_idempotently(kafka_msg)

    assert result is True
    assert len(redis_client.set_calls) == 1
    assert len(redis_client.delete_calls) == 0
    set_call = redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:idempotency:v2:spell-checker-service:")
    assert "spell-checker-service" in set_call[0]
    assert set_call[2] > 0  # TTL should be positive
    content_client.fetch_content.assert_called_once()
    result_store.store_content.assert_called_once()
    event_publisher.publish_spellcheck_result.assert_called_once()


@pytest.mark.asyncio
async def test_duplicate_event_skipped(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol,
) -> None:
    """Test that duplicate events are skipped without processing business logic."""
    from huleedu_service_libs.event_utils import generate_deterministic_event_id

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    # Simulate v2 key format for duplicate detection
    v2_key = (
        f"huleedu:idempotency:v2:spell-checker-service:"
        f"huleedu_essay_spellcheck_requested_v1:{deterministic_id}"
    )
    # Store with transaction-aware format indicating completed status
    redis_client.keys[v2_key] = (
        '{"status": "completed", "processed_at": 1640995200, '
        '"processed_by": "spell-checker-service"}'
    )

    config = IdempotencyConfig(service_name="spell-checker-service")

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            consumer_group_id="test-group",
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result = await handle_message_idempotently(kafka_msg)

    assert result is None
    # With transaction-aware pattern, duplicate detection happens via GET, no SETNX attempted
    assert len(redis_client.set_calls) == 0  # No SET attempted for duplicates
    assert len(redis_client.delete_calls) == 0
    content_client.fetch_content.assert_not_called()
    result_store.store_content.assert_not_called()
    event_publisher.publish_spellcheck_result.assert_not_called()


@pytest.mark.asyncio
async def test_processing_failure_keeps_lock(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol,
) -> None:
    """Test that business logic failures keep Redis lock to prevent infinite retries."""
    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    content_client.fetch_content.side_effect = Exception("Content service unavailable")
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    config = IdempotencyConfig(service_name="spell-checker-service")

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            consumer_group_id="test-group",
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result = await handle_message_idempotently(kafka_msg)

    assert result is True
    assert len(redis_client.set_calls) == 1
    assert len(redis_client.delete_calls) == 0
    event_publisher.publish_spellcheck_result.assert_called_once()


@pytest.mark.asyncio
async def test_deterministic_event_id_generation(
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol,
) -> None:
    """Test that deterministic event IDs are generated correctly for spell check events."""
    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    base_event_data = {
        "event_name": "essay.spellcheck.requested",
        "entity_id": "test-essay-123",
        "entity_type": "essay",
        "parent_id": "test-batch-456",
        "status": EssayStatus.AWAITING_SPELLCHECK.value,
        "system_metadata": {
            "entity_id": "test-essay-123",
            "entity_type": "essay",
            "parent_id": "test-batch-456",
            "timestamp": "2024-01-01T12:00:00Z",
            "processing_stage": "pending",
            "event": "essay.spellcheck.requested",
        },
        "text_storage_id": "storage-123",
        "language": "en",
    }
    # Use the same event_id to test true duplicate detection (retry scenario)
    shared_event_id = str(uuid.uuid4())
    event1 = {
        "event_id": shared_event_id,
        "event_type": topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }
    event2 = {
        "event_id": shared_event_id,  # Same event_id = same event (retry)
        "event_type": topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
        "event_timestamp": "2024-01-01T13:00:00Z",  # Different timestamp (retry delay)
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }
    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

    config = IdempotencyConfig(service_name="spell-checker-service")

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool | None:
        result = await process_single_message(
            msg=msg,
            http_session=http_session,
            content_client=content_client,
            result_store=result_store,
            event_publisher=event_publisher,
            spell_logic=real_spell_logic,
            consumer_group_id="test-group",
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True

    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None

    # With transaction-aware pattern, only first message attempts SETNX
    # Second message detects duplicate via GET and doesn't attempt SETNX
    assert len(redis_client.set_calls) == 1  # Only first message sets key
    assert len(redis_client.delete_calls) == 0

    key1 = redis_client.set_calls[0][0]
    assert key1.startswith("huleedu:idempotency:v2:spell-checker-service:")
    assert "huleedu_essay_spellcheck_requested_v1" in key1
    # V2 keys have format: prefix:service:event_type:hash
    assert len(key1.split(":")[-1]) == 64

    assert content_client.fetch_content.call_count == 1
    assert result_store.store_content.call_count == 1
    assert event_publisher.publish_spellcheck_result.call_count == 1

"""
Basic idempotency tests for the Spell Checker Service.

- Tests successful first-time processing.
- Tests duplicate event skipping.
- Tests graceful handling of business logic failures.
- Tests deterministic key generation.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.idempotency import idempotent_consumer

from common_core.status_enums import EssayStatus
from services.spell_checker_service.event_processor import process_single_message
from services.spell_checker_service.protocols import SpellLogicProtocol

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
        )

    result = await handle_message_idempotently(kafka_msg)

    assert result is True
    assert len(redis_client.set_calls) == 1
    assert len(redis_client.delete_calls) == 0
    set_call = redis_client.set_calls[0]
    assert set_call[0].startswith("huleedu:events:seen:")
    assert set_call[1] == "1"
    assert set_call[2] == 86400
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
    from common_core.events.utils import generate_deterministic_event_id

    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)
    deterministic_id = generate_deterministic_event_id(kafka_msg.value)
    redis_client.keys[f"huleedu:events:seen:{deterministic_id}"] = "1"

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
        )

    result = await handle_message_idempotently(kafka_msg)

    assert result is None
    assert len(redis_client.set_calls) == 1
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
        )

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
        "entity_ref": {"entity_id": "test-essay-123", "entity_type": "essay"},
        "status": EssayStatus.AWAITING_SPELLCHECK.value,
        "system_metadata": {
            "entity": {"entity_id": "test-essay-123", "entity_type": "essay"},
            "timestamp": "2024-01-01T12:00:00Z",
            "processing_stage": "pending",
            "event": "essay.spellcheck.requested",
        },
        "text_storage_id": "storage-123",
        "language": "en",
    }
    event1 = {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": "2024-01-01T12:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }
    event2 = {
        "event_id": str(uuid.uuid4()),
        "event_type": "huleedu.essay.spellcheck.requested.v1",
        "event_timestamp": "2024-01-01T13:00:00Z",
        "source_service": "essay_lifecycle_service",
        "correlation_id": str(uuid.uuid4()),
        "data": base_event_data,
    }
    kafka_msg1 = create_mock_kafka_message(event1)
    kafka_msg2 = create_mock_kafka_message(event2)

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
        )

    result1 = await handle_message_idempotently(kafka_msg1)
    assert result1 is True

    result2 = await handle_message_idempotently(kafka_msg2)
    assert result2 is None

    assert len(redis_client.set_calls) == 2
    assert len(redis_client.delete_calls) == 0

    key1 = redis_client.set_calls[0][0]
    key2 = redis_client.set_calls[1][0]
    assert key1 == key2
    assert key1.startswith("huleedu:events:seen:")
    assert len(key1.split(":")[3]) == 64

    assert content_client.fetch_content.call_count == 1
    assert result_store.store_content.call_count == 1
    assert event_publisher.publish_spellcheck_result.call_count == 1

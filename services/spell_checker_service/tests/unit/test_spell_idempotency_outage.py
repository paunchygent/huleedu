"""
Idempotency tests for outage and failure scenarios in the Spell Checker Service.

- Tests lock release on unhandled exceptions.
- Tests fail-open behavior when Redis is unavailable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.idempotency import idempotent_consumer

from services.spell_checker_service.event_processor import process_single_message
from services.spell_checker_service.protocols import SpellLogicProtocol

from .spell_idempotency_test_utils import (
    MockRedisClient,
    create_mock_kafka_message,
)


@pytest.mark.asyncio
async def test_exception_failure_releases_lock(
    sample_spellcheck_request_event: dict,
) -> None:
    """Test that unhandled exceptions release Redis lock to allow retry."""
    redis_client = MockRedisClient()
    kafka_msg = create_mock_kafka_message(sample_spellcheck_request_event)

    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_with_exception(msg: ConsumerRecord) -> bool:
        raise RuntimeError("Unexpected infrastructure failure")

    with pytest.raises(RuntimeError, match="Unexpected infrastructure failure"):
        await handle_message_with_exception(kafka_msg)

    assert len(redis_client.set_calls) == 1
    assert len(redis_client.delete_calls) == 1


@pytest.mark.asyncio
async def test_redis_failure_fallback(
    sample_spellcheck_request_event: dict,
    mock_boundary_services: tuple[AsyncMock, AsyncMock, AsyncMock, AsyncMock, AsyncMock],
    real_spell_logic: SpellLogicProtocol,
) -> None:
    """Test that Redis failures result in fail-open behavior."""
    redis_client = MockRedisClient()
    http_session, content_client, result_store, event_publisher, kafka_bus = mock_boundary_services
    redis_client.should_fail_set = True
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
    content_client.fetch_content.assert_called_once()
    result_store.store_content.assert_called_once()
    event_publisher.publish_spellcheck_result.assert_called_once()

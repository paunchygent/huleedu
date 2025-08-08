"""
Idempotency tests for outage and failure scenarios in the Spell Checker Service.

- Tests lock release on unhandled exceptions.
- Tests fail-open behavior when Redis is unavailable.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from services.spellchecker_service.event_processor import process_single_message
from services.spellchecker_service.protocols import SpellLogicProtocol

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

    config = IdempotencyConfig(service_name="spell-checker-service")

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_with_exception(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Coroutine[Any, Any, None]]
    ) -> bool:
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
    # With transaction-aware pattern, GET is attempted first and fails
    # No SET operation occurs when GET fails during outage
    assert len(redis_client.set_calls) == 0  # No SET attempted during outage
    assert len(redis_client.delete_calls) == 0
    content_client.fetch_content.assert_called_once()
    result_store.store_content.assert_called_once()
    event_publisher.publish_spellcheck_result.assert_called_once()

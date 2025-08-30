from __future__ import annotations

import pytest
from aiokafka import ConsumerRecord

from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from ._helpers_idempotency import create_mock_kafka_message


class TestIdempotentConsumerTTLBehavior:
    """Tests TTL selection for processing and completion states."""

    @pytest.mark.asyncio
    async def test_idempotent_consumer_processing_state_uses_short_ttl(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """Initial processing state must use 300s TTL to allow recovery from crashes."""
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)
        config = IdempotencyConfig(service_name="test-service")

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            await confirm_idempotency()
            return "ok"

        res = await handler(msg)
        assert res == "ok"
        assert len(mock_redis_client.set_calls) == 1
        assert mock_redis_client.set_calls[0][2] == 300

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "event_type, expected_ttl",
        [
            ("huleedu.essay.spellcheck.completed.v1", 3600),
            ("huleedu.result_aggregator.batch.completed.v1", 259200),
        ],
    )
    async def test_idempotent_consumer_completion_sets_event_type_specific_ttl(
        self, mock_redis_client, sample_event_data, event_type, expected_ttl
    ) -> None:
        """After confirm_idempotency, decorator must set completed state with event-type TTL."""
        data = sample_event_data.copy()
        data["event_type"] = event_type
        msg: ConsumerRecord = create_mock_kafka_message(data)
        config = IdempotencyConfig(service_name="test-service")

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            await confirm_idempotency()
            return "ok"

        res = await handler(msg)
        assert res == "ok"
        # One processing SET and one completion SETEX
        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.setex_calls) == 1
        key, ttl, _ = mock_redis_client.setex_calls[0]
        assert ttl == expected_ttl

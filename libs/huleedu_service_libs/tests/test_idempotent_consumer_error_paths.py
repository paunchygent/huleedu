from __future__ import annotations

import json

import pytest
from aiokafka import ConsumerRecord

from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from ._helpers_idempotency import create_mock_kafka_message


class TestIdempotentConsumerErrorHandling:
    """Tests error paths and fail-open behavior in idempotent_consumer."""

    @pytest.mark.asyncio
    async def test_idempotent_consumer_processing_failure_releases_lock(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """On handler exception, idempotency key is deleted to allow retry."""
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            raise Exception("Processing failed")

        with pytest.raises(Exception, match="Processing failed"):
            await handler(msg)

        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.delete_calls) == 1
        assert mock_redis_client.delete_calls[0].startswith("huleedu:idempotency:v2:test-service:")

    @pytest.mark.asyncio
    async def test_idempotent_consumer_redis_set_failure_fallback(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """If Redis SETNX fails, processing continues without idempotency protection."""
        mock_redis_client.should_fail_set = True
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            return f"processed_offset_{msg.offset}"

        result = await handler(msg)
        assert result == f"processed_offset_{msg.offset}"
        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.delete_calls) == 0

    @pytest.mark.asyncio
    async def test_idempotent_consumer_redis_delete_failure_logged_but_exception_propagates(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """If Redis DELETE fails during cleanup, original exception still propagates."""
        mock_redis_client.should_fail_delete = True
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            raise Exception("Processing failed")

        with pytest.raises(Exception, match="Processing failed"):
            await handler(msg)

        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.delete_calls) == 1

    @pytest.mark.asyncio
    async def test_idempotent_consumer_invalid_json_fails_open(
        self, mock_redis_client
    ) -> None:
        """Invalid JSON causes fail-open: handler executes with noop confirm."""
        # Create a ConsumerRecord with invalid JSON body
        bad_value = b"{not-json}"
        msg = ConsumerRecord(
            topic="test-topic",
            partition=0,
            offset=999,
            timestamp=0,
            timestamp_type=0,
            key=b"k",
            value=bad_value,
            headers=[],
            checksum=None,
            serialized_key_size=1,
            serialized_value_size=len(bad_value),
        )

        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            # confirm_idempotency is noop in fail-open; call is optional here
            return "processed_bad_json"

        result = await handler(msg)
        assert result == "processed_bad_json"
        # No Redis operations should occur on invalid JSON path
        assert len(mock_redis_client.set_calls) == 0
        assert len(mock_redis_client.delete_calls) == 0


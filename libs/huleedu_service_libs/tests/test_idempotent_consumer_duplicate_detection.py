from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import pytest
from aiokafka import ConsumerRecord

from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from ._helpers_idempotency import HandlerCallTracker, create_mock_kafka_message, tracked_handler


class TestIdempotentConsumerDuplicateDetection:
    """Tests for duplicate detection and deterministic keys in idempotent_consumer."""

    @pytest.mark.asyncio
    async def test_idempotent_consumer_first_time_processing_sets_processing_state(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """Processes first-time event, sets processing state key with TTL=300, and returns result."""
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)
        tracker = HandlerCallTracker()

        config = IdempotencyConfig(
            service_name="test-service", default_ttl=3600, enable_debug_logging=True
        )

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency, **kwargs) -> str:
            result = await tracked_handler(msg, tracker, "extra_arg", keyword_arg="test")
            await confirm_idempotency()
            return result

        result = await handler(msg, keyword_arg="test")

        assert result == f"tracked_result_{msg.offset}"
        assert len(mock_redis_client.set_calls) == 1
        assert mock_redis_client.set_calls[0][2] == 300  # processing TTL

        # Verify handler call arguments are preserved
        assert tracker.call_count == 1
        assert tracker.last_call_args[0] == msg
        assert tracker.last_call_args[1] == "extra_arg"
        assert tracker.last_call_kwargs == {"keyword_arg": "test"}

    @pytest.mark.asyncio
    async def test_idempotent_consumer_duplicate_event_skipped(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """Skips processing when Redis key exists with completed status."""
        msg: ConsumerRecord = create_mock_kafka_message(sample_event_data)

        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        # Pre-populate Redis to simulate completed event
        from huleedu_service_libs.event_utils import generate_deterministic_event_id

        deterministic_id = generate_deterministic_event_id(msg.value)
        redis_key = config.generate_redis_key(
            sample_event_data["event_type"], sample_event_data["event_id"], deterministic_id
        )
        mock_redis_client.keys[redis_key] = json.dumps(
            {"status": "completed", "processed_at": datetime.now(UTC).timestamp()}
        )

        tracker = HandlerCallTracker()

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        result = await handler(msg)
        assert result is None
        assert tracker.call_count == 0
        assert len(mock_redis_client.set_calls) == 0

    @pytest.mark.asyncio
    async def test_idempotent_consumer_deterministic_key_same_event_same_key(
        self, mock_redis_client
    ) -> None:
        """Identical event_id+data yields the same Redis key; second is skipped as duplicate."""
        fixed_event_id = str(uuid.uuid4())
        event_data = {
            "event_id": fixed_event_id,
            "event_type": "test.event.v1",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "test-service",
            "correlation_id": str(uuid.uuid4()),
            "data": {"test_field": "identical_value", "batch_id": "same-batch-123"},
        }

        msg1 = create_mock_kafka_message(event_data.copy(), offset=101)
        msg2 = create_mock_kafka_message(event_data.copy(), offset=102)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        res1 = await handler(msg1)
        assert res1 == f"tracked_result_{msg1.offset}"

        res2 = await handler(msg2)
        assert res2 is None
        assert len(mock_redis_client.set_calls) == 1  # Only first message attempts SETNX
        assert tracker.call_count == 1

    @pytest.mark.asyncio
    async def test_idempotent_consumer_different_data_different_keys(
        self, mock_redis_client
    ) -> None:
        """Different events produce different keys and both are processed."""
        event_data_1 = {
            "event_id": str(uuid.uuid4()),
            "data": {"batch_id": "batch-1", "value": "different"},
        }
        event_data_2 = {
            "event_id": str(uuid.uuid4()),
            "data": {"batch_id": "batch-2", "value": "content"},
        }

        msg1 = create_mock_kafka_message(event_data_1, offset=201)
        msg2 = create_mock_kafka_message(event_data_2, offset=202)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        res1 = await handler(msg1)
        res2 = await handler(msg2)

        assert res1 == f"tracked_result_{msg1.offset}"
        assert res2 == f"tracked_result_{msg2.offset}"
        assert len(mock_redis_client.set_calls) == 2
        key1 = mock_redis_client.set_calls[0][0]
        key2 = mock_redis_client.set_calls[1][0]
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_idempotent_consumer_locale_characters_do_not_affect_determinism(
        self, mock_redis_client, sample_event_data, swedish_source_service
    ) -> None:
        """Swedish characters in source_service should not affect duplicate detection keys."""
        # Two messages with identical event_id+data, differing only in source_service locale chars
        event_a = sample_event_data.copy()
        event_b = sample_event_data.copy()
        event_b["source_service"] = swedish_source_service

        msg1 = create_mock_kafka_message(event_a, offset=301)
        msg2 = create_mock_kafka_message(event_b, offset=302)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        res1 = await handler(msg1)
        res2 = await handler(msg2)

        assert res1 == f"tracked_result_{msg1.offset}"
        assert res2 is None  # Duplicate by event_id+data; locale chars should not matter

from __future__ import annotations

import uuid

import pytest
from aiokafka import ConsumerRecord
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer

from ._helpers_idempotency import HandlerCallTracker, create_mock_kafka_message, tracked_handler


class TestIdempotentConsumerHeaderOptimization:
    """Tests for header-based zero-parse optimization in idempotent_consumer."""

    @pytest.mark.asyncio
    async def test_idempotent_consumer_header_only_skips_json_parsing(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """When headers contain event_id + event_type, JSON parsing is skipped (headers_used=True)."""
        # Create message with complete headers
        headers = {
            "event_id": sample_event_data["event_id"],
            "event_type": sample_event_data["event_type"],
            "source_service": sample_event_data["source_service"],
        }
        msg = create_mock_kafka_message(sample_event_data, headers=headers)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        result = await handler(msg)
        assert result == f"tracked_result_{msg.offset}"
        assert tracker.call_count == 1

        # Verify Redis key was created (processing state)
        assert len(mock_redis_client.set_calls) == 1
        # Verify completion state was set
        assert len(mock_redis_client.setex_calls) == 1

    @pytest.mark.asyncio
    async def test_idempotent_consumer_incomplete_headers_falls_back_to_json(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """When headers missing event_id or event_type, falls back to JSON parsing."""
        # Headers with only event_id (missing event_type)
        headers = {
            "event_id": sample_event_data["event_id"],
            "source_service": sample_event_data["source_service"],
        }
        msg = create_mock_kafka_message(sample_event_data, headers=headers)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        result = await handler(msg)
        assert result == f"tracked_result_{msg.offset}"
        assert tracker.call_count == 1

    @pytest.mark.asyncio
    async def test_idempotent_consumer_header_and_json_paths_have_different_deterministic_keys(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """Header-based and JSON-based paths generate different deterministic keys (by design)."""
        event_id = str(uuid.uuid4())
        event_type = "test.deterministic.v1"

        # First message: JSON-only (no headers) - includes data in hash
        json_data = {
            "event_id": event_id,
            "event_type": event_type,
            "source_service": "test-service",
            "data": {"field": "value"},
        }
        msg1 = create_mock_kafka_message(json_data, headers=None, offset=401)

        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)
        tracker = HandlerCallTracker()

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        # Process first message (JSON path)
        res1 = await handler(msg1)
        assert res1 == f"tracked_result_{msg1.offset}"
        assert tracker.call_count == 1

        # Reset tracker and create second message with headers
        tracker.reset()
        headers = {
            "event_id": event_id,
            "event_type": event_type,
            "source_service": "test-service",
        }
        msg2 = create_mock_kafka_message(json_data, headers=headers, offset=402)

        # Process second message - should NOT be duplicate because header path uses different hash
        res2 = await handler(msg2)
        assert res2 == f"tracked_result_{msg2.offset}"  # Should process as different message
        assert tracker.call_count == 1  # Handler should be called

    @pytest.mark.asyncio
    async def test_idempotent_consumer_header_duplicate_detection_works(
        self, mock_redis_client, sample_event_data
    ) -> None:
        """Two messages with identical headers should be detected as duplicates."""
        headers = {
            "event_id": sample_event_data["event_id"],
            "event_type": sample_event_data["event_type"],
            "source_service": sample_event_data["source_service"],
        }

        msg1 = create_mock_kafka_message(sample_event_data, headers=headers, offset=501)
        msg2 = create_mock_kafka_message(sample_event_data, headers=headers, offset=502)

        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        # Process first message
        res1 = await handler(msg1)
        assert res1 == f"tracked_result_{msg1.offset}"

        # Process second message (should be duplicate)
        res2 = await handler(msg2)
        assert res2 is None
        assert tracker.call_count == 1  # Only first message processed

    @pytest.mark.asyncio
    async def test_idempotent_consumer_mixed_header_scenarios(self, mock_redis_client) -> None:
        """Test various header completeness scenarios."""
        base_data = {
            "event_id": str(uuid.uuid4()),
            "event_type": "test.mixed.v1",
            "source_service": "test-service",
            "data": {"test": "value"},
        }
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        test_cases = [
            # (description, headers, should_process)
            ("No headers", None, True),
            ("Empty headers", {}, True),
            ("Only event_id", {"event_id": base_data["event_id"]}, True),
            ("Only event_type", {"event_type": base_data["event_type"]}, True),
            (
                "Complete headers",
                {"event_id": base_data["event_id"], "event_type": base_data["event_type"]},
                True,
            ),
        ]

        for i, (desc, headers, should_process) in enumerate(test_cases):
            # Use unique event_id for each test case to avoid duplicates
            test_data = base_data.copy()
            test_data["event_id"] = str(uuid.uuid4())

            if headers and "event_id" in headers:
                headers["event_id"] = test_data["event_id"]

            msg = create_mock_kafka_message(test_data, headers=headers, offset=600 + i)
            tracker = HandlerCallTracker()

            @idempotent_consumer(redis_client=mock_redis_client, config=config)
            async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
                result = await tracked_handler(msg, tracker)
                await confirm_idempotency()
                return result

            result = await handler(msg)

            if should_process:
                assert result == f"tracked_result_{msg.offset}", f"Failed for: {desc}"
                assert tracker.call_count == 1, f"Handler not called for: {desc}"
            else:
                assert result is None, f"Should have been skipped for: {desc}"

    @pytest.mark.asyncio
    async def test_idempotent_consumer_swedish_characters_in_headers(
        self, mock_redis_client, sample_event_data, swedish_source_service
    ) -> None:
        """Swedish characters in headers should be handled correctly."""
        headers = {
            "event_id": sample_event_data["event_id"],
            "event_type": sample_event_data["event_type"],
            "source_service": swedish_source_service,  # Contains åäöÅÄÖ
        }

        msg = create_mock_kafka_message(sample_event_data, headers=headers)
        tracker = HandlerCallTracker()
        config = IdempotencyConfig(service_name="test-service", default_ttl=3600)

        @idempotent_consumer(redis_client=mock_redis_client, config=config)
        async def handler(msg: ConsumerRecord, *, confirm_idempotency) -> str:
            result = await tracked_handler(msg, tracker)
            await confirm_idempotency()
            return result

        result = await handler(msg)
        assert result == f"tracked_result_{msg.offset}"
        assert tracker.call_count == 1

        # Should process successfully despite Swedish characters
        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.setex_calls) == 1

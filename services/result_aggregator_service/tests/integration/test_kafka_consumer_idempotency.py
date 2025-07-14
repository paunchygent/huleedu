"""Integration tests for Kafka consumer idempotency handling."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from huleedu_service_libs.protocols import RedisClientProtocol

from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import BatchEssaysRegistered, EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer

from .conftest import MockRedisClient, create_kafka_record


class TestKafkaConsumerIdempotency:
    """Test cases for Kafka consumer idempotency handling."""

    async def test_idempotency_first_message_processed(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that first occurrence of a message is processed."""
        # Arrange
        batch_id: str = str(uuid4())
        data = self._create_batch_registered_data(batch_id)
        envelope = self._create_envelope(data)
        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_idempotently(record)

        # Assert
        assert result is True  # First time processing
        assert len(mock_redis_client.set_calls) == 1
        # V2 uses event-specific TTLs: batch registration events use 43200 seconds (12 hours)
        assert mock_redis_client.set_calls[0][2] == 43200  # TTL check for batch events
        mock_event_processor.process_batch_registered.assert_called_once()

    async def test_idempotency_duplicate_message_skipped(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that duplicate messages are skipped."""
        # Arrange
        batch_id: str = str(uuid4())
        data = self._create_batch_registered_data(batch_id)
        envelope = self._create_envelope(data)
        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Process first time
        result1 = await kafka_consumer._process_message_idempotently(record)
        assert result1 is True

        # Act - Process same message again
        result2 = await kafka_consumer._process_message_idempotently(record)

        # Assert
        assert result2 is None  # Duplicate detected
        assert len(mock_redis_client.set_calls) == 2
        assert mock_event_processor.process_batch_registered.call_count == 1  # Only called once

    async def test_idempotency_key_deleted_on_processing_error(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that idempotency key is deleted when processing fails."""
        # Arrange
        batch_id: str = str(uuid4())
        data = self._create_batch_registered_data(batch_id)
        envelope = self._create_envelope(data)
        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Make processor raise an error
        mock_event_processor.process_batch_registered.side_effect = Exception("Processing failed")

        # Act & Assert
        with pytest.raises(Exception, match="Processing failed"):
            await kafka_consumer._process_message_idempotently(record)

        # Assert key was set then deleted
        assert len(mock_redis_client.set_calls) == 1
        assert len(mock_redis_client.delete_calls) == 1
        # V2 uses namespaced keys: huleedu:idempotency:v2:result-aggregator-service:event_type:hash
        assert mock_redis_client.delete_calls[0].startswith(
            "huleedu:idempotency:v2:result-aggregator-service:"
        )

    async def test_idempotency_redis_failure_processes_message(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that messages are processed even if Redis fails (fail-open)."""
        # Arrange
        batch_id: str = str(uuid4())
        data = self._create_batch_registered_data(batch_id)
        envelope = self._create_envelope(data)
        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Create a failing Redis client
        failing_redis = AsyncMock(spec=RedisClientProtocol)
        failing_redis.set_if_not_exists.side_effect = Exception("Redis connection failed")

        # Create consumer with failing Redis
        consumer = ResultAggregatorKafkaConsumer(
            settings=Settings(),
            event_processor=mock_event_processor,
            metrics=kafka_consumer.metrics,  # Reuse the existing metrics instance
            redis_client=failing_redis,
        )

        # Act
        result = await consumer._process_message_idempotently(record)

        # Assert
        assert result is True  # Message still processed
        mock_event_processor.process_batch_registered.assert_called_once()

    async def test_idempotency_different_data_processed(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
        mock_redis_client: MockRedisClient,
    ) -> None:
        """Test that messages with different data are processed separately."""
        # Arrange
        batch_id1: str = str(uuid4())
        batch_id2: str = str(uuid4())

        data1 = self._create_batch_registered_data(batch_id1)
        envelope1 = self._create_envelope(data1)
        record1 = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope1,
        )

        data2 = self._create_batch_registered_data(batch_id2)
        envelope2 = self._create_envelope(data2)
        record2 = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope2,
        )

        # Act
        result1 = await kafka_consumer._process_message_idempotently(record1)
        result2 = await kafka_consumer._process_message_idempotently(record2)

        # Assert
        assert result1 is True
        assert result2 is True
        assert mock_event_processor.process_batch_registered.call_count == 2
        assert len(mock_redis_client.keys) == 2  # Two different keys

    def _create_batch_registered_data(self, batch_id: str) -> BatchEssaysRegistered:
        """Helper to create BatchEssaysRegistered data."""
        entity_ref = EntityReference(
            entity_id=batch_id,
            entity_type="batch",
        )

        return BatchEssaysRegistered(
            batch_id=batch_id,
            user_id=str(uuid4()),
            essay_ids=["essay-1", "essay-2"],
            expected_essay_count=2,
            metadata=SystemProcessingMetadata(entity=entity_ref),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

    def _create_envelope(self, data: Any) -> EventEnvelope[Any]:
        """Helper to create EventEnvelope."""
        return EventEnvelope(
            event_id=uuid4(),
            event_type=type(data).__name__,
            event_timestamp=datetime.now(UTC),
            source_service="test",
            correlation_id=uuid4(),
            data=data,
        )

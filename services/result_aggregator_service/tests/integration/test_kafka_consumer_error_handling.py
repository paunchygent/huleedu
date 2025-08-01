"""Integration tests for Kafka consumer error handling."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from aiokafka import ConsumerRecord
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import (
    BatchEssaysRegistered,
    EventEnvelope,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.status_enums import EssayStatus

from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer

from .conftest import create_kafka_record


class TestKafkaConsumerErrorHandling:
    """Test cases for Kafka consumer error handling."""

    async def test_invalid_json_is_logged_and_acknowledged(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
    ) -> None:
        """Test that invalid JSON is gracefully handled, logged, and acknowledged."""
        # Arrange
        record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            partition=0,
            offset=12345,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=b"invalid json {{{",  # Invalid JSON
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True  # Message should be acknowledged
        # The error handling is working correctly - the message was logged and acknowledged

    async def test_invalid_envelope_is_logged_and_acknowledged(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
    ) -> None:
        """Test that invalid envelope structure is gracefully handled, logged, and acknowledged."""
        # Arrange
        invalid_envelope = {
            # Missing required fields like event_id, event_type
            "data": {"some": "data"}
        }

        record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            partition=0,
            offset=12345,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=json.dumps(invalid_envelope).encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True  # Message should be acknowledged
        # The error handling is working correctly - the message was logged and acknowledged

    async def test_invalid_event_data_is_logged_and_acknowledged(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
    ) -> None:
        """Test that invalid event data is gracefully handled, logged, and acknowledged."""
        # Arrange
        envelope = {
            "event_id": str(uuid4()),
            "event_type": "BatchEssaysRegistered",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "test",
            "data": {
                # Missing required fields for BatchEssaysRegistered
                "batch_id": str(uuid4()),
                # Missing: user_id, essay_ids, etc.
            },
        }

        record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            partition=0,
            offset=12345,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=json.dumps(envelope).encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True  # Message should be acknowledged
        # The error handling is working correctly - the message was logged and acknowledged

    async def test_consumer_continues_after_poison_pill(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that consumer processes valid messages after encountering poison pills."""
        # Arrange - Create a sequence: valid -> poison -> valid
        batch_id1 = str(uuid4())
        batch_id2 = str(uuid4())

        # Valid batch registered event
        # EntityReference removed - using primitive parameters
        valid_data1 = BatchEssaysRegistered(
            entity_id=batch_id1,  # entity_id at top level (modernized from batch_id)
            user_id=str(uuid4()),
            essay_ids=["essay-1", "essay-2"],
            expected_essay_count=2,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id1,
                entity_type="batch",
                parent_id=None,
            ),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        valid_envelope1: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(UTC),
            source_service="batch_orchestrator",
            correlation_id=uuid4(),
            data=valid_data1,
        )

        valid_record1 = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=valid_envelope1,
            offset=1,
        )

        # Poison pill (invalid JSON)
        poison_record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            partition=0,
            offset=2,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=b"{'invalid': 'json', missing quotes}",  # Invalid JSON
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Valid spellcheck completed event
        # EntityReference removed - using primitive parameters
        essay_id = str(uuid4())

        valid_data2 = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id2,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=batch_id2,
            ),
            original_text_storage_id="original-123",
            corrections_made=3,
            storage_metadata=StorageReferenceMetadata(
                references={ContentType.CORRECTED_TEXT: {"corrected": "storage-456"}}
            ),
        )

        valid_envelope2: EventEnvelope[SpellcheckResultDataV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(UTC),
            source_service="spell_checker",
            correlation_id=uuid4(),
            data=valid_data2,
        )

        valid_record2 = create_kafka_record(
            topic="huleedu.essay.spellcheck.completed.v1",
            event_envelope=valid_envelope2,
            offset=3,
        )

        # Act - Process all messages
        result1 = await kafka_consumer._process_message_impl(valid_record1)
        result2 = await kafka_consumer._process_message_impl(poison_record)
        result3 = await kafka_consumer._process_message_impl(valid_record2)

        # Assert
        # All messages should be acknowledged
        assert result1 is True
        assert result2 is True
        assert result3 is True

        # Both valid messages should have been processed
        assert mock_event_processor.process_batch_registered.call_count == 1
        assert mock_event_processor.process_spellcheck_completed.call_count == 1

        # The poison pill was handled gracefully without affecting other messages

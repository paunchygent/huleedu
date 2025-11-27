"""Integration tests for Kafka consumer resilience with nullable batch_id scenarios."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import (
    BatchEssaysRegistered,
    EventEnvelope,
)
from common_core.events.cj_assessment_events import AssessmentResultV1
from common_core.events.essay_lifecycle_events import EssaySlotAssignedV1
from common_core.events.spellcheck_models import (
    SpellcheckMetricsV1,
    SpellcheckResultV1,
)
from common_core.metadata_models import StorageReferenceMetadata, SystemProcessingMetadata
from common_core.status_enums import EssayStatus
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer

from .conftest import create_kafka_record


def make_prompt_ref(label: str) -> StorageReferenceMetadata:
    prompt_ref = StorageReferenceMetadata()
    prompt_ref.add_reference(ContentType.STUDENT_PROMPT_TEXT, label)
    return prompt_ref


class TestKafkaConsumerResilience:
    """Test cases for consumer recovery from database errors and nullable batch_id scenarios."""

    async def test_consumer_recovers_from_fk_violation(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that consumer recovers from foreign key violations caused by old
        batch_id='pending' logic."""
        # Arrange - Mock consumer for commit verification and event processor to simulate
        # FK violation
        mock_kafka_consumer = AsyncMock()
        kafka_consumer.consumer = mock_kafka_consumer

        # Create a side effect function that throws IntegrityError for the idempotency wrapper
        async def throw_integrity_error(*args: object, **kwargs: object) -> None:
            raise IntegrityError(
                "INSERT statement", {"batch_id": "pending"}, Exception("ForeignKeyViolationError")
            )

        # Mock the idempotent wrapper to bypass idempotency and test error handling
        mock_idempotent_processor = AsyncMock(side_effect=throw_integrity_error)
        kafka_consumer._process_message_idempotently = mock_idempotent_processor

        essay_id = str(uuid4())

        metrics = SpellcheckMetricsV1(
            total_corrections=3,
            l2_dictionary_corrections=2,
            spellchecker_corrections=1,
            word_count=100,
            correction_density=3.0,
        )

        spellcheck_data = SpellcheckResultV1(
            event_name=ProcessingEvent.SPELLCHECK_RESULTS,
            entity_id=essay_id,
            entity_type="essay",
            parent_id="pending",  # Old behavior that causes FK violation
            batch_id="pending",
            correlation_id=str(uuid4()),
            user_id=None,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            corrections_made=3,
            correction_metrics=metrics,
            original_text_storage_id="original-123",
            corrected_text_storage_id="storage-456",
            processing_duration_ms=1500,
            processor_version="pyspellchecker_1.0_L2_swedish",
            system_metadata=SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
            ),
        )

        envelope: EventEnvelope[SpellcheckResultV1] = EventEnvelope(
            event_id=uuid4(),
            event_type=topic_name(ProcessingEvent.SPELLCHECK_RESULTS),
            event_timestamp=datetime.now(UTC),
            source_service="spell_checker",
            correlation_id=uuid4(),
            data=spellcheck_data,
        )

        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.SPELLCHECK_RESULTS),
            event_envelope=envelope,
        )

        # Mock the _process_batch method to test the error handling flow
        messages = {record.topic: [record]}

        # Act
        await kafka_consumer._process_batch(messages)

        # Assert - Consumer should commit offset even after FK violation
        mock_kafka_consumer.commit.assert_called()
        # The error should have been caught and classified
        mock_idempotent_processor.assert_called_once()

    async def test_consumer_classifies_errors_correctly(
        self, kafka_consumer: ResultAggregatorKafkaConsumer
    ) -> None:
        """Test that error classification logic works correctly for different error types."""
        # Test database integrity errors (permanent)
        integrity_error = IntegrityError("statement", {}, Exception("original"))
        is_retryable, error_type = kafka_consumer._classify_error(integrity_error)
        assert not is_retryable
        assert error_type == "database_integrity_error"

        # Test validation errors (permanent)
        validation_error = ValidationError.from_exception_data("title", [])
        is_retryable, error_type = kafka_consumer._classify_error(validation_error)
        assert not is_retryable
        assert error_type == "validation_error"

        # Test connection errors (retryable)
        connection_error = ConnectionError("Connection failed")
        is_retryable, error_type = kafka_consumer._classify_error(connection_error)
        assert is_retryable
        assert error_type == "connection_error"

        # Test timeout errors (retryable)
        timeout_error = TimeoutError("Request timed out")
        is_retryable, error_type = kafka_consumer._classify_error(timeout_error)
        assert is_retryable
        assert error_type == "connection_error"

        # Test value errors (permanent)
        value_error = ValueError("Invalid value")
        is_retryable, error_type = kafka_consumer._classify_error(value_error)
        assert not is_retryable
        assert error_type == "value_error"

        # Test unknown errors (permanent by default)
        unknown_error = RuntimeError("Unknown error")
        is_retryable, error_type = kafka_consumer._classify_error(unknown_error)
        assert not is_retryable
        assert error_type == "unknown_error"

    async def test_consumer_commits_offset_after_permanent_error(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that consumer commits offset after permanent errors to avoid infinite retry."""
        # Arrange - Mock consumer for commit verification
        mock_kafka_consumer = AsyncMock()
        kafka_consumer.consumer = mock_kafka_consumer

        # Mock event processor to throw permanent error
        mock_event_processor.process_batch_registered.side_effect = (
            ValidationError.from_exception_data("title", [])
        )

        batch_id = str(uuid4())
        batch_data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=str(uuid4()),
            essay_ids=["essay-1", "essay-2"],
            expected_essay_count=2,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
            ),
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-resilience-error"),
        )

        envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(UTC),
            source_service="batch_orchestrator",
            correlation_id=uuid4(),
            data=batch_data,
        )

        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Mock the _process_batch method to simulate batch processing with error
        messages = {record.topic: [record]}

        # Act
        await kafka_consumer._process_batch(messages)

        # Assert - Consumer should commit offset even after error
        mock_kafka_consumer.commit.assert_called()


class TestEventOrderingIndependence:
    """Test cases for event ordering independence with nullable batch_id."""

    async def test_slot_assignment_before_batch_registration(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test GUEST flow where slot assignment arrives before batch registration."""
        # Arrange - Essay slot assignment arrives first (batch_id will be None)
        essay_id = str(uuid4())
        file_upload_id = str(uuid4())

        # Slot assignment event (arrives first in GUEST flow)
        # Note: In GUEST flow, batch_id might be a temporary value that gets updated later
        slot_data = EssaySlotAssignedV1(
            event="essay.slot.assigned",
            batch_id="guest-pending",  # Temporary batch_id for GUEST flow
            essay_id=essay_id,
            file_upload_id=file_upload_id,
            text_storage_id="storage-123",
            original_file_name="guest_essay.docx",
            correlation_id=uuid4(),
        )

        slot_envelope: EventEnvelope[EssaySlotAssignedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="EssaySlotAssignedV1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle",
            correlation_id=uuid4(),
            data=slot_data,
        )

        slot_record = create_kafka_record(
            topic=topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
            event_envelope=slot_envelope,
        )

        # Act - Process slot assignment first
        result = await kafka_consumer._process_message_impl(slot_record)

        # Assert - Should process successfully with batch_id=None
        assert result is True
        mock_event_processor.process_essay_slot_assigned.assert_called_once()

    async def test_batch_registration_then_slot_assignment(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test REGULAR flow where batch registration arrives before slot assignment."""
        # Arrange - Batch registration arrives first
        batch_id = str(uuid4())
        essay_id = str(uuid4())

        # Batch registration event (arrives first in REGULAR flow)
        batch_data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=str(uuid4()),
            essay_ids=[essay_id],
            expected_essay_count=1,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
            ),
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-resilience-regular"),
        )

        batch_envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(UTC),
            source_service="batch_orchestrator",
            correlation_id=uuid4(),
            data=batch_data,
        )

        batch_record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=batch_envelope,
        )

        # Slot assignment event (arrives after batch registration)
        slot_data = EssaySlotAssignedV1(
            event="essay.slot.assigned",
            batch_id=batch_id,  # batch_id is available in REGULAR flow
            essay_id=essay_id,
            file_upload_id=str(uuid4()),
            text_storage_id="storage-123",
            original_file_name="regular_essay.docx",
            correlation_id=uuid4(),
        )

        slot_envelope: EventEnvelope[EssaySlotAssignedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="EssaySlotAssignedV1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle",
            correlation_id=uuid4(),
            data=slot_data,
        )

        slot_record = create_kafka_record(
            topic=topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
            event_envelope=slot_envelope,
        )

        # Act - Process both events in order
        batch_result = await kafka_consumer._process_message_impl(batch_record)
        slot_result = await kafka_consumer._process_message_impl(slot_record)

        # Assert - Both should process successfully
        assert batch_result is True
        assert slot_result is True
        mock_event_processor.process_batch_registered.assert_called_once()
        mock_event_processor.process_essay_slot_assigned.assert_called_once()

    async def test_multiple_essays_associated_correctly(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that multiple essays from different flows are associated correctly."""
        # Arrange - Mixed scenario with multiple essays
        batch_id = str(uuid4())
        user_id = str(uuid4())

        # Essay 1: GUEST flow (slot assignment first, no batch_id)
        essay_id_1 = str(uuid4())
        slot_data_1 = EssaySlotAssignedV1(
            event="essay.slot.assigned",
            batch_id="guest-pending",  # GUEST flow - temporary batch_id
            essay_id=essay_id_1,
            file_upload_id=str(uuid4()),
            text_storage_id="storage-1",
            original_file_name="guest_essay_1.docx",
            correlation_id=uuid4(),
        )

        # Essay 2: REGULAR flow (batch registration first)
        essay_id_2 = str(uuid4())
        batch_data = BatchEssaysRegistered(
            entity_id=batch_id,
            user_id=user_id,
            essay_ids=[essay_id_2],  # Only essay_2 is pre-registered
            expected_essay_count=1,
            metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
            ),
            course_code=CourseCode.ENG5,
            student_prompt_ref=make_prompt_ref("prompt-resilience-mixed"),
        )

        # Create event envelopes
        slot_envelope_1: EventEnvelope[EssaySlotAssignedV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="EssaySlotAssignedV1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle",
            correlation_id=uuid4(),
            data=slot_data_1,
        )

        batch_envelope: EventEnvelope[BatchEssaysRegistered] = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(UTC),
            source_service="batch_orchestrator",
            correlation_id=uuid4(),
            data=batch_data,
        )

        # Create records
        slot_record_1 = create_kafka_record(
            topic=topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
            event_envelope=slot_envelope_1,
        )

        batch_record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=batch_envelope,
        )

        # Act - Process events in mixed order
        slot_result_1 = await kafka_consumer._process_message_impl(slot_record_1)
        batch_result = await kafka_consumer._process_message_impl(batch_record)

        # Assert - All events should process successfully
        assert slot_result_1 is True
        assert batch_result is True

        # Verify correct method calls
        mock_event_processor.process_essay_slot_assigned.assert_called_once()
        mock_event_processor.process_batch_registered.assert_called_once()


class TestErrorClassification:
    """Test cases for comprehensive error classification scenarios."""

    @pytest.mark.parametrize(
        "error,expected_retryable,expected_type",
        [
            (IntegrityError("statement", {}, Exception("orig")), False, "database_integrity_error"),
            (ValidationError.from_exception_data("title", []), False, "validation_error"),
            (ConnectionError("Connection failed"), True, "connection_error"),
            (TimeoutError("Timeout"), True, "connection_error"),
            (ValueError("Invalid value"), False, "value_error"),
            (RuntimeError("Runtime error"), False, "unknown_error"),
            (json.JSONDecodeError("msg", "doc", 0), False, "validation_error"),
        ],
    )
    async def test_error_classification(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        error: Exception,
        expected_retryable: bool,
        expected_type: str,
    ) -> None:
        """Test error classification for various exception types."""
        # Act
        is_retryable, error_type = kafka_consumer._classify_error(error)

        # Assert
        assert is_retryable == expected_retryable
        assert error_type == expected_type

    async def test_consumer_handles_assessment_result_with_nullable_batch(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that assessment results can be processed even when essay has no
        batch association."""
        # Arrange - Assessment result for essay not yet associated with batch
        essay_id = str(uuid4())
        batch_id = str(uuid4())
        assessment_data = AssessmentResultV1(
            event_name=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED,
            entity_id=batch_id,
            entity_type="batch",
            parent_id=None,
            batch_id=batch_id,
            cj_assessment_job_id=str(uuid4()),
            assessment_method="cj_assessment",
            model_used="claude-3-opus",
            model_provider="anthropic",
            essay_results=[
                {
                    "essay_id": essay_id,
                    "normalized_score": 0.85,
                    "letter_grade": "B+",
                    "confidence_score": 0.9,
                    "confidence_label": "HIGH",
                    "bt_score": 1.2,
                    "rank": 1,
                    "is_anchor": False,
                }
            ],
            assessment_metadata={
                "judges": ["judge1", "judge2"],
                "session_id": str(uuid4()),
            },
            system_metadata=SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
            ),
        )

        envelope: EventEnvelope[AssessmentResultV1] = EventEnvelope(
            event_id=uuid4(),
            event_type="AssessmentResultV1",
            event_timestamp=datetime.now(UTC),
            source_service="cj_assessment",
            correlation_id=uuid4(),
            data=assessment_data,
        )

        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED),
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert - Should process successfully even without batch association
        assert result is True
        mock_event_processor.process_assessment_result.assert_called_once()

    async def test_consumer_resilience_with_corrupted_metadata(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
    ) -> None:
        """Test consumer resilience when event metadata is corrupted but JSON is valid."""
        # Arrange - Valid JSON but corrupted event structure
        corrupted_envelope = {
            "event_id": "not-a-uuid",  # Invalid UUID
            "event_type": "BatchEssaysRegistered",
            "event_timestamp": "invalid-timestamp",  # Invalid timestamp
            "source_service": "",  # Empty source service
            "data": {
                "entity_id": str(uuid4()),
                "user_id": str(uuid4()),
                "essay_ids": [],  # Empty essay list
                "expected_essay_count": -1,  # Invalid count
            },
        }

        record = ConsumerRecord(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            partition=0,
            offset=12345,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=json.dumps(corrupted_envelope).encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert - Should handle gracefully and acknowledge
        assert result is True  # Consumer acknowledges corrupted message

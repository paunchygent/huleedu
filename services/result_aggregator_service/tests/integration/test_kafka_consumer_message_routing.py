"""Integration tests for Kafka consumer message routing."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from aiokafka import ConsumerRecord

from common_core.domain_enums import ContentType, CourseCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events import (
    BatchEssaysRegistered,
    CJAssessmentCompletedV1,
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, EssayStatus
from services.result_aggregator_service.kafka_consumer import ResultAggregatorKafkaConsumer

from .conftest import create_kafka_record


class TestKafkaConsumerRouting:
    """Test cases for Kafka consumer message routing."""

    async def test_route_batch_registered_event(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test routing of BatchEssaysRegistered event."""
        # Arrange
        batch_id: str = str(uuid4())
        user_id: str = str(uuid4())

        entity_ref = EntityReference(
            entity_id=batch_id,
            entity_type="batch",
        )

        data = BatchEssaysRegistered(
            batch_id=batch_id,
            user_id=user_id,
            essay_ids=["essay-1", "essay-2", "essay-3"],
            expected_essay_count=3,
            metadata=SystemProcessingMetadata(entity=entity_ref),
            course_code=CourseCode.ENG5,
            essay_instructions="Write an essay",
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="BatchEssaysRegistered",
            event_timestamp=datetime.now(UTC),
            source_service="batch_orchestrator",
            correlation_id=uuid4(),
            data=data,
        )

        record = create_kafka_record(
            topic=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True
        mock_event_processor.process_batch_registered.assert_called_once()
        call_args = mock_event_processor.process_batch_registered.call_args
        assert call_args[0][0].event_id == envelope.event_id
        assert call_args[0][1].batch_id == batch_id

    async def test_route_spellcheck_completed_event(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test routing of SpellcheckResultDataV1 event."""
        # Arrange
        essay_id: str = str(uuid4())
        batch_id: str = str(uuid4())

        entity_ref = EntityReference(
            entity_id=essay_id,
            entity_type="essay",
            parent_id=batch_id,
        )

        data = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_ref=entity_ref,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=SystemProcessingMetadata(entity=entity_ref),
            original_text_storage_id="original-123",
            corrections_made=5,
            storage_metadata=StorageReferenceMetadata(
                references={ContentType.CORRECTED_TEXT: {"corrected": "storage-456"}}
            ),
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="SpellcheckResultDataV1",
            event_timestamp=datetime.now(UTC),
            source_service="spell_checker",
            correlation_id=uuid4(),
            data=data,
        )

        record = create_kafka_record(
            topic="huleedu.essay.spellcheck.completed.v1",
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True
        mock_event_processor.process_spellcheck_completed.assert_called_once()
        call_args = mock_event_processor.process_spellcheck_completed.call_args
        assert call_args[0][1].entity_ref.entity_id == essay_id

    async def test_route_cj_assessment_completed_event(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test routing of CJAssessmentCompletedV1 event."""
        # Arrange
        batch_id: str = str(uuid4())

        entity_ref = EntityReference(
            entity_id=batch_id,
            entity_type="batch",
        )

        rankings = [
            {"els_essay_id": "essay-1", "rank": 1, "score": 0.95},
            {"els_essay_id": "essay-2", "rank": 2, "score": 0.85},
        ]

        data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_ref=entity_ref,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(entity=entity_ref),
            cj_assessment_job_id="job-123",
            rankings=rankings,
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="CJAssessmentCompletedV1",
            event_timestamp=datetime.now(UTC),
            source_service="cj_assessment",
            correlation_id=uuid4(),
            data=data,
        )

        record = create_kafka_record(
            topic="huleedu.cj_assessment.completed.v1",
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True
        mock_event_processor.process_cj_assessment_completed.assert_called_once()
        call_args = mock_event_processor.process_cj_assessment_completed.call_args
        assert call_args[0][1].rankings == rankings

    async def test_route_batch_phase_outcome_event(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test routing of ELSBatchPhaseOutcomeV1 event."""
        # Arrange
        batch_id: str = str(uuid4())

        data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
                EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-2"),
            ],
            failed_essay_ids=[],
            correlation_id=uuid4(),
        )

        envelope = EventEnvelope(
            event_id=uuid4(),
            event_type="ELSBatchPhaseOutcomeV1",
            event_timestamp=datetime.now(UTC),
            source_service="essay_lifecycle",
            correlation_id=uuid4(),
            data=data,
        )

        record = create_kafka_record(
            topic="huleedu.els.batch_phase.outcome.v1",
            event_envelope=envelope,
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True
        mock_event_processor.process_batch_phase_outcome.assert_called_once()
        call_args = mock_event_processor.process_batch_phase_outcome.call_args
        assert call_args[0][1].batch_id == batch_id

    async def test_unhandled_topic_warning(
        self,
        kafka_consumer: ResultAggregatorKafkaConsumer,
        mock_event_processor: AsyncMock,
    ) -> None:
        """Test that unhandled topics generate a warning."""
        # Arrange
        # Create a simple envelope with dictionary data
        envelope_dict = {
            "event_id": str(uuid4()),
            "event_type": "UnknownEvent",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "unknown",
            "data": {"some": "data"},
        }

        record = ConsumerRecord(
            topic="huleedu.unknown.topic.v1",
            partition=0,
            offset=12345,
            timestamp=None,
            timestamp_type=None,
            key=None,
            value=json.dumps(envelope_dict).encode("utf-8"),
            checksum=None,
            serialized_key_size=None,
            serialized_value_size=None,
            headers=[],
        )

        # Act
        result = await kafka_consumer._process_message_impl(record)

        # Assert
        assert result is True
        # No processor method should be called
        mock_event_processor.process_batch_registered.assert_not_called()
        mock_event_processor.process_spellcheck_completed.assert_not_called()
        mock_event_processor.process_cj_assessment_completed.assert_not_called()
        mock_event_processor.process_batch_phase_outcome.assert_not_called()

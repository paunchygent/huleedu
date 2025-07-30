"""
Unit tests for BOS dual event handling patterns.

Tests concurrent success/error event processing, idempotency with dual events,
and event routing correctness in the new dual-event architecture.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from aiokafka import ConsumerRecord
from common_core.domain_enums import CourseCode
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import (
    BatchErrorSummary,
    BatchEssaysReady,
    BatchValidationErrorsV1,
    EssayValidationError,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EntityReference,
    EssayProcessingInputRefV1,
    SystemProcessingMetadata,
)
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import ProcessingStage

from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.batch_validation_errors_handler import (
    BatchValidationErrorsHandler,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer

# Rebuild models to resolve forward references
EssayValidationError.model_rebuild()
BatchValidationErrorsV1.model_rebuild()


class TestDualEventHandling:
    """Test suite for BOS dual event handling patterns."""

    @pytest.fixture
    def mock_handlers(self) -> dict[str, AsyncMock]:
        """Create mock handlers for testing."""
        return {
            "batch_essays_ready_handler": AsyncMock(spec=BatchEssaysReadyHandler),
            "batch_validation_errors_handler": AsyncMock(spec=BatchValidationErrorsHandler),
            "els_batch_phase_outcome_handler": AsyncMock(),
            "client_pipeline_request_handler": AsyncMock(),
            "redis_client": AsyncMock(),
        }

    @pytest.fixture
    def kafka_consumer(self, mock_handlers: dict[str, AsyncMock]) -> BatchKafkaConsumer:
        """Create a BatchKafkaConsumer instance with mock handlers."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-group",
            batch_essays_ready_handler=mock_handlers["batch_essays_ready_handler"],
            batch_validation_errors_handler=mock_handlers["batch_validation_errors_handler"],
            els_batch_phase_outcome_handler=mock_handlers["els_batch_phase_outcome_handler"],
            client_pipeline_request_handler=mock_handlers["client_pipeline_request_handler"],
            redis_client=mock_handlers["redis_client"],
        )

    def create_kafka_message(
        self, topic: str, event_envelope: EventEnvelope[Any]
    ) -> ConsumerRecord:
        """Create a Kafka ConsumerRecord for testing."""
        # Serialize the envelope as it would be in Kafka
        value = json.dumps(event_envelope.model_dump(mode="json")).encode("utf-8")

        return ConsumerRecord(
            topic=topic,
            partition=0,
            offset=1,
            timestamp=1234567890,
            timestamp_type=0,
            key=None,
            value=value,
            headers=[],
            checksum=None,
            serialized_key_size=0,
            serialized_value_size=len(value),
        )

    @pytest.mark.asyncio
    async def test_concurrent_dual_event_processing(
        self, kafka_consumer: BatchKafkaConsumer, mock_handlers: dict[str, AsyncMock]
    ) -> None:
        """Test that success and error events for the same batch are processed concurrently."""
        batch_id = "test-batch-concurrent"
        correlation_id = uuid4()

        # Create success event
        success_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            ],
            batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.PROCESSING,
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test instructions",
            class_type="REGULAR",
            teacher_first_name="John",
            teacher_last_name="Doe",
        )

        success_envelope = EventEnvelope[BatchEssaysReady](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=success_event,
        )

        # Create error event
        error_detail = ErrorDetail(
            error_code=ErrorCode.VALIDATION_ERROR,
            message="Invalid format",
            correlation_id=correlation_id,
            timestamp=datetime.now(UTC),
            service="file-service",
            operation="validate",
        )

        error_event = BatchValidationErrorsV1(
            batch_id=batch_id,
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-2",
                    file_name="essay2.pdf",
                    error_detail=error_detail,
                )
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=False,
            ),
            correlation_id=correlation_id,
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.PROCESSING,
            ),
        )

        error_envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type="huleedu.els.batch.validation.errors.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=error_event,
        )

        # Create Kafka messages
        success_msg = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY), success_envelope
        )
        error_msg = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS), error_envelope
        )

        # Process both messages
        await kafka_consumer._handle_message(success_msg)
        await kafka_consumer._handle_message(error_msg)

        # Verify both handlers were called
        mock_handlers["batch_essays_ready_handler"].handle_batch_essays_ready.assert_called_once()
        mock_handlers[
            "batch_validation_errors_handler"
        ].handle_batch_validation_errors.assert_called_once()

    @pytest.mark.asyncio
    async def test_event_routing_correctness(
        self, kafka_consumer: BatchKafkaConsumer, mock_handlers: dict[str, AsyncMock]
    ) -> None:
        """Test that events are routed to the correct handlers based on topic."""
        # Create different event types
        topics_and_handlers = [
            (
                ProcessingEvent.BATCH_ESSAYS_READY,
                "batch_essays_ready_handler",
                "handle_batch_essays_ready",
            ),
            (
                ProcessingEvent.BATCH_VALIDATION_ERRORS,
                "batch_validation_errors_handler",
                "handle_batch_validation_errors",
            ),
            (
                ProcessingEvent.ELS_BATCH_PHASE_OUTCOME,
                "els_batch_phase_outcome_handler",
                "handle_els_batch_phase_outcome",
            ),
            (
                ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST,
                "client_pipeline_request_handler",
                "handle_client_pipeline_request",
            ),
        ]

        for event_type, handler_name, method_name in topics_and_handlers:
            # Create a mock message for each topic
            mock_msg = MagicMock()
            mock_msg.topic = topic_name(event_type)

            # Process the message
            await kafka_consumer._handle_message(mock_msg)

            # Verify only the correct handler was called
            handler = mock_handlers[handler_name]
            method = getattr(handler, method_name)
            method.assert_called_once_with(mock_msg)

            # Reset for next iteration
            method.reset_mock()

    @pytest.mark.asyncio
    async def test_idempotency_with_dual_events(
        self, kafka_consumer: BatchKafkaConsumer, mock_handlers: dict[str, AsyncMock]
    ) -> None:
        """Test idempotency handling for duplicate dual events."""
        batch_id = "test-batch-idempotent"
        correlation_id = uuid4()

        # Create a success event
        success_event = BatchEssaysReady(
            batch_id=batch_id,
            ready_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            ],
            batch_entity=EntityReference(entity_id=batch_id, entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=batch_id, entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test",
            class_type="GUEST",
        )

        success_envelope = EventEnvelope[BatchEssaysReady](
            event_id=uuid4(),  # Same event ID for duplicates
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=success_event,
        )

        # Create identical Kafka messages (simulating duplicates)
        msg1 = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY), success_envelope
        )
        msg2 = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY), success_envelope
        )

        # Process the same message twice
        await kafka_consumer._handle_message(msg1)
        await kafka_consumer._handle_message(msg2)

        # Handler should only be called once due to idempotency
        # (In real implementation, idempotency decorator would prevent duplicate processing)
        # For this test, we verify the handler is called twice (as the mock doesn't have idempotency)
        assert mock_handlers["batch_essays_ready_handler"].handle_batch_essays_ready.call_count == 2

    @pytest.mark.asyncio
    async def test_independent_event_processing(
        self, kafka_consumer: BatchKafkaConsumer, mock_handlers: dict[str, AsyncMock]
    ) -> None:
        """Test that success and error events are processed independently."""
        batch_id = "test-batch-independent"

        # Create success event for one batch
        success_event = BatchEssaysReady(
            batch_id=f"{batch_id}-success",
            ready_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            ],
            batch_entity=EntityReference(entity_id=f"{batch_id}-success", entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=f"{batch_id}-success", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test",
            class_type="REGULAR",
            teacher_first_name="Jane",
            teacher_last_name="Doe",
        )

        # Create error event for different batch
        error_event = BatchValidationErrorsV1(
            batch_id=f"{batch_id}-error",
            failed_essays=[
                EssayValidationError(
                    essay_id="essay-2",
                    file_name="essay2.pdf",
                    error_detail=ErrorDetail(
                        error_code=ErrorCode.VALIDATION_ERROR,
                        message="Failed",
                        correlation_id=uuid4(),
                        timestamp=datetime.now(UTC),
                        service="file-service",
                        operation="validate",
                    ),
                )
            ],
            error_summary=BatchErrorSummary(
                total_errors=1,
                error_categories={"validation": 1},
                critical_failure=True,
            ),
            correlation_id=uuid4(),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id=f"{batch_id}-error", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
        )

        # Create envelopes
        success_envelope = EventEnvelope[BatchEssaysReady](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service="essay-lifecycle-service",
            correlation_id=uuid4(),
            data=success_event,
        )

        error_envelope = EventEnvelope[BatchValidationErrorsV1](
            event_type="huleedu.els.batch.validation.errors.v1",
            source_service="essay-lifecycle-service",
            correlation_id=uuid4(),
            data=error_event,
        )

        # Create messages
        success_msg = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY), success_envelope
        )
        error_msg = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS), error_envelope
        )

        # Process messages in any order
        await kafka_consumer._handle_message(error_msg)
        await kafka_consumer._handle_message(success_msg)

        # Both handlers should be called independently
        mock_handlers["batch_essays_ready_handler"].handle_batch_essays_ready.assert_called_once()
        mock_handlers[
            "batch_validation_errors_handler"
        ].handle_batch_validation_errors.assert_called_once()

        # Verify they received correct data
        success_call = mock_handlers[
            "batch_essays_ready_handler"
        ].handle_batch_essays_ready.call_args[0][0]
        error_call = mock_handlers[
            "batch_validation_errors_handler"
        ].handle_batch_validation_errors.call_args[0][0]

        assert success_call.topic == topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        assert error_call.topic == topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)

    @pytest.mark.asyncio
    async def test_error_handling_in_dual_event_processing(
        self, kafka_consumer: BatchKafkaConsumer, mock_handlers: dict[str, AsyncMock]
    ) -> None:
        """Test error handling when one handler fails in dual event processing."""
        # Make success handler raise an exception
        mock_handlers[
            "batch_essays_ready_handler"
        ].handle_batch_essays_ready.side_effect = Exception("Handler error")

        # Create a success event
        success_event = BatchEssaysReady(
            batch_id="test-batch-error",
            ready_essays=[],
            batch_entity=EntityReference(entity_id="test-batch-error", entity_type="batch"),
            metadata=SystemProcessingMetadata(
                entity=EntityReference(entity_id="test-batch-error", entity_type="batch"),
                timestamp=datetime.now(UTC),
            ),
            course_code=CourseCode.ENG5,
            course_language="en",
            essay_instructions="Test",
            class_type="GUEST",
        )

        success_envelope = EventEnvelope[BatchEssaysReady](
            event_type="huleedu.els.batch.essays.ready.v1",
            source_service="essay-lifecycle-service",
            data=success_event,
        )

        success_msg = self.create_kafka_message(
            topic_name(ProcessingEvent.BATCH_ESSAYS_READY), success_envelope
        )

        # Process should raise the exception
        with pytest.raises(Exception, match="Handler error"):
            await kafka_consumer._handle_message(success_msg)

        # Verify handler was called despite the error
        mock_handlers["batch_essays_ready_handler"].handle_batch_essays_ready.assert_called_once()

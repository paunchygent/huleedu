"""Unit tests for BOS Pipeline Orchestration components.

Tests actual business logic following 070-testing-and-quality-assurance.mdc.
Mocks only external boundaries, not internal business logic.
"""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from huleedu_service_libs.protocols import RedisClientProtocol

from services.batch_orchestrator_service.implementations.batch_essays_ready_handler import (
    BatchEssaysReadyHandler,
)
from services.batch_orchestrator_service.implementations.batch_validation_errors_handler import (
    BatchValidationErrorsHandler,
)
from services.batch_orchestrator_service.implementations.client_pipeline_request_handler import (
    ClientPipelineRequestHandler,
)
from services.batch_orchestrator_service.implementations.els_batch_phase_outcome_handler import (
    ELSBatchPhaseOutcomeHandler,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer


@pytest.mark.docker
class TestBatchKafkaConsumerBusinessLogic:
    """Test BatchKafkaConsumer business logic without overmocking."""

    @pytest.fixture
    def mock_batch_essays_ready_handler(self) -> AsyncMock:
        """Mock the BatchEssaysReadyHandler external boundary."""
        return AsyncMock(spec=BatchEssaysReadyHandler)

    @pytest.fixture
    def mock_els_batch_phase_outcome_handler(self) -> AsyncMock:
        """Mock the ELSBatchPhaseOutcomeHandler external boundary."""
        return AsyncMock(spec=ELSBatchPhaseOutcomeHandler)

    @pytest.fixture
    def mock_client_pipeline_request_handler(self) -> AsyncMock:
        """Mock the ClientPipelineRequestHandler external boundary."""
        return AsyncMock(spec=ClientPipelineRequestHandler)

    @pytest.fixture
    def mock_batch_validation_errors_handler(self) -> AsyncMock:
        """Mock the BatchValidationErrorsHandler external boundary."""
        return AsyncMock(spec=BatchValidationErrorsHandler)

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for idempotency support."""
        return AsyncMock(spec=RedisClientProtocol)

    @pytest.fixture
    def mock_batch_content_provisioning_completed_handler(self) -> AsyncMock:
        """Mock the BatchContentProvisioningCompletedHandler for Phase 1."""
        from services.batch_orchestrator_service.implementations.batch_content_provisioning_completed_handler import (
            BatchContentProvisioningCompletedHandler,
        )

        return AsyncMock(spec=BatchContentProvisioningCompletedHandler)

    @pytest.fixture
    def mock_student_associations_confirmed_handler(self) -> AsyncMock:
        """Mock the StudentAssociationsConfirmedHandler for Phase 1."""
        from services.batch_orchestrator_service.implementations.student_associations_confirmed_handler import (
            StudentAssociationsConfirmedHandler,
        )

        return AsyncMock(spec=StudentAssociationsConfirmedHandler)

    @pytest.fixture
    def kafka_consumer(
        self,
        mock_batch_essays_ready_handler: AsyncMock,
        mock_batch_content_provisioning_completed_handler: AsyncMock,
        mock_batch_validation_errors_handler: AsyncMock,
        mock_els_batch_phase_outcome_handler: AsyncMock,
        mock_client_pipeline_request_handler: AsyncMock,
        mock_student_associations_confirmed_handler: AsyncMock,
        mock_redis_client: AsyncMock,
    ) -> BatchKafkaConsumer:
        """Create Kafka consumer with mocked external dependencies."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-group",
            batch_essays_ready_handler=mock_batch_essays_ready_handler,
            batch_content_provisioning_completed_handler=mock_batch_content_provisioning_completed_handler,
            batch_validation_errors_handler=mock_batch_validation_errors_handler,
            els_batch_phase_outcome_handler=mock_els_batch_phase_outcome_handler,
            client_pipeline_request_handler=mock_client_pipeline_request_handler,
            student_associations_confirmed_handler=mock_student_associations_confirmed_handler,
            redis_client=mock_redis_client,
        )

    async def test_els_batch_phase_outcome_message_routing(
        self,
        kafka_consumer: BatchKafkaConsumer,
        mock_els_batch_phase_outcome_handler: AsyncMock,
    ) -> None:
        """Test that ELS batch phase outcome messages are routed to the correct handler."""
        # Mock Kafka message for ELS batch phase outcome
        mock_message = Mock()
        mock_message.topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        mock_message.partition = 0
        mock_message.offset = 123

        # Execute the message routing logic
        await kafka_consumer._handle_message(mock_message)

        # Verify the correct handler was called
        handler_mock = cast(AsyncMock, kafka_consumer.els_batch_phase_outcome_handler)
        handler_mock.handle_els_batch_phase_outcome.assert_called_once_with(
            mock_message,
        )

    async def test_batch_essays_ready_message_routing(
        self,
        kafka_consumer: BatchKafkaConsumer,
        mock_batch_essays_ready_handler: AsyncMock,
    ) -> None:
        """Test that BatchEssaysReady messages are routed to the correct handler."""
        # Mock Kafka message for BatchEssaysReady
        mock_message = Mock()
        mock_message.topic = topic_name(ProcessingEvent.BATCH_ESSAYS_READY)  # Correct topic name
        mock_message.partition = 0
        mock_message.offset = 456

        # Execute the message routing logic
        await kafka_consumer._handle_message(mock_message)

        # Verify the correct handler was called
        mock_batch_essays_ready_handler.handle_batch_essays_ready.assert_called_once_with(
            mock_message,
        )

    async def test_client_pipeline_request_message_routing(
        self,
        kafka_consumer: BatchKafkaConsumer,
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that ClientBatchPipelineRequest messages are routed to the correct handler."""
        # Mock Kafka message for ClientBatchPipelineRequest
        mock_message = Mock()
        mock_message.topic = topic_name(ProcessingEvent.CLIENT_BATCH_PIPELINE_REQUEST)
        mock_message.partition = 0
        mock_message.offset = 789

        # Execute the message routing logic
        await kafka_consumer._handle_message(mock_message)

        # Verify the correct handler was called
        mock_client_pipeline_request_handler.handle_client_pipeline_request.assert_called_once_with(
            mock_message,
        )

    async def test_unknown_topic_handling(
        self,
        kafka_consumer: BatchKafkaConsumer,
        mock_batch_essays_ready_handler: AsyncMock,
        mock_els_batch_phase_outcome_handler: AsyncMock,
        mock_client_pipeline_request_handler: AsyncMock,
    ) -> None:
        """Test that unknown topics are handled gracefully without calling any handlers."""
        # Mock Kafka message for unknown topic
        mock_message = Mock()
        mock_message.topic = "unknown.topic.name"
        mock_message.partition = 0
        mock_message.offset = 999

        # Execute the message routing logic (should not raise exception)
        await kafka_consumer._handle_message(mock_message)

        # Verify no handlers were called
        mock_batch_essays_ready_handler.handle_batch_essays_ready.assert_not_called()
        mock_els_batch_phase_outcome_handler.handle_els_batch_phase_outcome.assert_not_called()
        mock_client_pipeline_request_handler.handle_client_pipeline_request.assert_not_called()


class TestELSBatchPhaseOutcomeHandler:
    """Test ELSBatchPhaseOutcomeHandler business logic without overmocking."""

    @pytest.fixture
    def mock_phase_coordinator(self) -> AsyncMock:
        """Mock the external boundary - phase coordinator protocol."""
        return AsyncMock()

    @pytest.fixture
    def outcome_handler(self, mock_phase_coordinator: AsyncMock) -> ELSBatchPhaseOutcomeHandler:
        """Create ELS outcome handler with mocked external dependencies."""
        return ELSBatchPhaseOutcomeHandler(phase_coordinator=mock_phase_coordinator)

    async def test_els_batch_phase_outcome_processing_with_data_propagation(
        self,
        outcome_handler: ELSBatchPhaseOutcomeHandler,
        mock_phase_coordinator: AsyncMock,
    ) -> None:
        """Test processing of ELSBatchPhaseOutcomeV1 with data propagation to next phase."""
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Create valid processed essays with updated text_storage_id from spellcheck
        processed_essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id="corrected_original_text_1",  # Updated from spellcheck
            ),
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id="corrected_original_text_2",  # Updated from spellcheck
            ),
        ]

        # Create ELS outcome event
        from common_core.pipeline_models import PhaseName
        from common_core.status_enums import BatchStatus

        outcome_data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=processed_essays,
            failed_essay_ids=["essay-3"],
            correlation_id=correlation_id,
        )

        # Create event envelope
        event_envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
            event_type="els.batch.phase.outcome.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=outcome_data,
        )

        # Mock Kafka message
        mock_message = Mock()
        mock_message.value = event_envelope.model_dump_json().encode()
        mock_message.topic = topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        mock_message.partition = 0
        mock_message.offset = 123

        # Execute the business logic
        await outcome_handler.handle_els_batch_phase_outcome(mock_message)

        # Verify the external boundary was called with the new signature including processed essays
        mock_phase_coordinator.handle_phase_concluded.assert_called_once_with(
            batch_id=batch_id,
            completed_phase=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            correlation_id=correlation_id,
            processed_essays_for_next_phase=processed_essays,  # NEW: Phase 3 data propagation
        )

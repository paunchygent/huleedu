"""Unit tests for BOS Pipeline Orchestration components.

Tests actual business logic following 070-testing-and-quality-assurance.mdc.
Mocks only external boundaries, not internal business logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer


class TestBatchKafkaConsumerBusinessLogic:
    """Test BatchKafkaConsumer business logic without overmocking."""

    @pytest.fixture
    def mock_batch_processing_service(self):
        """Mock the external boundary - batch processing service protocol."""
        return AsyncMock()

    @pytest.fixture
    def kafka_consumer(self, mock_batch_processing_service):
        """Create Kafka consumer with mocked external dependencies."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-group",
            event_publisher=AsyncMock(),
            batch_repo=AsyncMock(),
            phase_coordinator=mock_batch_processing_service,
        )

    async def test_els_batch_phase_outcome_message_processing(
        self, kafka_consumer, mock_batch_processing_service
    ):
        """Test processing of ELSBatchPhaseOutcomeV1 Kafka message."""
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Create valid processed essays
        processed_essays = [
            EssayProcessingInputRefV1(
                essay_id=str(uuid4()),
                text_storage_id=str(uuid4()),
            ),
        ]

        # Create ELS outcome event
        outcome_data = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            processed_essays=processed_essays,
            failed_essay_ids=["essay-2"],
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
        mock_message.topic = "huleedu.els.batch_phase.outcome.v1"
        mock_message.partition = 0
        mock_message.offset = 123

        # Execute the business logic
        await kafka_consumer._handle_els_batch_phase_outcome(mock_message)

        # Verify the external boundary was called correctly
        mock_batch_processing_service.handle_phase_concluded.assert_called_once_with(
            batch_id,
            "spellcheck",
            "COMPLETED_SUCCESSFULLY",
            str(correlation_id),
        )

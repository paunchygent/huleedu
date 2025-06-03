"""Integration tests for BOS-ELS phase coordination.

Tests the communication flow between Batch Orchestrator Service (BOS) and 
Essay Lifecycle Service (ELS) using real business logic components.

Following 070-testing-and-quality-assurance.mdc:
- Mock only external boundaries (phase coordinator, specialized services, storage)
- Test real business logic components (BatchKafkaConsumer, event serialization)
- Limited scope component interactions (not full E2E)

FIXED INTEGRATION TESTS:
- Tests actual BatchKafkaConsumer._handle_els_batch_phase_outcome() method
- Uses real Kafka message structure (msg.value, msg.topic)
- Validates JSON roundtrip serialization/deserialization
- Tests error handling for malformed messages
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EssayProcessingInputRefV1
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer


class RealKafkaMessage:
    """Real Kafka message structure for integration testing."""

    def __init__(self, envelope: EventEnvelope, topic: str):
        """Create Kafka message with real .value and .topic attributes."""
        self.value = envelope.model_dump_json().encode('utf-8')
        self.topic = topic
        self.partition = 0
        self.offset = 123


class TestBosElsPhaseCoordination:
    """Test BOS-ELS coordination using real business logic components."""

    @pytest.fixture
    def mock_phase_coordinator(self):
        """Mock the external boundary - phase coordinator protocol."""
        return AsyncMock()

    @pytest.fixture
    def kafka_consumer(self, mock_phase_coordinator):
        """Create real BatchKafkaConsumer with mocked external dependencies."""
        return BatchKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-group",
            event_publisher=AsyncMock(),
            batch_repo=AsyncMock(),
            phase_coordinator=mock_phase_coordinator,
        )

    async def test_real_bos_els_kafka_integration(
        self, kafka_consumer, mock_phase_coordinator
    ):
        """Test actual BatchKafkaConsumer._handle_els_batch_phase_outcome()
         with real Kafka message structure."""
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Create valid processed essays with updated text_storage_id
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
        outcome_event = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            processed_essays=processed_essays,
            failed_essay_ids=["essay-3"],  # One essay failed
            correlation_id=correlation_id,
        )

        # Create event envelope following Pydantic v2 standards
        envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
            event_type="huleedu.els.batch_phase.outcome.v1",
            source_service="essay-lifecycle-service",
            correlation_id=correlation_id,
            data=outcome_event,
        )

        # Create real Kafka message structure
        kafka_msg = RealKafkaMessage(
            envelope=envelope,
            topic="huleedu.els.batch_phase.outcome.v1"
        )

        # Test ACTUAL BatchKafkaConsumer method with real JSON serialization
        await kafka_consumer._handle_els_batch_phase_outcome(kafka_msg)

        # Verify phase coordinator called with correct individual parameters
        mock_phase_coordinator.handle_phase_concluded.assert_called_once_with(
            batch_id,                     # batch_id string
            "spellcheck",                 # phase_name string
            "COMPLETED_SUCCESSFULLY",     # phase_status string
            str(correlation_id),          # correlation_id as string
        )

    async def test_kafka_message_json_deserialization_error_handling(
        self, kafka_consumer, mock_phase_coordinator
    ):
        """Test error handling for malformed Kafka message JSON."""
        # Create malformed Kafka message
        malformed_msg = Mock()
        malformed_msg.value = b"invalid json content"
        malformed_msg.topic = "huleedu.els.batch_phase.outcome.v1"
        malformed_msg.partition = 0
        malformed_msg.offset = 456

        # Should handle the error gracefully without crashing
        with pytest.raises(json.JSONDecodeError):
            await kafka_consumer._handle_els_batch_phase_outcome(malformed_msg)

        # Phase coordinator should not be called for malformed messages
        mock_phase_coordinator.handle_phase_concluded.assert_not_called()

    async def test_missing_required_fields_in_outcome_event(
        self, kafka_consumer, mock_phase_coordinator
    ):
        """Test handling of ELSBatchPhaseOutcomeV1 events with missing required fields."""
        correlation_id = uuid4()

        # Create event envelope with incomplete data (missing batch_id)
        incomplete_data = {
            "phase_name": "spellcheck",
            "phase_status": "COMPLETED_SUCCESSFULLY",
            "processed_essays": [],
            "failed_essay_ids": [],
            "correlation_id": str(correlation_id),
            # batch_id is missing
        }

        envelope_data = {
            "event_type": "huleedu.els.batch_phase.outcome.v1",
            "source_service": "essay-lifecycle-service",
            "correlation_id": str(correlation_id),
            "data": incomplete_data,
        }

        # Create Kafka message with incomplete event
        incomplete_msg = Mock()
        incomplete_msg.value = json.dumps(envelope_data).encode('utf-8')
        incomplete_msg.topic = "huleedu.els.batch_phase.outcome.v1"

        # Should handle missing fields gracefully
        await kafka_consumer._handle_els_batch_phase_outcome(incomplete_msg)

        # Phase coordinator should not be called for incomplete events
        mock_phase_coordinator.handle_phase_concluded.assert_not_called()

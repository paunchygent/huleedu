"""
Comprehensive tests for Kafka DLQ Producer Implementation.

Tests focus on message publishing behavior, schema compliance, error handling,
and integration with the Kafka infrastructure. Only mocks external Kafka boundaries.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import BaseModel

from common_core.events.envelope import EventEnvelope
from services.batch_conductor_service.implementations.kafka_dlq_producer_impl import (
    KafkaDlqProducerImpl,
)


class MockEntityRef(BaseModel):
    """Test model for entity references."""

    entity_id: str
    parent_id: str


class MockEntityRefNoParent(BaseModel):
    """Test model for entity references without parent_id."""

    entity_id: str


class MockProcessingResult(BaseModel):
    """Test model for processing results."""

    status: str
    errors_found: int
    corrections: list[str]


class MockEventData(BaseModel):
    """Test model for event data in DLQ producer tests."""

    batch_id: str
    entity_ref: MockEntityRef
    processing_result: MockProcessingResult


class MockSimpleEventData(BaseModel):
    """Simple test model for basic event data."""

    batch_id: str
    other_data: str


class MockEntityOnlyEventData(BaseModel):
    """Test model for events with only entity reference."""

    entity_ref: MockEntityRef


class MockEntityNoParentEventData(BaseModel):
    """Test model for events with entity reference without parent_id."""

    entity_ref: MockEntityRefNoParent


class MockEntityIdEventData(BaseModel):
    """Test model for events with entity_id."""

    entity_id: str
    status: str = "completed"


class MockEmptyEventData(BaseModel):
    """Test model for empty event data."""

    random_data: str = "no_key_fields"
    status: str = "failed"


class MockAnalysisResult(BaseModel):
    """Test model for analysis result."""

    text: str


class MockLargeEventData(BaseModel):
    """Test model for large event data."""

    batch_id: str
    large_text_field: str
    essay_content: str
    analysis_results: list[MockAnalysisResult]


class MockPipelineFailureEventData(BaseModel):
    """Test model for pipeline failure event data."""

    batch_id: str
    requested_pipeline: str
    failure_reason: str
    error_details: str


class MockSpellcheckFailureEventData(BaseModel):
    """Test model for spellcheck failure event data."""

    batch_id: str
    entity_ref: MockEntityRef
    failure_reason: str
    error_details: str


class MockConcurrentFailureEventData(BaseModel):
    """Test model for concurrent failure event data."""

    batch_id: str
    failure_sequence: int


class TestKafkaDlqProducerBehavior:
    """Test business behavior of DLQ producer with realistic failure scenarios."""

    @pytest.fixture
    def mock_kafka_bus(self) -> MagicMock:
        """Mock Kafka bus that tracks message publications."""
        mock_bus = MagicMock()
        mock_producer = AsyncMock()
        mock_producer.send.return_value = None  # Successful send
        mock_bus.producer = mock_producer
        return mock_bus

    @pytest.fixture
    def dlq_producer(self, mock_kafka_bus: MagicMock) -> KafkaDlqProducerImpl:
        """Create DLQ producer with mocked Kafka infrastructure."""
        return KafkaDlqProducerImpl(kafka_bus=mock_kafka_bus)

    @pytest.fixture
    def sample_event_envelope(self) -> EventEnvelope[MockEventData]:
        """Create realistic event envelope for testing."""
        return EventEnvelope[MockEventData](
            event_id=uuid4(),
            event_type="huleedu.spellcheck.result.v1",
            event_timestamp=datetime.now(UTC),
            source_service="spellchecker_service",
            correlation_id=uuid4(),
            data=MockEventData(
                batch_id="batch_essays_001",
                entity_ref=MockEntityRef(entity_id="essay_123", parent_id="batch_essays_001"),
                processing_result=MockProcessingResult(
                    status="completed",
                    errors_found=3,
                    corrections=["teh -> the", "recieve -> receive", "occured -> occurred"],
                ),
            ),
        )

    # Test Category 1: Successful Message Publication

    async def test_successful_dlq_publication_with_event_envelope(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test successful DLQ publication with EventEnvelope input."""
        # Arrange
        base_topic = "huleedu.spellcheck.results"
        dlq_reason = "ValidationFailed"
        additional_metadata = {"retry_count": 3, "last_error": "Schema validation failed"}

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic=base_topic,
            failed_event_envelope=sample_event_envelope,
            dlq_reason=dlq_reason,
            additional_metadata=additional_metadata,
        )

        # Assert
        assert result is True

        # Verify Kafka producer was called correctly
        mock_kafka_bus.producer.send.assert_called_once()
        send_call = mock_kafka_bus.producer.send.call_args

        # Check topic naming
        assert send_call.kwargs["topic"] == "huleedu.spellcheck.results.DLQ"

        # Check message key extraction - should extract batch_id from event data
        assert send_call.kwargs["key"] == "batch_essays_001"

        # Check message structure
        published_message = json.loads(send_call.kwargs["value"])
        assert published_message["schema_version"] == 1
        assert published_message["dlq_reason"] == dlq_reason
        assert published_message["service"] == "batch_conductor_service"
        assert published_message["additional_metadata"] == additional_metadata

        # Verify original event envelope is preserved
        assert (
            published_message["failed_event_envelope"]["event_type"]
            == "huleedu.spellcheck.result.v1"
        )
        assert (
            published_message["failed_event_envelope"]["source_service"] == "spellchecker_service"
        )

    async def test_successful_dlq_publication_with_dict_input(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test successful DLQ publication with dictionary input."""
        # Arrange
        base_topic = "huleedu.batch.processing"
        dlq_reason = "ProcessingTimeout"

        # Create a realistic dictionary event (simulating a serialized event)
        dict_event = {
            "event_id": str(uuid4()),
            "event_type": "huleedu.batch.timeout.v1",
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "batch_orchestrator_service",
            "data": {
                "batch_id": "batch_timeout_001",
                "timeout_duration": "300s",
                "incomplete_essays": ["essay_456", "essay_789"],
            },
        }

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic=base_topic, failed_event_envelope=dict_event, dlq_reason=dlq_reason
        )

        # Assert
        assert result is True

        # Verify message structure
        send_call = mock_kafka_bus.producer.send.call_args
        published_message = json.loads(send_call.kwargs["value"])

        assert published_message["schema_version"] == 1
        assert published_message["dlq_reason"] == dlq_reason
        assert published_message["failed_event_envelope"] == dict_event
        assert (
            "additional_metadata" not in published_message
        )  # Should not be present when not provided

    async def test_dlq_publication_without_additional_metadata(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test DLQ publication without additional metadata."""
        # Arrange
        base_topic = "huleedu.cj.assessment.results"
        dlq_reason = "CycleDetected"

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic=base_topic,
            failed_event_envelope=sample_event_envelope,
            dlq_reason=dlq_reason,
        )

        # Assert
        assert result is True

        # Verify no additional metadata is included
        send_call = mock_kafka_bus.producer.send.call_args
        published_message = json.loads(send_call.kwargs["value"])
        assert "additional_metadata" not in published_message

    # Test Category 2: Message Schema and Format Validation

    async def test_dlq_message_schema_compliance(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that DLQ messages follow the required schema exactly."""
        # Arrange
        base_topic = "huleedu.ai.feedback.results"
        dlq_reason = "ModelUnavailable"
        test_metadata = {"model_version": "gpt-4", "region": "us-east-1"}

        # Act
        await dlq_producer.publish_to_dlq(
            base_topic=base_topic,
            failed_event_envelope=sample_event_envelope,
            dlq_reason=dlq_reason,
            additional_metadata=test_metadata,
        )

        # Assert - Verify exact schema structure
        send_call = mock_kafka_bus.producer.send.call_args
        published_message = json.loads(send_call.kwargs["value"])

        # Check required fields
        required_fields = [
            "schema_version",
            "failed_event_envelope",
            "dlq_reason",
            "timestamp",
            "service",
        ]
        for field in required_fields:
            assert field in published_message, f"Required field '{field}' missing from DLQ message"

        # Check field types and values
        assert isinstance(published_message["schema_version"], int)
        assert published_message["schema_version"] == 1
        assert isinstance(published_message["failed_event_envelope"], dict)
        assert isinstance(published_message["dlq_reason"], str)
        assert isinstance(published_message["timestamp"], str)
        assert published_message["service"] == "batch_conductor_service"

        # Verify timestamp is valid ISO format
        timestamp_str = published_message["timestamp"]
        parsed_timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        assert parsed_timestamp.tzinfo is not None  # Should be timezone-aware

    async def test_dlq_topic_naming_convention(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test that DLQ topic names follow the .DLQ convention."""
        # Arrange - Test various base topic formats
        base_topics = [
            "huleedu.spellcheck.results",
            "huleedu.batch.processing.status",
            "simple.topic",
            "complex.nested.topic.structure",
        ]

        for base_topic in base_topics:
            # Act
            await dlq_producer.publish_to_dlq(
                base_topic=base_topic,
                failed_event_envelope=sample_event_envelope,
                dlq_reason="MockReason",
            )

            # Assert
            send_call = mock_kafka_bus.producer.send.call_args
            expected_dlq_topic = f"{base_topic}.DLQ"
            assert send_call.kwargs["topic"] == expected_dlq_topic

    # Test Category 3: Message Key Extraction and Partitioning

    async def test_message_key_extraction_from_batch_id(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test key extraction when event data has direct batch_id."""
        # Arrange - Event with direct batch_id in data
        event_with_batch_id = EventEnvelope[MockSimpleEventData](
            event_id=uuid4(),
            event_type="huleedu.test.event.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_service",
            data=MockSimpleEventData(batch_id="batch_direct_123", other_data="test_value"),
        )

        # Act
        await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=event_with_batch_id,
            dlq_reason="MockReason",
        )

        # Assert - Should use direct batch_id as key
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["key"] == "batch_direct_123"

    async def test_message_key_extraction_from_entity_ref_parent_id(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test key extraction from entity_ref.parent_id when no direct batch_id."""
        # Arrange - Event with entity_ref structure
        event_with_entity_ref = EventEnvelope[MockEntityOnlyEventData](
            event_id=uuid4(),
            event_type="huleedu.test.event.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_service",
            data=MockEntityOnlyEventData(
                entity_ref=MockEntityRef(entity_id="essay_456", parent_id="batch_parent_789")
            ),
        )

        # Act
        await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=event_with_entity_ref,
            dlq_reason="MockReason",
        )

        # Assert - Should use entity_ref.parent_id as key
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["key"] == "batch_parent_789"

    async def test_message_key_extraction_from_entity_ref_entity_id(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test key extraction from entity_ref.entity_id when no parent_id."""
        # Arrange - Event with entity_ref but no parent_id
        event_with_entity_id = EventEnvelope[MockEntityNoParentEventData](
            event_id=uuid4(),
            event_type="huleedu.test.event.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_service",
            data=MockEntityNoParentEventData(
                entity_ref=MockEntityRefNoParent(entity_id="standalone_entity_999")
            ),
        )

        # Act
        await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=event_with_entity_id,
            dlq_reason="MockReason",
        )

        # Assert - Should use entity_ref.entity_id as key
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["key"] == "standalone_entity_999"

    async def test_message_key_extraction_fallback_to_none(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test key extraction fallback when no suitable key fields are available."""
        # Arrange - Event with no batch_id or entity_ref
        event_without_key_fields = EventEnvelope[MockEmptyEventData](
            event_id=uuid4(),
            event_type="huleedu.test.event.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_service",
            data=MockEmptyEventData(),
        )

        # Act
        await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=event_without_key_fields,
            dlq_reason="MockReason",
        )

        # Assert - Should use None as key when no suitable fields found
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["key"] is None

    # Test Category 4: Error Handling and Resilience

    async def test_kafka_send_failure_handling(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Test handling of Kafka producer send failures."""
        # Arrange - Make Kafka send fail
        mock_kafka_bus.producer.send.side_effect = Exception("Kafka broker unavailable")

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=sample_event_envelope,
            dlq_reason="MockFailure",
        )

        # Assert - Should return False and not raise exception
        assert result is False

        # Verify send was attempted
        mock_kafka_bus.producer.send.assert_called_once()

    async def test_malformed_event_envelope_handling(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test handling of malformed event envelopes."""
        # Arrange - Malformed event envelope (missing required fields)
        malformed_event = {"incomplete": "event", "missing_required_fields": True}

        # Act - Should not raise exception
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=malformed_event,
            dlq_reason="MalformedEvent",
        )

        # Assert - Should still attempt to publish (graceful handling)
        assert result is True  # Should succeed because we're just serializing the dict as-is

        # Verify the malformed event was preserved in the DLQ message
        send_call = mock_kafka_bus.producer.send.call_args
        published_message = json.loads(send_call.kwargs["value"])
        assert published_message["failed_event_envelope"] == malformed_event

    async def test_json_serialization_error_handling(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test handling of JSON serialization errors."""
        # Arrange - Create event with non-serializable data
        from datetime import datetime

        class NonSerializableData:
            def __init__(self):
                self.data = "non-serializable"

        non_serializable_event = {
            "event_id": "test-id",
            "non_serializable_object": NonSerializableData(),
            "datetime_object": datetime.now(),  # datetime objects not JSON serializable by default
        }

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=non_serializable_event,
            dlq_reason="SerializationTest",
        )

        # Assert - Should handle serialization error gracefully
        assert result is False

    # Test Category 5: Integration and Real-world Scenarios

    async def test_pipeline_resolution_failure_dlq_scenario(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test realistic pipeline resolution failure DLQ scenario."""
        # Arrange - Simulate a pipeline resolution failure event
        pipeline_failure_event = EventEnvelope[MockPipelineFailureEventData](
            event_id=uuid4(),
            event_type="huleedu.batch.pipeline.resolution.failed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="batch_conductor_service",
            correlation_id=uuid4(),
            data=MockPipelineFailureEventData(
                batch_id="batch_pipeline_fail_001",
                requested_pipeline="ai_feedback",
                failure_reason="dependency_resolution_failed",
                error_details="Circular dependency: ai_feedback -> spellcheck -> ai_feedback",
            ),
        )

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.pipelines.resolution",
            failed_event_envelope=pipeline_failure_event,
            dlq_reason="dependency_resolution_failed",
            additional_metadata={
                "batch_id": "batch_pipeline_fail_001",
                "requested_pipeline": "ai_feedback",
                "error_details": "Circular dependency: ai_feedback -> spellcheck -> ai_feedback",
            },
        )

        # Assert
        assert result is True

        # Verify realistic DLQ structure for pipeline failures
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["topic"] == "huleedu.pipelines.resolution.DLQ"
        assert send_call.kwargs["key"] == "batch_pipeline_fail_001"

        published_message = json.loads(send_call.kwargs["value"])
        assert published_message["dlq_reason"] == "dependency_resolution_failed"
        assert "batch_pipeline_fail_001" in str(published_message["additional_metadata"])

    async def test_spellcheck_result_failure_dlq_scenario(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test realistic spellcheck service failure DLQ scenario."""
        # Arrange - Simulate a spellcheck processing failure
        spellcheck_failure_event = EventEnvelope[MockSpellcheckFailureEventData](
            event_id=uuid4(),
            event_type="huleedu.spellcheck.processing.failed.v1",
            event_timestamp=datetime.now(UTC),
            source_service="spellchecker_service",
            correlation_id=uuid4(),
            data=MockSpellcheckFailureEventData(
                batch_id="batch_spellcheck_fail_001",
                entity_ref=MockEntityRef(
                    entity_id="essay_failed_001",
                    parent_id="batch_spellcheck_fail_001",
                ),
                failure_reason="text_encoding_error",
                error_details="Unable to decode essay text: invalid UTF-8 sequence",
            ),
        )

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.spellcheck.results",
            failed_event_envelope=spellcheck_failure_event,
            dlq_reason="text_encoding_error",
            additional_metadata={
                "essay_id": "essay_failed_001",
                "encoding_attempted": "utf-8",
                "retry_count": 3,
            },
        )

        # Assert
        assert result is True

        # Verify message partitioning uses batch_id
        send_call = mock_kafka_bus.producer.send.call_args
        assert send_call.kwargs["key"] == "batch_spellcheck_fail_001"

    async def test_concurrent_dlq_publications(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test that concurrent DLQ publications work independently."""
        # Arrange - Multiple different failure events
        failure_events = []
        for i in range(3):
            event = EventEnvelope[MockConcurrentFailureEventData](
                event_id=uuid4(),
                event_type=f"huleedu.test.failure.v{i + 1}",
                event_timestamp=datetime.now(UTC),
                source_service="test_service",
                data=MockConcurrentFailureEventData(
                    batch_id=f"batch_concurrent_{i + 1}", failure_sequence=i + 1
                ),
            )
            failure_events.append(event)

        # Act - Publish concurrently
        import asyncio

        results = await asyncio.gather(
            *[
                dlq_producer.publish_to_dlq(
                    base_topic=f"huleedu.test.topic_{i + 1}",
                    failed_event_envelope=event,
                    dlq_reason=f"ConcurrentFailure_{i + 1}",
                )
                for i, event in enumerate(failure_events)
            ]
        )

        # Assert - All should succeed independently
        assert all(results)
        assert len(results) == 3

        # Verify all calls were made
        assert mock_kafka_bus.producer.send.call_count == 3

    async def test_dlq_publish_timeout_returns_false(
        self,
        dlq_producer: KafkaDlqProducerImpl,
        mock_kafka_bus: MagicMock,
        sample_event_envelope: EventEnvelope,
    ) -> None:
        """Timeouts during DLQ publish should be logged and reported as False without raising."""

        import asyncio

        mock_kafka_bus.producer.send.side_effect = asyncio.TimeoutError

        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.test.topic",
            failed_event_envelope=sample_event_envelope,
            dlq_reason="TimeoutScenario",
        )

        assert result is False
        mock_kafka_bus.producer.send.assert_called_once()

    async def test_large_event_data_handling(
        self, dlq_producer: KafkaDlqProducerImpl, mock_kafka_bus: MagicMock
    ) -> None:
        """Test handling of large event data payloads."""
        # Arrange - Create event with large data payload
        large_text = "x" * 10000  # 10KB of text
        large_data_event = EventEnvelope[MockLargeEventData](
            event_id=uuid4(),
            event_type="huleedu.large.data.event.v1",
            event_timestamp=datetime.now(UTC),
            source_service="test_service",
            data=MockLargeEventData(
                batch_id="batch_large_data_001",
                large_text_field=large_text,
                essay_content=large_text,
                analysis_results=[MockAnalysisResult(text=large_text[:1000]) for _ in range(10)],
            ),
        )

        # Act
        result = await dlq_producer.publish_to_dlq(
            base_topic="huleedu.large.data.topic",
            failed_event_envelope=large_data_event,
            dlq_reason="LargeDataProcessingFailure",
        )

        # Assert - Should handle large payloads successfully
        assert result is True

        # Verify the large data was preserved
        send_call = mock_kafka_bus.producer.send.call_args
        published_message = json.loads(send_call.kwargs["value"])
        original_data = published_message["failed_event_envelope"]["data"]
        assert len(original_data["large_text_field"]) == 10000
        assert len(original_data["analysis_results"]) == 10

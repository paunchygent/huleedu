"""
Comprehensive tests for BCS Kafka consumer event processing.

Tests focus on business behavior and realistic scenarios rather than implementation details.
Only mocks external protocol boundaries, never internal business logic.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from common_core.event_enums import ProcessingEvent, topic_name
from services.batch_conductor_service.kafka_consumer import BCSKafkaConsumer


class TestBCSKafkaConsumerBehavior:
    """Test business behavior of BCS Kafka consumer with realistic scenarios."""

    @pytest.fixture
    def mock_batch_state_repo(self) -> AsyncMock:
        """Mock BatchStateRepository for boundary testing."""
        mock = AsyncMock()
        mock.record_essay_step_completion.return_value = True
        return mock

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock RedisClient for boundary testing."""
        mock = AsyncMock()
        mock.set_if_not_exists.return_value = True
        return mock

    @pytest.fixture
    def mock_kafka_consumer(self) -> AsyncMock:
        """Mock AIOKafkaConsumer for testing consumer lifecycle."""
        mock = AsyncMock()
        mock.start.return_value = None
        mock.stop.return_value = None
        mock.commit.return_value = None
        return mock

    @pytest.fixture
    def kafka_consumer(
        self, mock_batch_state_repo: AsyncMock, mock_redis_client: AsyncMock
    ) -> BCSKafkaConsumer:
        """Create BCSKafkaConsumer with mocked dependencies."""
        return BCSKafkaConsumer(
            kafka_bootstrap_servers="localhost:9092",
            consumer_group="test-group",
            batch_state_repo=mock_batch_state_repo,
            redis_client=mock_redis_client,
        )

    @pytest.fixture
    def sample_spellcheck_message_data(self) -> dict:
        """Create a sample spellcheck event message that matches the expected structure."""
        return {
            "event_id": "550e8400-e29b-41d4-a716-446655440000",
            "event_type": topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED),
            "event_timestamp": "2024-01-01T00:00:00Z",
            "source_service": "spell-checker-service",
            "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
            "data": {
                "entity_id": "essay-123",
                "batch_id": "batch-456",
                "correlation_id": "550e8400-e29b-41d4-a716-446655440001",
                "status": "completed",  # ProcessingStatus.COMPLETED (lowercase for enum)
                "corrected_text_storage_id": "text-storage-123",
                "error_code": None,
                "processing_duration_ms": 1500,
                "timestamp": "2024-01-01T12:00:00Z",
            },
        }

    @pytest.fixture
    def sample_cj_assessment_message_data(self) -> dict:
        """Create a sample CJ assessment event message."""
        return {
            "event_id": str(uuid4()),
            "event_type": topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
            "event_timestamp": datetime.now(UTC).isoformat(),
            "source_service": "cj-assessment-service",
            "correlation_id": str(uuid4()),
            "data": {
                "event_name": "cj_assessment.completed",
                "cj_assessment_job_id": "cj_job_789",
                "entity_id": "batch-789",
                "entity_type": "batch",
                "parent_id": None,
                "status": "completed_successfully",
                "system_metadata": {
                    "entity_id": "batch-789",
                    "entity_type": "batch",
                    "parent_id": None,
                    "processing_stage": "completed",
                    "event": "cj_assessment_completed",
                },
                "processing_summary": {
                    "total_essays": 3,
                    "successful": 3,
                    "failed": 0,
                    "successful_essay_ids": ["essay-001", "essay-002", "essay-003"],
                    "failed_essay_ids": [],
                    "processing_time_seconds": 5.2,
                },
            },
        }

    # Test Category 1: Spellcheck Event Processing

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_spellcheck_completion_processing(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test successful processing of spellcheck completion event."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act
        await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

        # Assert
        mock_batch_state_repo.record_essay_step_completion.assert_called_once()
        call_args = mock_batch_state_repo.record_essay_step_completion.call_args

        assert call_args[1]["batch_id"] == "batch-456"
        assert call_args[1]["essay_id"] == "essay-123"
        assert call_args[1]["step_name"] == "spellcheck"
        assert call_args[1]["metadata"]["completion_status"] == "success"
        assert call_args[1]["metadata"]["status"] == "completed"  # ProcessingStatus.COMPLETED.value

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_spellcheck_failure_processing(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test processing of spellcheck failure event."""
        # Arrange
        sample_spellcheck_message_data["data"]["status"] = (
            "failed"  # ProcessingStatus.FAILED (lowercase for enum)
        )
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act
        await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

        # Assert
        mock_batch_state_repo.record_essay_step_completion.assert_called_once()
        call_args = mock_batch_state_repo.record_essay_step_completion.call_args
        assert call_args[1]["metadata"]["completion_status"] == "failed"

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_spellcheck_missing_batch_id(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test handling of spellcheck event with missing batch_id.

        The handler should raise a ValidationError when batch_id is None,
        and no phase completion should be recorded.
        """
        # Arrange - Set batch_id to None (invalid)
        sample_spellcheck_message_data["data"]["batch_id"] = None

        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act & Assert - The handler should raise ValidationError
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

        # Verify the error is about the batch_id field
        assert "batch_id" in str(exc_info.value)

        # Assert - No phase completion should be recorded due to validation error
        mock_batch_state_repo.record_essay_step_completion.assert_not_called()
        mock_batch_state_repo.record_phase_completion.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_spellcheck_batch_id_from_system_metadata(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test batch_id extraction and validation."""
        # Arrange - Ensure batch_id is present in thin event
        sample_spellcheck_message_data["data"]["batch_id"] = "batch-from-event"

        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act
        await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

        # Assert
        mock_batch_state_repo.record_essay_step_completion.assert_called_once()
        call_args = mock_batch_state_repo.record_essay_step_completion.call_args
        assert call_args[1]["batch_id"] == "batch-from-event"

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_spellcheck_deserialization_error(
        self, kafka_consumer: BCSKafkaConsumer, mock_batch_state_repo: AsyncMock
    ) -> None:
        """Test handling of spellcheck message deserialization errors."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = b"invalid json"  # Must be bytes for .decode() to work
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act & Assert - Should raise validation error for invalid JSON structure
        from pydantic import ValidationError

        with pytest.raises((json.JSONDecodeError, ValidationError)):
            await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

        mock_batch_state_repo.record_essay_step_completion.assert_not_called()

    # Test Category 2: CJ Assessment Event Processing

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_cj_assessment_completion_processing(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test successful processing of CJ assessment completion event."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Act
        await kafka_consumer._handle_cj_assessment_completed(mock_msg)

        # Assert - Should record completion for all 3 essays
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 3

        # Verify first essay completion (state tracking only, no business data)
        first_call = mock_batch_state_repo.record_essay_step_completion.call_args_list[0]
        assert first_call[1]["batch_id"] == "batch-789"
        assert first_call[1]["essay_id"] == "essay-001"
        assert first_call[1]["step_name"] == "cj_assessment"
        assert first_call[1]["metadata"]["completion_status"] == "success"
        assert first_call[1]["metadata"]["cj_job_id"] == "cj_job_789"
        # NO business data (rank, score) - just state tracking

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_cj_assessment_empty_rankings(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test handling of CJ assessment with no successful essays."""
        # Arrange
        sample_cj_assessment_message_data["data"]["processing_summary"]["successful_essay_ids"] = []
        sample_cj_assessment_message_data["data"]["processing_summary"]["successful"] = 0
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Act
        await kafka_consumer._handle_cj_assessment_completed(mock_msg)

        # Assert - No completions should be recorded
        mock_batch_state_repo.record_essay_step_completion.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_cj_assessment_missing_essay_id(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test handling of CJ assessment with None in successful essay IDs."""
        # Arrange
        sample_cj_assessment_message_data["data"]["processing_summary"]["successful_essay_ids"] = [
            None,
            "essay-002",
            "essay-003",
        ]
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Act
        await kafka_consumer._handle_cj_assessment_completed(mock_msg)

        # Assert - Should record completions for the 2 valid essays only
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 2

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_cj_assessment_repository_failure(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test handling of batch state repository failure during CJ assessment processing."""
        # Arrange
        mock_batch_state_repo.record_essay_step_completion.return_value = False
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Act
        await kafka_consumer._handle_cj_assessment_completed(mock_msg)

        # Assert - Should attempt to record all completions despite failures
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 3

    # Test Category 3: Consumer Lifecycle Management

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_consumer_initial_state(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test consumer initial state."""
        # Assert
        assert not await kafka_consumer.is_consuming()
        assert kafka_consumer._consumer is None
        assert not kafka_consumer._consuming

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_consumer_stop_when_not_consuming(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test stop when not consuming (should handle gracefully)."""
        # Act
        await kafka_consumer.stop_consuming()

        # Assert - Should handle gracefully without errors
        assert not await kafka_consumer.is_consuming()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_consumer_start_already_consuming(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test starting consumer when already consuming raises error."""
        # Arrange
        kafka_consumer._consuming = True

        # Act & Assert
        with pytest.raises(RuntimeError, match="Consumer is already running"):
            await kafka_consumer.start_consuming()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_consumer_stop_with_exception(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test stop consuming with exception during shutdown."""
        # Arrange
        mock_consumer = AsyncMock()
        mock_consumer.stop.side_effect = Exception("Shutdown error")
        kafka_consumer._consumer = mock_consumer
        kafka_consumer._consuming = True

        # Act
        await kafka_consumer.stop_consuming()

        # Assert - Should handle exception gracefully
        assert not kafka_consumer._consuming

    # Test Category 4: Message Routing and Event Type Extraction

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_unknown_topic_handling(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test handling of messages from unknown topics."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps({"test": "data"}).encode("utf-8")
        mock_msg.topic = "unknown.topic"

        # Act
        await kafka_consumer._handle_message(mock_msg)

        # Assert - Should handle gracefully without raising

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_event_type_extraction_from_topic(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test event type extraction from various topic formats."""
        # Test cases
        test_cases = [
            (topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED), "spellcheck_phase_completed"),
            (topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED), "cj_assessment_completed"),
            ("huleedu.ai.feedback.completed.v1", "ai_feedback_completed"),
            ("short.topic", "unknown_event"),
            ("single", "unknown_event"),
        ]

        for topic, expected_event_type in test_cases:
            # Act
            result = kafka_consumer._extract_event_type_from_topic(topic)

            # Assert
            assert result == expected_event_type

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_message_routing_spellcheck_topic(
        self, kafka_consumer: BCSKafkaConsumer, sample_spellcheck_message_data: dict
    ) -> None:
        """Test message routing to spellcheck handler based on topic."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Mock the handler to verify it's called
        with patch.object(kafka_consumer, "_handle_spellcheck_phase_completed") as mock_handler:
            # Act
            await kafka_consumer._handle_message(mock_msg)

            # Assert
            mock_handler.assert_called_once_with(mock_msg)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_message_routing_cj_assessment_topic(
        self, kafka_consumer: BCSKafkaConsumer, sample_cj_assessment_message_data: dict
    ) -> None:
        """Test message routing to CJ assessment handler based on topic."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Mock the handler to verify it's called
        with patch.object(kafka_consumer, "_handle_cj_assessment_completed") as mock_handler:
            # Act
            await kafka_consumer._handle_message(mock_msg)

            # Assert
            mock_handler.assert_called_once_with(mock_msg)

    # Test Category 5: Error Handling and Resilience

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_batch_state_repo_failure_during_spellcheck(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test handling of batch state repository failure during spellcheck processing."""
        # Arrange
        mock_batch_state_repo.record_essay_step_completion.side_effect = Exception("Database error")
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Act & Assert
        with pytest.raises(Exception, match="Database error"):
            await kafka_consumer._handle_spellcheck_phase_completed(mock_msg)

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_message_handler_exception_propagation(
        self, kafka_consumer: BCSKafkaConsumer, sample_spellcheck_message_data: dict
    ) -> None:
        """Test that exceptions from message handlers are properly propagated."""
        # Arrange
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)

        # Mock handler to raise exception
        with patch.object(
            kafka_consumer,
            "_handle_spellcheck_phase_completed",
            side_effect=Exception("Handler error"),
        ):
            # Act & Assert
            with pytest.raises(Exception, match="Handler error"):
                await kafka_consumer._handle_message(mock_msg)

    # Test Category 6: Metrics and Observability

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_metrics_tracking_success(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test successful event processing metrics tracking."""
        # Arrange
        event_type = "spellcheck_completed"

        # Mock metrics
        mock_metrics = {"events_processed_total": Mock()}
        mock_counter = Mock()
        mock_metrics["events_processed_total"].labels.return_value = mock_counter
        kafka_consumer._metrics = mock_metrics

        # Act
        await kafka_consumer._track_event_success(event_type)

        # Assert
        mock_metrics["events_processed_total"].labels.assert_called_once_with(
            event_type=event_type, outcome="success"
        )
        mock_counter.inc.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_metrics_tracking_failure(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test failed event processing metrics tracking."""
        # Arrange
        event_type = "spellcheck_completed"
        failure_reason = "processing_error"

        # Mock metrics
        mock_metrics = {"events_processed_total": Mock()}
        mock_counter = Mock()
        mock_metrics["events_processed_total"].labels.return_value = mock_counter
        kafka_consumer._metrics = mock_metrics

        # Act
        await kafka_consumer._track_event_failure(event_type, failure_reason)

        # Assert
        mock_metrics["events_processed_total"].labels.assert_called_once_with(
            event_type=event_type, outcome=failure_reason
        )
        mock_counter.inc.assert_called_once()

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_metrics_tracking_with_no_metrics(self, kafka_consumer: BCSKafkaConsumer) -> None:
        """Test metrics tracking when metrics are not available."""
        # Arrange
        kafka_consumer._metrics = None

        # Act - Should not raise exceptions
        await kafka_consumer._track_event_success("test_event")
        await kafka_consumer._track_event_failure("test_event", "test_failure")

        # Assert - No exceptions should be raised

    # Test Category 7: Integration and Real-world Scenarios

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_concurrent_message_processing(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
    ) -> None:
        """Test concurrent processing of multiple messages."""
        # Arrange
        messages = []
        for i in range(3):
            msg_data = sample_spellcheck_message_data.copy()
            msg_data["data"]["entity_id"] = f"essay-{i}"
            msg_data["event_id"] = str(uuid4())

            mock_msg = Mock()
            mock_msg.value = json.dumps(msg_data).encode("utf-8")
            mock_msg.topic = topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED)
            messages.append(mock_msg)

        # Act
        await asyncio.gather(
            *[kafka_consumer._handle_spellcheck_phase_completed(msg) for msg in messages]
        )

        # Assert
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 3

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_mixed_event_types_processing(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_spellcheck_message_data: dict,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test processing of mixed event types in sequence."""
        # Arrange
        spellcheck_msg = Mock()
        spellcheck_msg.value = json.dumps(sample_spellcheck_message_data).encode("utf-8")
        spellcheck_msg.topic = "huleedu.development.essay.spellcheck"

        cj_msg = Mock()
        cj_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        cj_msg.topic = "huleedu.cj_assessment.completed"

        # Act
        await kafka_consumer._handle_spellcheck_phase_completed(spellcheck_msg)
        await kafka_consumer._handle_cj_assessment_completed(cj_msg)

        # Assert - Should record completions for spellcheck + 3 CJ assessment essays
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 4

    @pytest.mark.asyncio
    @pytest.mark.docker
    async def test_large_cj_assessment_batch(
        self,
        kafka_consumer: BCSKafkaConsumer,
        mock_batch_state_repo: AsyncMock,
        sample_cj_assessment_message_data: dict,
    ) -> None:
        """Test processing of CJ assessment with large number of essays."""
        # Arrange - Create 50 successful essay IDs
        successful_essay_ids = [f"essay-{i:03d}" for i in range(50)]
        sample_cj_assessment_message_data["data"]["processing_summary"] = {
            "total_essays": 50,
            "successful": 50,
            "failed": 0,
            "successful_essay_ids": successful_essay_ids,
            "failed_essay_ids": [],
            "processing_time_seconds": 25.5,
        }
        mock_msg = Mock()
        mock_msg.value = json.dumps(sample_cj_assessment_message_data).encode("utf-8")
        mock_msg.topic = topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED)

        # Act
        await kafka_consumer._handle_cj_assessment_completed(mock_msg)

        # Assert
        assert mock_batch_state_repo.record_essay_step_completion.call_count == 50

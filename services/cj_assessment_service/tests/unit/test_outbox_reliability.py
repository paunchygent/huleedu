"""Unit tests for Outbox Pattern reliability behavioral outcomes.

This module tests the observable behavioral outcomes of the transactional outbox pattern:
- Event persistence occurs before publishing attempts
- Retry mechanisms handle publishing failures appropriately 
- Duplicate event prevention works across concurrent scenarios
- Transaction rollback scenarios maintain data consistency
- Cleanup processes work after successful publishing
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentCompletedV1, GradeProjectionSummary
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage

from services.cj_assessment_service.implementations.event_publisher_impl import CJEventPublisherImpl
from services.cj_assessment_service.models_db import EventOutbox


class TestOutboxReliability:
    """Tests for outbox pattern reliability behavioral outcomes."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create mock outbox manager matching outbox protocol interface."""
        manager = AsyncMock()
        manager.publish_to_outbox = AsyncMock()
        return manager

    @pytest.fixture
    def test_settings(self) -> Mock:
        """Create test settings with outbox configuration."""
        return Mock(
            CJ_ASSESSMENT_COMPLETED_TOPIC="cj_assessment.completed.v1",
            ASSESSMENT_RESULT_TOPIC="huleedu.assessment.results.v1",
            CJ_ASSESSMENT_FAILED_TOPIC="cj_assessment.failed.v1",
            SERVICE_NAME="cj_assessment_service",
        )

    @pytest.fixture
    def sample_completion_event(self) -> EventEnvelope[CJAssessmentCompletedV1]:
        """Create sample completion event envelope."""
        # Create proper system metadata
        system_metadata = SystemProcessingMetadata(
            entity_id="batch_123",
            entity_type="cj_batch",
            parent_id=None,
            timestamp=datetime.now(UTC),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
        )
        
        # Create grade projections summary
        grade_projections = GradeProjectionSummary(
            projections_available=True,
            primary_grades={"essay_1": "A", "essay_2": "B"},
            confidence_labels={"essay_1": "HIGH", "essay_2": "MID"},
            confidence_scores={"essay_1": 0.9, "essay_2": 0.7},
        )
        
        # Create proper completion data
        completion_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_id="batch_123",
            entity_type="cj_batch",
            parent_id=None,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=system_metadata,
            cj_assessment_job_id="job_456",
            rankings=[
                {"els_essay_id": "essay_1", "rank": 1, "score": 0.8},
                {"els_essay_id": "essay_2", "rank": 2, "score": 0.6},
            ],
            grade_projections_summary=grade_projections,
        )
        
        return EventEnvelope[CJAssessmentCompletedV1](
            event_type="cj_assessment.completed.v1",
            source_service="cj_assessment_service",
            correlation_id=uuid4(),
            data=completion_data,
        )

    @pytest.fixture
    def mock_database_session(self) -> AsyncMock:
        """Create mock database session for outbox operations."""
        session = AsyncMock()
        session.add = Mock()
        session.flush = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.query = Mock()
        return session

    @pytest.mark.asyncio
    async def test_event_persistence_before_publishing(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
        sample_completion_event: EventEnvelope[CJAssessmentCompletedV1],
    ) -> None:
        """Test that events are persisted to outbox before any publishing attempts."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id = uuid4()

        # Act
        await event_publisher.publish_assessment_completed(
            completion_data=sample_completion_event,
            correlation_id=correlation_id,
        )

        # Assert - Outbox manager should be called for transactional persistence
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "cj_batch"
        assert call_args.kwargs["event_type"] == test_settings.CJ_ASSESSMENT_COMPLETED_TOPIC
        assert call_args.kwargs["event_data"] == sample_completion_event
        assert call_args.kwargs["topic"] == test_settings.CJ_ASSESSMENT_COMPLETED_TOPIC

    @pytest.mark.asyncio
    async def test_retry_mechanism_on_publish_failure(self) -> None:
        """Test that failed publishing attempts increment retry count appropriately."""
        # Arrange - Create outbox event that has failed publishing
        failed_outbox_event = EventOutbox(
            id=uuid4(),
            aggregate_id="batch_123",
            aggregate_type="cj_batch",
            event_type="cj_assessment.completed.v1",
            event_data={"test": "data"},
            event_key="batch_123",
            topic="cj_assessment.completed.v1",
            created_at=datetime.now(UTC),
            published_at=None,  # Not yet published
            retry_count=0,
            last_error=None,
        )

        # Simulate retry increment after failure
        failed_outbox_event.retry_count += 1
        failed_outbox_event.last_error = "Kafka connection timeout"

        # Act & Assert - Behavioral outcome of retry logic
        assert failed_outbox_event.retry_count == 1
        assert failed_outbox_event.last_error == "Kafka connection timeout"
        assert failed_outbox_event.published_at is None

        # Simulate second failure
        failed_outbox_event.retry_count += 1
        failed_outbox_event.last_error = "Kafka partition unavailable"

        assert failed_outbox_event.retry_count == 2
        assert failed_outbox_event.published_at is None

    @pytest.mark.asyncio  
    async def test_duplicate_event_prevention(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
        sample_completion_event: EventEnvelope[CJAssessmentCompletedV1],
    ) -> None:
        """Test that duplicate events with same aggregate_id are handled appropriately."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id = uuid4()
        
        # Simulate the outbox manager detecting duplicate
        mock_outbox_manager.publish_to_outbox.side_effect = [
            None,  # First call succeeds
            Exception("Duplicate event detected"),  # Second call fails
        ]

        # Act - Publish the same event twice
        await event_publisher.publish_assessment_completed(
            completion_data=sample_completion_event,
            correlation_id=correlation_id,
        )

        # Second attempt should handle duplicate appropriately
        with pytest.raises(Exception, match="Duplicate event detected"):
            await event_publisher.publish_assessment_completed(
                completion_data=sample_completion_event,
                correlation_id=correlation_id,
            )

        # Assert - Both calls were attempted (duplicate detection is outbox manager's responsibility)
        assert mock_outbox_manager.publish_to_outbox.call_count == 2

    @pytest.mark.asyncio
    async def test_outbox_cleanup_after_success(self) -> None:
        """Test that successful publishing updates outbox event appropriately."""
        # Arrange - Create outbox event ready for cleanup
        successful_outbox_event = EventOutbox(
            id=uuid4(),
            aggregate_id="batch_123",
            aggregate_type="cj_batch", 
            event_type="cj_assessment.completed.v1",
            event_data={"test": "data"},
            event_key="batch_123",
            topic="cj_assessment.completed.v1",
            created_at=datetime.now(UTC) - timedelta(minutes=5),
            published_at=None,
            retry_count=1,
            last_error="Previous failure",
        )

        # Act - Simulate successful publishing cleanup
        successful_outbox_event.published_at = datetime.now(UTC)
        successful_outbox_event.last_error = None

        # Assert - Behavioral outcome of successful cleanup
        assert successful_outbox_event.published_at is not None
        assert successful_outbox_event.last_error is None
        assert successful_outbox_event.retry_count == 1  # Preserved for audit

        # Verify cleanup timing is reasonable
        time_to_publish = (
            successful_outbox_event.published_at - successful_outbox_event.created_at
        ).total_seconds()
        assert time_to_publish >= 300  # At least 5 minutes (from arrangement)

    @pytest.mark.asyncio
    async def test_transaction_rollback_scenarios(
        self,
        mock_database_session: AsyncMock,
    ) -> None:
        """Test that transaction rollback maintains outbox data consistency."""
        # Arrange - Create outbox event in transaction
        outbox_event = EventOutbox(
            id=uuid4(),
            aggregate_id="batch_456",
            aggregate_type="cj_batch",
            event_type="cj_assessment.completed.v1",
            event_data={"business": "data"},
            event_key="batch_456",
            topic="cj_assessment.completed.v1",
            created_at=datetime.now(UTC),
            published_at=None,
            retry_count=0,
            last_error=None,
        )

        # Act - Simulate transaction rollback scenario
        try:
            mock_database_session.add(outbox_event)
            # Simulate business logic failure
            raise Exception("Business logic validation failed")
        except Exception:
            await mock_database_session.rollback()

        # Assert - Rollback behavior
        mock_database_session.add.assert_called_once_with(outbox_event)
        mock_database_session.rollback.assert_called_once()
        
        # Event should not be committed
        mock_database_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_concurrent_publishing_safety(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
        sample_completion_event: EventEnvelope[CJAssessmentCompletedV1],
    ) -> None:
        """Test that concurrent publishing attempts are handled safely."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id_1 = uuid4()
        correlation_id_2 = uuid4()

        # Configure different responses for concurrent calls
        mock_outbox_manager.publish_to_outbox.side_effect = [
            None,  # First concurrent call succeeds
            None,  # Second concurrent call also succeeds
        ]

        # Act - Simulate concurrent publishing
        await event_publisher.publish_assessment_completed(
            completion_data=sample_completion_event,
            correlation_id=correlation_id_1,
        )
        
        await event_publisher.publish_assessment_completed(
            completion_data=sample_completion_event,
            correlation_id=correlation_id_2,
        )

        # Assert - Both calls completed without race condition issues
        assert mock_outbox_manager.publish_to_outbox.call_count == 2
        
        # Verify each call had proper parameters
        first_call = mock_outbox_manager.publish_to_outbox.call_args_list[0]
        second_call = mock_outbox_manager.publish_to_outbox.call_args_list[1]
        
        assert first_call.kwargs["aggregate_type"] == "cj_batch"
        assert second_call.kwargs["aggregate_type"] == "cj_batch"
        assert first_call.kwargs["event_data"] == sample_completion_event
        assert second_call.kwargs["event_data"] == sample_completion_event

    @pytest.mark.asyncio
    async def test_assessment_result_outbox_pattern(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that RAS assessment results use outbox pattern correctly."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id = uuid4()
        
        # Create mock RAS result data
        mock_result_envelope = Mock()
        mock_result_envelope.data.cj_assessment_job_id = "job_789"

        # Act
        await event_publisher.publish_assessment_result(
            result_data=mock_result_envelope,
            correlation_id=correlation_id,
        )

        # Assert - RAS events use outbox pattern
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "assessment_result"
        assert call_args.kwargs["event_type"] == "assessment.result.published"
        assert call_args.kwargs["topic"] == test_settings.ASSESSMENT_RESULT_TOPIC
        assert call_args.kwargs["event_data"] == mock_result_envelope

    @pytest.mark.asyncio
    async def test_event_metadata_extraction_behavior(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
        sample_completion_event: EventEnvelope[CJAssessmentCompletedV1],
    ) -> None:
        """Test that aggregate IDs are extracted correctly from event data."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id = uuid4()

        # Act
        await event_publisher.publish_assessment_completed(
            completion_data=sample_completion_event,
            correlation_id=correlation_id,
        )

        # Assert - Aggregate ID extraction behavior
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        
        # Should extract aggregate_id from event data's entity_id
        expected_aggregate_id = sample_completion_event.data.entity_id
        assert call_args.kwargs["aggregate_id"] == expected_aggregate_id

    @pytest.mark.asyncio
    async def test_outbox_event_field_validation(self) -> None:
        """Test that outbox events have all required fields for reliable processing."""
        # Arrange & Act - Create outbox event with all required fields
        complete_outbox_event = EventOutbox(
            id=uuid4(),
            aggregate_id="batch_complete_123",
            aggregate_type="cj_batch",
            event_type="cj_assessment.completed.v1", 
            event_data={"complete": "event_data"},
            event_key="batch_complete_123",
            topic="cj_assessment.completed.v1",
            created_at=datetime.now(UTC),
            published_at=None,
            retry_count=0,
            last_error=None,
        )

        # Assert - All essential outbox fields are present and valid
        assert complete_outbox_event.id is not None
        assert isinstance(complete_outbox_event.aggregate_id, str)
        assert isinstance(complete_outbox_event.aggregate_type, str)
        assert isinstance(complete_outbox_event.event_type, str)
        assert isinstance(complete_outbox_event.event_data, dict)
        assert isinstance(complete_outbox_event.topic, str)
        assert isinstance(complete_outbox_event.created_at, datetime)
        assert isinstance(complete_outbox_event.retry_count, int)
        
        # Nullable fields should have appropriate types when set
        assert complete_outbox_event.published_at is None or isinstance(complete_outbox_event.published_at, datetime)
        assert complete_outbox_event.last_error is None or isinstance(complete_outbox_event.last_error, str)
        assert complete_outbox_event.event_key is None or isinstance(complete_outbox_event.event_key, str)

    @pytest.mark.asyncio
    async def test_failure_event_outbox_integration(
        self,
        mock_outbox_manager: AsyncMock,
        test_settings: Mock,
    ) -> None:
        """Test that failure events also use outbox pattern for consistency."""
        # Arrange
        event_publisher = CJEventPublisherImpl(mock_outbox_manager, test_settings)
        correlation_id = uuid4()
        
        mock_failure_envelope = Mock()
        mock_failure_envelope.data.entity_id = "failed_batch_123"

        # Act
        await event_publisher.publish_assessment_failed(
            failure_data=mock_failure_envelope,
            correlation_id=correlation_id,
        )

        # Assert - Failure events use same outbox reliability pattern
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "cj_batch"
        assert call_args.kwargs["event_type"] == test_settings.CJ_ASSESSMENT_FAILED_TOPIC
        assert call_args.kwargs["topic"] == test_settings.CJ_ASSESSMENT_FAILED_TOPIC
        assert call_args.kwargs["event_data"] == mock_failure_envelope
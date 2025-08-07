"""Unit tests for ResultNotificationProjector."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.events.result_events import (
    BatchAssessmentCompletedV1,
    BatchResultsReadyV1,
    PhaseResultSummary,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.notification_projector import ResultNotificationProjector


class TestResultNotificationProjector:
    """Tests for the ResultNotificationProjector class."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Provide mock outbox manager."""
        return AsyncMock()

    @pytest.fixture
    def settings(self) -> Settings:
        """Provide test settings."""
        return Settings()

    @pytest.fixture
    def projector(self, mock_outbox_manager: AsyncMock, settings: Settings) -> ResultNotificationProjector:
        """Provide notification projector instance."""
        return ResultNotificationProjector(
            outbox_manager=mock_outbox_manager,
            settings=settings,
        )

    @pytest.fixture
    def sample_batch_results_ready_event(self) -> BatchResultsReadyV1:
        """Provide sample BatchResultsReadyV1 event."""
        return BatchResultsReadyV1(
            batch_id="batch-123",
            user_id="teacher-456",
            correlation_id=uuid4(),
            total_essays=10,
            completed_essays=10,
            phase_results={
                "spellcheck": PhaseResultSummary(
                    phase_name="spellcheck",
                    status="completed",
                    completed_count=10,
                    failed_count=0,
                    processing_time_seconds=5.2,
                ),
                "cj_assessment": PhaseResultSummary(
                    phase_name="cj_assessment",
                    status="completed",
                    completed_count=10,
                    failed_count=0,
                    processing_time_seconds=120.5,
                ),
            },
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=125.7,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(
                entity_id="batch-123",
                entity_type="batch",
                service_name="result_aggregator_service"
            ),
            event_timestamp=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def sample_batch_assessment_completed_event(self) -> BatchAssessmentCompletedV1:
        """Provide sample BatchAssessmentCompletedV1 event."""
        return BatchAssessmentCompletedV1(
            batch_id="batch-789",
            user_id="teacher-101",
            assessment_job_id="job-202",
            rankings_summary=[
                {"essay_id": "essay1", "rank": 1, "score": 0.95},
                {"essay_id": "essay2", "rank": 2, "score": 0.87},
                {"essay_id": "essay3", "rank": 3, "score": 0.76},
            ],
            correlation_id=uuid4(),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(
                entity_id="batch-123",
                entity_type="batch",
                service_name="result_aggregator_service"
            ),
            event_timestamp=datetime.now(timezone.utc),
        )

    async def test_handle_batch_results_ready_creates_correct_notification(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
        sample_batch_results_ready_event: BatchResultsReadyV1,
    ) -> None:
        """Test that batch results ready event creates correct high-priority notification."""
        # Arrange
        correlation_id = uuid4()

        # Act
        await projector.handle_batch_results_ready(sample_batch_results_ready_event, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify outbox parameters
        assert call_args[1]["aggregate_type"] == "teacher_notification"
        assert call_args[1]["aggregate_id"] == "teacher-456"
        assert call_args[1]["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        assert call_args[1]["topic"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)

        # Verify envelope structure
        envelope = call_args[1]["event_data"]
        assert envelope.event_type == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        assert envelope.source_service == "result_aggregator_service"

        # Verify notification content
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-456"
        assert notification.notification_type == "batch_results_ready"
        assert notification.category == WebSocketEventCategory.PROCESSING_RESULTS
        assert notification.priority == NotificationPriority.HIGH
        assert notification.batch_id == "batch-123"
        assert not notification.action_required
        assert notification.correlation_id == str(correlation_id)

        # Verify payload content
        payload = notification.payload
        assert payload["batch_id"] == "batch-123"
        assert payload["total_essays"] == 10
        assert payload["completed_essays"] == 10
        assert payload["overall_status"] == BatchStatus.COMPLETED_SUCCESSFULLY.value
        assert payload["processing_duration_seconds"] == 125.7
        assert "Batch batch-123 processing completed with 10/10 essays" in payload["message"]

        # Verify phase results
        assert "phase_results" in payload
        assert "spellcheck" in payload["phase_results"]
        assert "cj_assessment" in payload["phase_results"]
        assert payload["phase_results"]["spellcheck"]["status"] == "completed"
        assert payload["phase_results"]["spellcheck"]["completed_count"] == 10
        assert payload["phase_results"]["spellcheck"]["failed_count"] == 0
        assert payload["phase_results"]["spellcheck"]["processing_time_seconds"] == 5.2

    async def test_handle_batch_assessment_completed_creates_correct_notification(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
        sample_batch_assessment_completed_event: BatchAssessmentCompletedV1,
    ) -> None:
        """Test that batch assessment completed event creates correct standard-priority notification."""
        # Arrange
        correlation_id = uuid4()

        # Act
        await projector.handle_batch_assessment_completed(sample_batch_assessment_completed_event, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify outbox parameters
        assert call_args[1]["aggregate_type"] == "teacher_notification"
        assert call_args[1]["aggregate_id"] == "teacher-101"
        assert call_args[1]["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        assert call_args[1]["topic"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)

        # Verify envelope structure
        envelope = call_args[1]["event_data"]
        assert envelope.event_type == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
        assert envelope.source_service == "result_aggregator_service"

        # Verify notification content
        notification = envelope.data
        assert isinstance(notification, TeacherNotificationRequestedV1)
        assert notification.teacher_id == "teacher-101"
        assert notification.notification_type == "batch_assessment_completed"
        assert notification.category == WebSocketEventCategory.PROCESSING_RESULTS
        assert notification.priority == NotificationPriority.STANDARD
        assert notification.batch_id == "batch-789"
        assert not notification.action_required
        assert notification.correlation_id == str(correlation_id)

        # Verify payload content
        payload = notification.payload
        assert payload["batch_id"] == "batch-789"
        assert payload["assessment_job_id"] == "job-202"
        assert payload["rankings_available"] is True
        assert payload["rankings_count"] == 3
        assert "Comparative judgment assessment completed for batch batch-789" in payload["message"]

    async def test_handle_batch_assessment_completed_with_no_rankings(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that batch assessment completed with no rankings creates correct notification."""
        # Arrange
        event = BatchAssessmentCompletedV1(
            batch_id="batch-empty",
            user_id="teacher-999",
            assessment_job_id="job-empty",
            rankings_summary=[],  # No rankings
            correlation_id=uuid4(),
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(
                entity_id="batch-123",
                entity_type="batch",
                service_name="result_aggregator_service"
            ),
            event_timestamp=datetime.now(timezone.utc),
        )

        # Act
        await projector.handle_batch_assessment_completed(event, uuid4())

        # Assert
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]
        notification = envelope.data
        payload = notification.payload

        assert payload["rankings_available"] is False
        assert payload["rankings_count"] == 0

    async def test_outbox_manager_error_handling(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
        sample_batch_results_ready_event: BatchResultsReadyV1,
    ) -> None:
        """Test that outbox manager errors are properly handled and re-raised."""
        # Arrange
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Outbox failed")

        # Act & Assert
        with pytest.raises(Exception, match="Outbox failed"):
            await projector.handle_batch_results_ready(sample_batch_results_ready_event, uuid4())

    @pytest.mark.parametrize(
        "priority_level,expected_priority",
        [
            ("batch_results_ready", NotificationPriority.HIGH),
            ("batch_assessment_completed", NotificationPriority.STANDARD),
        ],
    )
    async def test_notification_priority_assignment(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
        sample_batch_results_ready_event: BatchResultsReadyV1,
        sample_batch_assessment_completed_event: BatchAssessmentCompletedV1,
        priority_level: str,
        expected_priority: NotificationPriority,
    ) -> None:
        """Test that correct priority levels are assigned to different notification types."""
        # Act
        if priority_level == "batch_results_ready":
            await projector.handle_batch_results_ready(sample_batch_results_ready_event, uuid4())
        else:
            await projector.handle_batch_assessment_completed(sample_batch_assessment_completed_event, uuid4())

        # Assert
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]
        notification = envelope.data
        assert notification.priority == expected_priority

    async def test_correlation_id_propagation(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test that correlation IDs are properly propagated from domain events to notifications."""
        # Arrange
        correlation_id = uuid4()
        event = BatchResultsReadyV1(
            batch_id="batch-corr",
            user_id="teacher-corr",
            correlation_id=correlation_id,
            total_essays=5,
            completed_essays=5,
            phase_results={},
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=60.0,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(
                entity_id="batch-123",
                entity_type="batch",
                service_name="result_aggregator_service"
            ),
            event_timestamp=datetime.now(timezone.utc),
        )

        # Act
        await projector.handle_batch_results_ready(event, correlation_id)

        # Assert
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]
        notification = envelope.data
        assert notification.correlation_id == str(correlation_id)

    async def test_teacher_friendly_messages(
        self,
        projector: ResultNotificationProjector,
        mock_outbox_manager: AsyncMock,
        sample_batch_results_ready_event: BatchResultsReadyV1,
        sample_batch_assessment_completed_event: BatchAssessmentCompletedV1,
    ) -> None:
        """Test that notification messages are teacher-friendly and non-technical."""
        # Test batch results ready message
        await projector.handle_batch_results_ready(sample_batch_results_ready_event, uuid4())
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]
        notification = envelope.data
        message = notification.payload["message"]

        assert "processing completed" in message.lower()
        assert "batch-123" in message
        assert "10/10 essays" in message
        # Should not contain technical jargon
        assert "correlation_id" not in message.lower()
        assert "aggregate" not in message.lower()

        # Reset mock for next test
        mock_outbox_manager.reset_mock()

        # Test batch assessment completed message
        await projector.handle_batch_assessment_completed(sample_batch_assessment_completed_event, uuid4())
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]
        notification = envelope.data
        message = notification.payload["message"]

        assert "comparative judgment assessment completed" in message.lower()
        assert "batch-789" in message
        # Should not contain technical jargon
        assert "job_id" not in message.lower()
        assert "rankings_summary" not in message.lower()

"""Behavioral unit tests for ELS notification projector.

Tests behavioral outcomes rather than implementation details following Rule 075.
"""

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from services.essay_lifecycle_service.notification_projector import ELSNotificationProjector


class TestELSNotificationProjector:
    """Behavioral tests for ELS notification projector."""

    @pytest.fixture
    def mock_kafka_publisher(self) -> AsyncMock:
        """Mock Kafka publisher."""
        return AsyncMock()

    @pytest.fixture
    def notification_projector(self, mock_kafka_publisher: AsyncMock) -> ELSNotificationProjector:
        """Create notification projector with mock dependencies."""
        return ELSNotificationProjector(mock_kafka_publisher)

    @pytest.fixture
    def sample_spellcheck_outcome(self) -> ELSBatchPhaseOutcomeV1:
        """Sample spellcheck phase outcome event."""
        return ELSBatchPhaseOutcomeV1(
            batch_id="batch-123",
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
                EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-2"),
            ],
            failed_essay_ids=[],
            correlation_id=uuid4(),
        )

    @pytest.fixture
    def sample_cj_assessment_outcome(self) -> ELSBatchPhaseOutcomeV1:
        """Sample CJ assessment phase outcome event."""
        return ELSBatchPhaseOutcomeV1(
            batch_id="batch-456",
            phase_name=PhaseName.CJ_ASSESSMENT,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            ],
            failed_essay_ids=["essay-2"],
            correlation_id=uuid4(),
        )

    async def test_spellcheck_completion_notification_published(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock, sample_spellcheck_outcome: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Test that spellcheck completion results in LOW priority notification being published."""
        teacher_id = "teacher-123"

        await notification_projector.handle_phase_outcome(sample_spellcheck_outcome, teacher_id)

        # Verify notification was published
        mock_kafka_publisher.publish.assert_called_once()
        call_args = mock_kafka_publisher.publish.call_args

        # Extract envelope from call arguments
        envelope = call_args.kwargs["envelope"]
        notification = envelope.data

        # Behavioral verification: correct notification type and priority
        assert notification.teacher_id == teacher_id
        assert notification.notification_type == "batch_spellcheck_completed"
        assert notification.priority == "low"
        assert notification.category == "batch_progress"
        assert notification.batch_id == sample_spellcheck_outcome.batch_id
        assert notification.action_required is False

        # Verify payload contains expected data
        payload = notification.payload
        assert payload["phase_name"] == "spellcheck"
        assert payload["success_count"] == 2
        assert payload["failed_count"] == 0
        assert payload["total_count"] == 2
        assert "All 2 essays completed successfully" in payload["message"]

    async def test_cj_assessment_completion_notification_published(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock, sample_cj_assessment_outcome: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Test that CJ assessment completion results in STANDARD priority notification being published."""
        teacher_id = "teacher-456"

        await notification_projector.handle_phase_outcome(sample_cj_assessment_outcome, teacher_id)

        # Verify notification was published
        mock_kafka_publisher.publish.assert_called_once()
        call_args = mock_kafka_publisher.publish.call_args

        # Extract envelope from call arguments
        envelope = call_args.kwargs["envelope"]
        notification = envelope.data

        # Behavioral verification: correct notification type and priority
        assert notification.teacher_id == teacher_id
        assert notification.notification_type == "batch_cj_assessment_completed"
        assert notification.priority == "standard"
        assert notification.category == "batch_progress"
        assert notification.batch_id == sample_cj_assessment_outcome.batch_id
        assert notification.action_required is False

        # Verify payload reflects partial success
        payload = notification.payload
        assert payload["phase_name"] == "cj_assessment"
        assert payload["success_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["total_count"] == 2
        assert "1 of 2 essays completed successfully" in payload["message"]

    async def test_unknown_phase_name_skips_notification(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock
    ) -> None:
        """Test that unknown phase names are handled gracefully without publishing."""
        # Create event with unsupported phase name
        unknown_phase_outcome = ELSBatchPhaseOutcomeV1(
            batch_id="batch-789",
            phase_name=PhaseName.NLP,  # Not supported in mapping
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-1"),
            ],
            failed_essay_ids=[],
            correlation_id=uuid4(),
        )

        await notification_projector.handle_phase_outcome(unknown_phase_outcome, "teacher-789")

        # Behavioral verification: no notification published
        mock_kafka_publisher.publish.assert_not_called()

    async def test_kafka_publish_failure_raises_exception(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock, sample_spellcheck_outcome: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Test that Kafka publishing failures are properly handled."""
        # Configure mock to raise exception
        mock_kafka_publisher.publish.side_effect = Exception("Kafka connection failed")

        teacher_id = "teacher-error"

        # Behavioral verification: exception is propagated
        with pytest.raises(Exception, match="Kafka connection failed"):
            await notification_projector.handle_phase_outcome(sample_spellcheck_outcome, teacher_id)

    async def test_teacher_id_included_in_notification(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock, sample_spellcheck_outcome: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Test that provided teacher_id is correctly included in notification."""
        teacher_id = "specific-teacher-999"

        await notification_projector.handle_phase_outcome(sample_spellcheck_outcome, teacher_id)

        # Verify teacher_id is used as intended
        call_args = mock_kafka_publisher.publish.call_args
        envelope = call_args.kwargs["envelope"]
        notification = envelope.data

        # Behavioral verification: teacher_id propagated correctly
        assert notification.teacher_id == teacher_id
        # Also verify it's used as message key
        assert call_args.kwargs["key"] == teacher_id

    async def test_correlation_id_preserved_in_notification(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock, sample_spellcheck_outcome: ELSBatchPhaseOutcomeV1
    ) -> None:
        """Test that correlation_id from original event is preserved in notification."""
        teacher_id = "teacher-correlation"
        original_correlation_id = sample_spellcheck_outcome.correlation_id

        await notification_projector.handle_phase_outcome(sample_spellcheck_outcome, teacher_id)

        call_args = mock_kafka_publisher.publish.call_args
        envelope = call_args.kwargs["envelope"]
        notification = envelope.data

        # Behavioral verification: correlation ID preserved
        assert notification.correlation_id == str(original_correlation_id)

    async def test_failed_processing_generates_appropriate_message(
        self, notification_projector: ELSNotificationProjector, mock_kafka_publisher: AsyncMock
    ) -> None:
        """Test that completely failed processing generates appropriate message."""
        failed_outcome = ELSBatchPhaseOutcomeV1(
            batch_id="batch-failed",
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.FAILED_CRITICALLY,
            processed_essays=[],
            failed_essay_ids=["essay-1", "essay-2"],
            correlation_id=uuid4(),
        )

        await notification_projector.handle_phase_outcome(failed_outcome, "teacher-fail")

        call_args = mock_kafka_publisher.publish.call_args
        envelope = call_args.kwargs["envelope"]
        notification = envelope.data

        # Behavioral verification: failure message reflects reality
        payload = notification.payload
        assert payload["success_count"] == 0
        assert payload["failed_count"] == 2
        assert payload["total_count"] == 2
        assert "Processing failed for 2 essays" in payload["message"]
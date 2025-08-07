"""Unit tests for Result Aggregator Service Event Publisher.

Tests the ResultEventPublisher implementation following the TRUE OUTBOX PATTERN
and CANONICAL NOTIFICATION PATTERN.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, create_autospec
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.result_events import (
    BatchAssessmentCompletedV1,
    BatchResultsReadyV1,
    PhaseResultSummary,
)
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.event_publisher_impl import (
    ResultEventPublisher,
)
from services.result_aggregator_service.notification_projector import (
    ResultNotificationProjector,
)
from services.result_aggregator_service.protocols import OutboxManagerProtocol


class TestResultEventPublisher:
    """Tests for ResultEventPublisher implementation."""

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Create mock outbox manager."""
        mock = create_autospec(OutboxManagerProtocol, spec_set=True)
        mock.publish_to_outbox = AsyncMock()
        mock.notify_relay_worker = AsyncMock()
        return mock

    @pytest.fixture
    def mock_notification_projector(self) -> AsyncMock:
        """Create mock notification projector."""
        mock = create_autospec(ResultNotificationProjector, spec_set=True)
        mock.handle_batch_results_ready = AsyncMock()
        mock.handle_batch_assessment_completed = AsyncMock()
        return mock

    @pytest.fixture
    def settings(self) -> Settings:
        """Create test settings."""
        settings = Settings()
        settings.SERVICE_NAME = "result_aggregator_service"
        return settings

    @pytest.fixture
    def event_publisher(
        self,
        mock_outbox_manager: AsyncMock,
        settings: Settings,
        mock_notification_projector: AsyncMock,
    ) -> ResultEventPublisher:
        """Create event publisher with mocked dependencies."""
        return ResultEventPublisher(
            outbox_manager=mock_outbox_manager,
            settings=settings,
            notification_projector=mock_notification_projector,
        )

    @pytest.fixture
    def event_publisher_without_projector(
        self,
        mock_outbox_manager: AsyncMock,
        settings: Settings,
    ) -> ResultEventPublisher:
        """Create event publisher without notification projector."""
        return ResultEventPublisher(
            outbox_manager=mock_outbox_manager,
            settings=settings,
            notification_projector=None,
        )

    def _create_system_metadata(
        self, entity_id: str, stage: ProcessingStage = ProcessingStage.COMPLETED
    ) -> SystemProcessingMetadata:
        """Helper to create system metadata."""
        return SystemProcessingMetadata(
            entity_id=entity_id,
            entity_type="batch",
            processing_stage=stage,
        )

    @pytest.mark.asyncio
    async def test_publish_batch_results_ready_with_notification(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
        mock_notification_projector: AsyncMock,
    ):
        """Test publishing BatchResultsReadyV1 event with notification projection."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-123"),
            batch_id="batch-123",
            user_id="teacher-456",
            total_essays=10,
            completed_essays=9,
            phase_results={
                "spellcheck": PhaseResultSummary(
                    phase_name="spellcheck",
                    status="completed",
                    completed_count=9,
                    failed_count=1,
                    processing_time_seconds=45.2,
                ),
                "cj_assessment": PhaseResultSummary(
                    phase_name="cj_assessment",
                    status="completed",
                    completed_count=9,
                    failed_count=0,
                    processing_time_seconds=120.5,
                ),
            },
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=165.7,
        )

        # Act
        await event_publisher.publish_batch_results_ready(event_data, correlation_id)

        # Assert - Verify TRUE OUTBOX PATTERN
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args[1]["aggregate_type"] == "batch"
        assert call_args[1]["aggregate_id"] == "batch-123"
        assert call_args[1]["event_type"] == topic_name(ProcessingEvent.BATCH_RESULTS_READY)
        assert call_args[1]["topic"] == topic_name(ProcessingEvent.BATCH_RESULTS_READY)

        # Verify envelope structure
        envelope = call_args[1]["event_data"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.BATCH_RESULTS_READY)
        assert envelope.source_service == "result_aggregator_service"
        assert envelope.correlation_id == correlation_id
        assert envelope.data == event_data

        # Assert - Verify CANONICAL NOTIFICATION PATTERN
        mock_notification_projector.handle_batch_results_ready.assert_called_once_with(event_data)

    @pytest.mark.asyncio
    async def test_publish_batch_results_ready_without_notification(
        self,
        event_publisher_without_projector: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
    ):
        """Test publishing BatchResultsReadyV1 event without notification projector."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-789"),
            batch_id="batch-789",
            user_id="teacher-999",
            total_essays=5,
            completed_essays=5,
            phase_results={},
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=60.0,
        )

        # Act
        await event_publisher_without_projector.publish_batch_results_ready(
            event_data, correlation_id
        )

        # Assert - Verify outbox called but no notification
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        # No notification projector to call

    @pytest.mark.asyncio
    async def test_publish_batch_assessment_completed_with_notification(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
        mock_notification_projector: AsyncMock,
    ):
        """Test publishing BatchAssessmentCompletedV1 event with notification projection."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchAssessmentCompletedV1(
            event_name=ProcessingEvent.BATCH_ASSESSMENT_COMPLETED,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-456"),
            batch_id="batch-456",
            user_id="teacher-789",
            assessment_job_id="cj-job-001",
            rankings_summary=[
                {"essay_id": "essay-1", "rank": 1, "score": 0.95},
                {"essay_id": "essay-2", "rank": 2, "score": 0.87},
                {"essay_id": "essay-3", "rank": 3, "score": 0.72},
            ],
        )

        # Act
        await event_publisher.publish_batch_assessment_completed(event_data, correlation_id)

        # Assert - Verify TRUE OUTBOX PATTERN
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args[1]["aggregate_type"] == "batch"
        assert call_args[1]["aggregate_id"] == "batch-456"
        assert call_args[1]["event_type"] == topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
        assert call_args[1]["topic"] == topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)

        # Verify envelope structure
        envelope = call_args[1]["event_data"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
        assert envelope.source_service == "result_aggregator_service"
        assert envelope.correlation_id == correlation_id
        assert envelope.data == event_data

        # Assert - Verify CANONICAL NOTIFICATION PATTERN
        mock_notification_projector.handle_batch_assessment_completed.assert_called_once_with(
            event_data
        )

    @pytest.mark.asyncio
    async def test_publish_batch_assessment_completed_without_notification(
        self,
        event_publisher_without_projector: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
    ):
        """Test publishing BatchAssessmentCompletedV1 event without notification projector."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchAssessmentCompletedV1(
            event_name=ProcessingEvent.BATCH_ASSESSMENT_COMPLETED,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-111"),
            batch_id="batch-111",
            user_id="teacher-222",
            assessment_job_id="cj-job-002",
            rankings_summary=[],
        )

        # Act
        await event_publisher_without_projector.publish_batch_assessment_completed(
            event_data, correlation_id
        )

        # Assert - Verify outbox called but no notification
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        # No notification projector to call

    @pytest.mark.parametrize(
        "batch_id,user_id,total_essays,completed_essays",
        [
            # Standard cases
            ("batch-001", "teacher-001", 10, 10),
            ("batch-002", "teacher-002", 5, 4),
            # Edge cases
            ("batch-003", "teacher-003", 0, 0),  # Empty batch
            ("batch-004", "teacher-004", 100, 99),  # Large batch
            ("batch-äöå", "teacher-åäö", 3, 3),  # Swedish characters
        ],
    )
    @pytest.mark.asyncio
    async def test_publish_batch_results_ready_various_data(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
        mock_notification_projector: AsyncMock,
        batch_id: str,
        user_id: str,
        total_essays: int,
        completed_essays: int,
    ):
        """Test publishing with various batch data scenarios."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata(batch_id),
            batch_id=batch_id,
            user_id=user_id,
            total_essays=total_essays,
            completed_essays=completed_essays,
            phase_results={},
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=30.0,
        )

        # Act
        await event_publisher.publish_batch_results_ready(event_data, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args[1]["aggregate_id"] == batch_id
        mock_notification_projector.handle_batch_results_ready.assert_called_once_with(event_data)

    @pytest.mark.asyncio
    async def test_trace_context_injection(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
    ):
        """Test that trace context is injected into event metadata."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-trace"),
            batch_id="batch-trace",
            user_id="teacher-trace",
            total_essays=1,
            completed_essays=1,
            phase_results={},
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=1.0,
        )

        # Act
        await event_publisher.publish_batch_results_ready(event_data, correlation_id)

        # Assert
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        envelope = call_args[1]["event_data"]

        # Metadata should exist for trace context
        assert envelope.metadata is not None
        assert isinstance(envelope.metadata, dict)

    @pytest.mark.asyncio
    async def test_outbox_manager_failure_propagates(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
    ):
        """Test that outbox manager failures propagate correctly."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.FAILED_CRITICALLY,
            system_metadata=self._create_system_metadata("batch-fail", ProcessingStage.FAILED),
            batch_id="batch-fail",
            user_id="teacher-fail",
            total_essays=1,
            completed_essays=0,
            phase_results={},
            overall_status=BatchStatus.FAILED_CRITICALLY,
            processing_duration_seconds=0.1,
        )

        # Configure outbox to fail
        mock_outbox_manager.publish_to_outbox.side_effect = Exception("Outbox failure")

        # Act & Assert
        with pytest.raises(Exception, match="Outbox failure"):
            await event_publisher.publish_batch_results_ready(event_data, correlation_id)

    @pytest.mark.asyncio
    async def test_notification_projector_failure_does_not_affect_outbox(
        self,
        event_publisher: ResultEventPublisher,
        mock_outbox_manager: AsyncMock,
        mock_notification_projector: AsyncMock,
    ):
        """Test that notification projector failures don't affect outbox pattern."""
        # Arrange
        correlation_id = uuid4()
        event_data = BatchResultsReadyV1(
            event_name=ProcessingEvent.BATCH_RESULTS_READY,
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=self._create_system_metadata("batch-notif-fail"),
            batch_id="batch-notif-fail",
            user_id="teacher-notif-fail",
            total_essays=5,
            completed_essays=5,
            phase_results={},
            overall_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processing_duration_seconds=10.0,
        )

        # Configure notification projector to fail
        mock_notification_projector.handle_batch_results_ready.side_effect = Exception(
            "Notification failure"
        )

        # Act & Assert - notification failure should propagate
        with pytest.raises(Exception, match="Notification failure"):
            await event_publisher.publish_batch_results_ready(event_data, correlation_id)

        # But outbox should have been called successfully first
        mock_outbox_manager.publish_to_outbox.assert_called_once()

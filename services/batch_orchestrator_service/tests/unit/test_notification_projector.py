"""Unit tests for Batch Orchestrator Service notification projector."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchPipelineCompletedV1
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.pipeline_models import PhaseName
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

from services.batch_orchestrator_service.notification_projector import NotificationProjector
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)


@pytest.fixture
def mock_batch_repo() -> Mock:
    """Create mock batch repository."""
    return Mock(spec=BatchRepositoryProtocol)


@pytest.fixture
def mock_event_publisher() -> Mock:
    """Create mock event publisher."""
    mock = Mock(spec=BatchEventPublisherProtocol)
    mock.publish_batch_event = AsyncMock()
    return mock


@pytest.fixture
def notification_projector(
    mock_batch_repo: Mock, mock_event_publisher: Mock
) -> NotificationProjector:
    """Create notification projector with mock dependencies."""
    return NotificationProjector(mock_batch_repo, mock_event_publisher)


@pytest.mark.asyncio
async def test_handle_batch_processing_started_single_phase(
    notification_projector: NotificationProjector,
    mock_event_publisher: Mock,
) -> None:
    """Test notification projection for batch processing start with single phase."""
    # Arrange
    batch_id = "test-batch-123"
    user_id = "teacher-456"
    correlation_id = uuid4()
    requested_pipeline = "spellcheck"
    resolved_pipeline = [PhaseName.SPELLCHECK]

    # Act
    await notification_projector.handle_batch_processing_started(
        batch_id=batch_id,
        requested_pipeline=requested_pipeline,
        resolved_pipeline=resolved_pipeline,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]

    assert envelope.event_type == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert envelope.source_service == "batch_orchestrator_service"

    notification: TeacherNotificationRequestedV1 = envelope.data
    assert notification.teacher_id == user_id
    assert notification.notification_type == "batch_processing_started"
    assert notification.category == WebSocketEventCategory.BATCH_PROGRESS
    assert notification.priority == NotificationPriority.LOW
    assert notification.batch_id == batch_id
    assert notification.correlation_id == str(correlation_id)
    assert notification.action_required is False

    # Check payload
    payload = notification.payload
    assert payload["batch_id"] == batch_id
    assert payload["requested_pipeline"] == requested_pipeline
    assert payload["resolved_pipeline"] == ["spellcheck"]
    assert payload["first_phase"] == "spellcheck"
    assert payload["total_phases"] == 1
    assert "Processing started" in payload["message"]


@pytest.mark.asyncio
async def test_handle_batch_processing_started_multi_phase(
    notification_projector: NotificationProjector,
    mock_event_publisher: Mock,
) -> None:
    """Test notification projection for batch processing start with multiple phases."""
    # Arrange
    batch_id = "test-batch-789"
    user_id = "teacher-012"
    correlation_id = uuid4()
    requested_pipeline = "full_processing"
    resolved_pipeline = [
        PhaseName.SPELLCHECK,
        PhaseName.CJ_ASSESSMENT,
        PhaseName.AI_FEEDBACK,
    ]

    # Act
    await notification_projector.handle_batch_processing_started(
        batch_id=batch_id,
        requested_pipeline=requested_pipeline,
        resolved_pipeline=resolved_pipeline,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]

    notification: TeacherNotificationRequestedV1 = envelope.data

    # Check payload for multi-phase pipeline
    payload = notification.payload
    assert payload["resolved_pipeline"] == ["spellcheck", "cj_assessment", "ai_feedback"]
    assert payload["first_phase"] == "spellcheck"
    assert payload["total_phases"] == 3
    assert "Initiating spellcheck phase" in payload["message"]


@pytest.mark.asyncio
async def test_handle_batch_processing_started_empty_pipeline(
    notification_projector: NotificationProjector,
    mock_event_publisher: Mock,
) -> None:
    """Test notification projection when resolved pipeline is empty."""
    # Arrange
    batch_id = "test-batch-empty"
    user_id = "teacher-empty"
    correlation_id = uuid4()
    requested_pipeline = "unknown"
    resolved_pipeline: list[PhaseName] = []  # Empty pipeline

    # Act
    await notification_projector.handle_batch_processing_started(
        batch_id=batch_id,
        requested_pipeline=requested_pipeline,
        resolved_pipeline=resolved_pipeline,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]

    notification: TeacherNotificationRequestedV1 = envelope.data

    # Check payload handles empty pipeline gracefully
    payload = notification.payload
    assert payload["resolved_pipeline"] == []
    assert payload["first_phase"] == "unknown"
    assert payload["total_phases"] == 0
    assert "Initiating unknown phase" in payload["message"]


@pytest.mark.asyncio
async def test_notification_publish_failure_does_not_raise(
    notification_projector: NotificationProjector,
    mock_event_publisher: Mock,
) -> None:
    """Test that notification publish failures don't stop pipeline processing."""
    # Arrange
    batch_id = "test-batch-fail"
    user_id = "teacher-fail"
    correlation_id = uuid4()
    requested_pipeline = "spellcheck"
    resolved_pipeline = [PhaseName.SPELLCHECK]

    # Make the publisher raise an exception
    mock_event_publisher.publish_batch_event.side_effect = Exception("Kafka connection failed")

    # Act - should not raise
    await notification_projector.handle_batch_processing_started(
        batch_id=batch_id,
        requested_pipeline=requested_pipeline,
        resolved_pipeline=resolved_pipeline,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Assert - publisher was called but exception was caught
    mock_event_publisher.publish_batch_event.assert_called_once()


@pytest.mark.asyncio
async def test_notification_correct_priority_and_category(
    notification_projector: NotificationProjector,
    mock_event_publisher: Mock,
) -> None:
    """Test that notification has correct priority and category per spec."""
    # Arrange
    batch_id = "test-batch-priority"
    user_id = "teacher-priority"
    correlation_id = uuid4()
    requested_pipeline = "cj_assessment"
    resolved_pipeline = [PhaseName.CJ_ASSESSMENT]

    # Act
    await notification_projector.handle_batch_processing_started(
        batch_id=batch_id,
        requested_pipeline=requested_pipeline,
        resolved_pipeline=resolved_pipeline,
        user_id=user_id,
        correlation_id=correlation_id,
    )

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]

    notification: TeacherNotificationRequestedV1 = envelope.data

    # Per spec: batch_processing_started is LOW priority, BATCH_PROGRESS category
    assert notification.priority == NotificationPriority.LOW
    assert notification.category == WebSocketEventCategory.BATCH_PROGRESS
    assert notification.action_required is False


# Test methods for handle_batch_pipeline_completed


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_successful_completion(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test notification projection for successful pipeline completion."""
    # Arrange
    batch_id = "test-batch-success"
    user_id = "teacher-123"
    correlation_id = uuid4()
    
    # Mock batch repository response with user_id in processing_metadata
    mock_batch_repo.get_batch_by_id.return_value = {
        "batch_id": batch_id,
        "processing_metadata": {"user_id": user_id},
    }

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["spellcheck", "cj_assessment"],
        final_status="COMPLETED_SUCCESSFULLY",
        processing_duration_seconds=45.2,
        successful_essay_count=25,
        failed_essay_count=0,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert
    mock_batch_repo.get_batch_by_id.assert_called_once_with(batch_id)
    mock_event_publisher.publish_batch_event.assert_called_once()
    
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]
    notification: TeacherNotificationRequestedV1 = envelope.data

    # Verify notification properties for successful completion
    assert notification.teacher_id == user_id
    assert notification.notification_type == "pipeline_completed"
    assert notification.category == WebSocketEventCategory.BATCH_PROGRESS
    assert notification.priority == NotificationPriority.HIGH  # Successful completion is HIGH priority
    assert notification.action_required is False  # No action required for success
    assert notification.batch_id == batch_id
    assert notification.correlation_id == str(correlation_id)

    # Verify payload content
    payload = notification.payload
    assert payload["batch_id"] == batch_id
    assert payload["final_status"] == "COMPLETED_SUCCESSFULLY"
    assert payload["completed_phases"] == ["spellcheck", "cj_assessment"]
    assert payload["successful_essays"] == 25
    assert payload["failed_essays"] == 0
    assert payload["duration_seconds"] == 45.2
    assert "Pipeline completed successfully" in payload["message"]


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_with_failures(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test notification projection for pipeline completion with failures."""
    # Arrange
    batch_id = "test-batch-failures"
    user_id = "teacher-456"
    correlation_id = uuid4()
    
    # Mock batch repository response
    mock_batch_repo.get_batch_by_id.return_value = {
        "batch_id": batch_id,
        "processing_metadata": {"user_id": user_id},
    }

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["spellcheck", "cj_assessment"],
        final_status="COMPLETED_WITH_FAILURES",
        processing_duration_seconds=62.8,
        successful_essay_count=22,
        failed_essay_count=3,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]
    notification: TeacherNotificationRequestedV1 = envelope.data

    # Verify notification properties for completion with failures
    assert notification.teacher_id == user_id
    assert notification.priority == NotificationPriority.IMMEDIATE  # Failures are IMMEDIATE priority
    assert notification.action_required is True  # Action required for failures
    
    # Verify payload content shows failures
    payload = notification.payload
    assert payload["final_status"] == "COMPLETED_WITH_FAILURES"
    assert payload["successful_essays"] == 22
    assert payload["failed_essays"] == 3
    assert "Pipeline completed with 3 failures" in payload["message"]


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_missing_batch(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test graceful handling when batch is not found."""
    # Arrange
    batch_id = "nonexistent-batch"
    correlation_id = uuid4()
    
    # Mock batch repository to return None (batch not found)
    mock_batch_repo.get_batch_by_id.return_value = None

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["spellcheck"],
        final_status="COMPLETED_SUCCESSFULLY",
        processing_duration_seconds=30.0,
        successful_essay_count=10,
        failed_essay_count=0,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert
    mock_batch_repo.get_batch_by_id.assert_called_once_with(batch_id)
    # Should not publish notification when batch is not found
    mock_event_publisher.publish_batch_event.assert_not_called()


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_missing_user_id(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test graceful handling when user_id is missing from processing_metadata."""
    # Arrange
    batch_id = "test-batch-no-user"
    correlation_id = uuid4()
    
    # Mock batch repository response without user_id in processing_metadata
    mock_batch_repo.get_batch_by_id.return_value = {
        "batch_id": batch_id,
        "processing_metadata": {},  # No user_id field
    }

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["spellcheck"],
        final_status="COMPLETED_SUCCESSFULLY",
        processing_duration_seconds=25.0,
        successful_essay_count=15,
        failed_essay_count=0,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert
    mock_batch_repo.get_batch_by_id.assert_called_once_with(batch_id)
    # Should not publish notification when user_id is missing
    mock_event_publisher.publish_batch_event.assert_not_called()


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_publish_failure_does_not_raise(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test that notification publish failures don't stop pipeline completion processing."""
    # Arrange
    batch_id = "test-batch-publish-fail"
    user_id = "teacher-789"
    correlation_id = uuid4()
    
    # Mock batch repository response
    mock_batch_repo.get_batch_by_id.return_value = {
        "batch_id": batch_id,
        "processing_metadata": {"user_id": user_id},
    }

    # Make the publisher raise an exception
    mock_event_publisher.publish_batch_event.side_effect = Exception("Kafka connection failed")

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["spellcheck"],
        final_status="COMPLETED_SUCCESSFULLY",
        processing_duration_seconds=40.0,
        successful_essay_count=20,
        failed_essay_count=0,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act - should not raise exception
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert - publisher was called but exception was caught
    mock_event_publisher.publish_batch_event.assert_called_once()


@pytest.mark.asyncio
async def test_handle_batch_pipeline_completed_correct_envelope_structure(
    notification_projector: NotificationProjector,
    mock_batch_repo: Mock,
    mock_event_publisher: Mock,
) -> None:
    """Test that the event envelope has correct structure and source service."""
    # Arrange
    batch_id = "test-batch-envelope"
    user_id = "teacher-envelope"
    correlation_id = uuid4()
    
    mock_batch_repo.get_batch_by_id.return_value = {
        "batch_id": batch_id,
        "processing_metadata": {"user_id": user_id},
    }

    event = BatchPipelineCompletedV1(
        batch_id=batch_id,
        completed_phases=["cj_assessment"],
        final_status="COMPLETED_SUCCESSFULLY",
        processing_duration_seconds=55.0,
        successful_essay_count=18,
        failed_essay_count=0,
        correlation_id=correlation_id,
        metadata=SystemProcessingMetadata(
            entity_id=batch_id,
            entity_type="batch",
        ),
    )

    # Act
    await notification_projector.handle_batch_pipeline_completed(event)

    # Assert
    mock_event_publisher.publish_batch_event.assert_called_once()
    call_args = mock_event_publisher.publish_batch_event.call_args[0]
    envelope: EventEnvelope = call_args[0]

    # Verify envelope structure
    assert envelope.event_type == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert envelope.source_service == "batch_orchestrator_service"
    assert isinstance(envelope.data, TeacherNotificationRequestedV1)

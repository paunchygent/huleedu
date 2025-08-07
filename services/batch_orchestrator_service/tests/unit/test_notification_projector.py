"""Unit tests for Batch Orchestrator Service notification projector."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.events.notification_events import TeacherNotificationRequestedV1
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

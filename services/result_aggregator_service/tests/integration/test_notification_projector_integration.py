"""Integration tests for ResultNotificationProjector with OutboxManager.

Tests the complete flow from domain event to notification storage in outbox,
verifying the TRUE OUTBOX PATTERN implementation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.result_events import (
    BatchAssessmentCompletedV1,
    BatchResultsReadyV1,
    PhaseResultSummary,
)
from common_core.status_enums import BatchStatus
from common_core.websocket_enums import NotificationPriority, WebSocketEventCategory

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.implementations.outbox_manager import OutboxManager
from services.result_aggregator_service.notification_projector import ResultNotificationProjector


class MockOutboxRepository:
    """Mock outbox repository for testing."""

    def __init__(self) -> None:
        self.stored_events: list[dict] = []

    async def add_event(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: dict,
        topic: str,
    ) -> None:
        """Mock storing event in outbox."""
        self.stored_events.append({
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "event_data": event_data,
            "topic": topic,
        })

    async def get_unpublished_events(self, limit: int = 100) -> list[dict]:
        """Mock getting unpublished events."""
        return self.stored_events[:limit]


class MockAtomicRedisClient:
    """Mock atomic Redis client for testing."""

    def __init__(self) -> None:
        self.notifications_sent: list[str] = []

    async def lpush(self, _key: str, value: str) -> int:
        """Mock Redis LPUSH for notifications."""
        self.notifications_sent.append(value)
        return 1


@pytest.fixture
def mock_outbox_repository() -> MockOutboxRepository:
    """Provide mock outbox repository."""
    return MockOutboxRepository()


@pytest.fixture
def mock_redis_client() -> MockAtomicRedisClient:
    """Provide mock atomic Redis client."""
    return MockAtomicRedisClient()


@pytest.fixture
def settings() -> Settings:
    """Provide test settings."""
    return Settings()


@pytest.fixture
def outbox_manager(
    mock_outbox_repository: MockOutboxRepository,
    mock_redis_client: MockAtomicRedisClient,
    settings: Settings,
) -> OutboxManager:
    """Provide OutboxManager with mocked dependencies."""
    return OutboxManager(
        outbox_repository=mock_outbox_repository,
        redis_client=mock_redis_client,
        settings=settings,
    )


@pytest.fixture
def notification_projector(
    outbox_manager: OutboxManager,
    settings: Settings,
) -> ResultNotificationProjector:
    """Provide notification projector with real outbox manager."""
    return ResultNotificationProjector(
        outbox_manager=outbox_manager,
        settings=settings,
    )


@pytest.fixture
def sample_batch_results_ready_event() -> BatchResultsReadyV1:
    """Provide sample BatchResultsReadyV1 event."""
    return BatchResultsReadyV1(
        batch_id="integration-batch-123",
        user_id="integration-teacher-456",
        correlation_id=uuid4(),
        total_essays=15,
        completed_essays=15,
        phase_results={
            "spellcheck": PhaseResultSummary(
                phase_name="spellcheck",
                status="completed",
                completed_count=15,
                failed_count=0,
                processing_time_seconds=7.8,
            ),
            "cj_assessment": PhaseResultSummary(
                phase_name="cj_assessment",
                status="completed",
                completed_count=15,
                failed_count=0,
                processing_time_seconds=180.2,
            ),
        },
        overall_status=BatchStatus.COMPLETED,
        processing_duration_seconds=188.0,
        event_timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def sample_batch_assessment_completed_event() -> BatchAssessmentCompletedV1:
    """Provide sample BatchAssessmentCompletedV1 event."""
    return BatchAssessmentCompletedV1(
        batch_id="integration-batch-789",
        user_id="integration-teacher-101",
        assessment_job_id="integration-job-202",
        rankings_summary=[
            {"essay_id": "essay1", "rank": 1, "score": 0.92},
            {"essay_id": "essay2", "rank": 2, "score": 0.85},
            {"essay_id": "essay3", "rank": 3, "score": 0.78},
            {"essay_id": "essay4", "rank": 4, "score": 0.71},
        ],
        correlation_id=uuid4(),
        event_timestamp=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_batch_results_ready_end_to_end_flow(
    notification_projector: ResultNotificationProjector,
    mock_outbox_repository: MockOutboxRepository,
    mock_redis_client: MockAtomicRedisClient,
    sample_batch_results_ready_event: BatchResultsReadyV1,
) -> None:
    """Test complete flow from BatchResultsReadyV1 event to outbox storage."""
    # Act
    await notification_projector.handle_batch_results_ready(sample_batch_results_ready_event)

    # Assert outbox storage
    assert len(mock_outbox_repository.stored_events) == 1
    stored_event = mock_outbox_repository.stored_events[0]

    # Verify outbox parameters
    assert stored_event["aggregate_type"] == "teacher_notification"
    assert stored_event["aggregate_id"] == "integration-teacher-456"
    assert stored_event["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert stored_event["topic"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)

    # Verify event envelope structure
    event_data = stored_event["event_data"]
    assert event_data["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert event_data["source_service"] == "result_aggregator_service"

    # Verify notification content
    notification_data = event_data["data"]
    assert notification_data["teacher_id"] == "integration-teacher-456"
    assert notification_data["notification_type"] == "batch_results_ready"
    assert notification_data["category"] == WebSocketEventCategory.PROCESSING_RESULTS.value
    assert notification_data["priority"] == NotificationPriority.HIGH.value
    assert notification_data["batch_id"] == "integration-batch-123"
    assert notification_data["action_required"] is False

    # Verify payload details
    payload = notification_data["payload"]
    assert payload["batch_id"] == "integration-batch-123"
    assert payload["total_essays"] == 15
    assert payload["completed_essays"] == 15
    assert payload["overall_status"] == BatchStatus.COMPLETED.value
    assert payload["processing_duration_seconds"] == 188.0
    assert "integration-batch-123 processing completed with 15/15 essays" in payload["message"]

    # Verify phase results in payload
    assert "phase_results" in payload
    assert "spellcheck" in payload["phase_results"]
    assert "cj_assessment" in payload["phase_results"]
    spellcheck_result = payload["phase_results"]["spellcheck"]
    assert spellcheck_result["status"] == "completed"
    assert spellcheck_result["completed_count"] == 15
    assert spellcheck_result["failed_count"] == 0
    assert spellcheck_result["processing_time_seconds"] == 7.8

    # Verify Redis notification was sent for relay worker wake-up
    assert len(mock_redis_client.notifications_sent) == 1
    assert mock_redis_client.notifications_sent[0] == "result_aggregator_service"


@pytest.mark.asyncio
async def test_batch_assessment_completed_end_to_end_flow(
    notification_projector: ResultNotificationProjector,
    mock_outbox_repository: MockOutboxRepository,
    mock_redis_client: MockAtomicRedisClient,
    sample_batch_assessment_completed_event: BatchAssessmentCompletedV1,
) -> None:
    """Test complete flow from BatchAssessmentCompletedV1 event to outbox storage."""
    # Act
    await notification_projector.handle_batch_assessment_completed(sample_batch_assessment_completed_event)

    # Assert outbox storage
    assert len(mock_outbox_repository.stored_events) == 1
    stored_event = mock_outbox_repository.stored_events[0]

    # Verify outbox parameters
    assert stored_event["aggregate_type"] == "teacher_notification"
    assert stored_event["aggregate_id"] == "integration-teacher-101"
    assert stored_event["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert stored_event["topic"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)

    # Verify event envelope structure
    event_data = stored_event["event_data"]
    assert event_data["event_type"] == topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert event_data["source_service"] == "result_aggregator_service"

    # Verify notification content
    notification_data = event_data["data"]
    assert notification_data["teacher_id"] == "integration-teacher-101"
    assert notification_data["notification_type"] == "batch_assessment_completed"
    assert notification_data["category"] == WebSocketEventCategory.PROCESSING_RESULTS.value
    assert notification_data["priority"] == NotificationPriority.STANDARD.value
    assert notification_data["batch_id"] == "integration-batch-789"
    assert notification_data["action_required"] is False

    # Verify payload details
    payload = notification_data["payload"]
    assert payload["batch_id"] == "integration-batch-789"
    assert payload["assessment_job_id"] == "integration-job-202"
    assert payload["rankings_available"] is True
    assert payload["rankings_count"] == 4
    assert "Comparative judgment assessment completed for batch integration-batch-789" in payload["message"]

    # Verify Redis notification was sent for relay worker wake-up
    assert len(mock_redis_client.notifications_sent) == 1
    assert mock_redis_client.notifications_sent[0] == "result_aggregator_service"


@pytest.mark.asyncio
async def test_multiple_notifications_stored_separately(
    notification_projector: ResultNotificationProjector,
    mock_outbox_repository: MockOutboxRepository,
    sample_batch_results_ready_event: BatchResultsReadyV1,
    sample_batch_assessment_completed_event: BatchAssessmentCompletedV1,
) -> None:
    """Test that multiple notifications are stored separately in outbox."""
    # Act - Process both events
    await notification_projector.handle_batch_results_ready(sample_batch_results_ready_event)
    await notification_projector.handle_batch_assessment_completed(sample_batch_assessment_completed_event)

    # Assert - Two separate events stored
    assert len(mock_outbox_repository.stored_events) == 2

    # Verify first notification (batch results ready)
    first_event = mock_outbox_repository.stored_events[0]
    first_notification = first_event["event_data"]["data"]
    assert first_notification["teacher_id"] == "integration-teacher-456"
    assert first_notification["notification_type"] == "batch_results_ready"
    assert first_notification["priority"] == NotificationPriority.HIGH.value

    # Verify second notification (assessment completed)
    second_event = mock_outbox_repository.stored_events[1]
    second_notification = second_event["event_data"]["data"]
    assert second_notification["teacher_id"] == "integration-teacher-101"
    assert second_notification["notification_type"] == "batch_assessment_completed"
    assert second_notification["priority"] == NotificationPriority.STANDARD.value


@pytest.mark.asyncio
async def test_outbox_manager_failure_propagation(
    mock_outbox_repository: MockOutboxRepository,
    mock_redis_client: MockAtomicRedisClient,
    settings: Settings,
    sample_batch_results_ready_event: BatchResultsReadyV1,
) -> None:
    """Test that OutboxManager failures are properly propagated."""
    # Arrange - Create failing outbox repository
    failing_repo = AsyncMock(spec=OutboxRepositoryProtocol)
    failing_repo.add_event.side_effect = Exception("Database connection failed")

    outbox_manager = OutboxManager(
        outbox_repository=failing_repo,
        redis_client=mock_redis_client,
        settings=settings,
    )

    notification_projector = ResultNotificationProjector(
        outbox_manager=outbox_manager,
        settings=settings,
    )

    # Act & Assert - Exception should be propagated
    with pytest.raises(Exception, match="Database connection failed"):
        await notification_projector.handle_batch_results_ready(sample_batch_results_ready_event)


@pytest.mark.asyncio
async def test_true_outbox_pattern_compliance(
    notification_projector: ResultNotificationProjector,
    mock_outbox_repository: MockOutboxRepository,
    sample_batch_results_ready_event: BatchResultsReadyV1,
) -> None:
    """Test compliance with TRUE OUTBOX PATTERN requirements."""
    # Act
    await notification_projector.handle_batch_results_ready(sample_batch_results_ready_event)

    # Assert TRUE OUTBOX PATTERN compliance
    assert len(mock_outbox_repository.stored_events) == 1
    stored_event = mock_outbox_repository.stored_events[0]

    # 1. Event stored in database (outbox)
    assert stored_event["aggregate_type"] == "teacher_notification"
    assert stored_event["aggregate_id"] == "integration-teacher-456"

    # 2. No direct Kafka publishing (verified by mocking)
    # The notification projector should NEVER directly publish to Kafka
    # All publishing goes through the outbox pattern

    # 3. Event envelope properly formatted for relay worker
    event_data = stored_event["event_data"]
    assert "event_id" in event_data
    assert "event_type" in event_data
    assert "event_timestamp" in event_data
    assert "source_service" in event_data
    assert "correlation_id" in event_data
    assert "data" in event_data

    # 4. Proper topic configuration
    expected_topic = topic_name(ProcessingEvent.TEACHER_NOTIFICATION_REQUESTED)
    assert stored_event["topic"] == expected_topic
    assert stored_event["event_type"] == expected_topic

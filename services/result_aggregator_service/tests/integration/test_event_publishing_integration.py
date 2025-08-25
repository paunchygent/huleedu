"""Integration tests for EventProcessorImpl event publishing functionality."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.events import (
    ELSBatchPhaseOutcomeV1,
    EventEnvelope,
)
from common_core.events.result_events import (
    BatchAssessmentCompletedV1,
    BatchResultsReadyV1,
)
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
)
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, ProcessingStage

from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)


@pytest.fixture
def mock_batch_repository() -> AsyncMock:
    """Mock batch repository for testing."""
    return AsyncMock()


@pytest.fixture
def mock_state_store() -> AsyncMock:
    """Mock state store for testing."""
    return AsyncMock()


@pytest.fixture
def mock_cache_manager() -> AsyncMock:
    """Mock cache manager for testing."""
    return AsyncMock()


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mock event publisher for testing."""
    publisher = AsyncMock()
    publisher.publish_batch_results_ready = AsyncMock()
    publisher.publish_batch_assessment_completed = AsyncMock()
    return publisher


@pytest.fixture
def event_processor(
    mock_batch_repository: AsyncMock,
    mock_state_store: AsyncMock,
    mock_cache_manager: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> EventProcessorImpl:
    """Create EventProcessorImpl with mocked dependencies."""
    return EventProcessorImpl(
        batch_repository=mock_batch_repository,
        state_store=mock_state_store,
        cache_manager=mock_cache_manager,
        event_publisher=mock_event_publisher,
    )


@pytest.mark.asyncio
async def test_batch_results_ready_published_when_all_phases_complete(
    event_processor: EventProcessorImpl,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test that BatchResultsReadyV1 is published when all phases complete."""
    # Arrange
    batch_id = str(uuid4())
    user_id = str(uuid4())
    correlation_id = uuid4()

    # Create mock batch
    mock_batch = MagicMock()
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id
    # Use timezone-naive timestamps to match service duration calculations
    mock_batch.processing_started_at = datetime.utcnow()
    mock_batch.processing_completed_at = None

    # Create mock essays with all phases completed
    mock_essays = [
        MagicMock(
            essay_id=f"essay_{i}",
            spellcheck_status=ProcessingStage.COMPLETED,
            spellcheck_completed_at=datetime.utcnow(),
            cj_assessment_status=ProcessingStage.COMPLETED,
            cj_assessment_completed_at=datetime.utcnow(),
        )
        for i in range(3)
    ]

    # Setup repository mocks
    mock_batch_repository.get_batch.return_value = mock_batch
    mock_batch_repository.get_batch_essays.return_value = mock_essays
    mock_batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event
    envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
        event_type="huleedu.els.batch.phase_outcome.v1",
        source_service="essay_lifecycle_service",
        correlation_id=correlation_id,
        data=ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay_0", text_storage_id="storage_0"),
                EssayProcessingInputRefV1(essay_id="essay_1", text_storage_id="storage_1"),
                EssayProcessingInputRefV1(essay_id="essay_2", text_storage_id="storage_2"),
            ],
            failed_essay_ids=[],
        ),
    )

    # Act
    await event_processor.process_batch_phase_outcome(envelope, envelope.data)

    # Assert
    mock_event_publisher.publish_batch_results_ready.assert_called_once()

    # Verify the event data
    call_args = mock_event_publisher.publish_batch_results_ready.call_args
    event_data: BatchResultsReadyV1 = call_args.kwargs["event_data"]

    assert event_data.batch_id == batch_id
    assert event_data.user_id == user_id
    assert event_data.total_essays == 3
    assert event_data.completed_essays == 3
    assert event_data.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
    assert call_args.kwargs["correlation_id"] == correlation_id

    # Verify phase results
    assert "spellcheck" in event_data.phase_results
    assert "cj_assessment" in event_data.phase_results
    assert event_data.phase_results["spellcheck"].completed_count == 3
    assert event_data.phase_results["spellcheck"].failed_count == 0
    assert event_data.phase_results["cj_assessment"].completed_count == 3
    assert event_data.phase_results["cj_assessment"].failed_count == 0


@pytest.mark.asyncio
async def test_batch_results_ready_not_published_when_phases_incomplete(
    event_processor: EventProcessorImpl,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test that BatchResultsReadyV1 is NOT published when phases are incomplete."""
    # Arrange
    batch_id = str(uuid4())
    correlation_id = uuid4()

    # Create mock batch
    mock_batch = MagicMock()
    mock_batch.batch_id = batch_id
    mock_batch.user_id = str(uuid4())

    # Create mock essays with incomplete phases (CJ not done)
    mock_essays = [
        MagicMock(
            essay_id=f"essay_{i}",
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=None,  # CJ not done yet
        )
        for i in range(3)
    ]

    # Setup repository mocks
    mock_batch_repository.get_batch.return_value = mock_batch
    mock_batch_repository.get_batch_essays.return_value = mock_essays
    mock_batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event
    envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
        event_type="huleedu.els.batch.phase_outcome.v1",
        source_service="essay_lifecycle_service",
        correlation_id=correlation_id,
        data=ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay_0", text_storage_id="storage_0"),
                EssayProcessingInputRefV1(essay_id="essay_1", text_storage_id="storage_1"),
                EssayProcessingInputRefV1(essay_id="essay_2", text_storage_id="storage_2"),
            ],
            failed_essay_ids=[],
        ),
    )

    # Act
    await event_processor.process_batch_phase_outcome(envelope, envelope.data)

    # Assert - Event should NOT be published
    mock_event_publisher.publish_batch_results_ready.assert_not_called()


@pytest.mark.asyncio
async def test_batch_assessment_completed_published_on_assessment_result(
    event_processor: EventProcessorImpl,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test that BatchAssessmentCompletedV1 is published when AssessmentResultV1 is received."""
    # Arrange
    batch_id = str(uuid4())
    user_id = str(uuid4())
    correlation_id = uuid4()
    job_id = str(uuid4())

    # Create mock batch
    mock_batch = MagicMock()
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id

    # Setup repository mocks
    mock_batch_repository.get_batch.return_value = mock_batch
    mock_batch_repository.update_essay_cj_assessment_result = AsyncMock()

    # Create assessment result event (new pattern)
    from common_core.events.cj_assessment_events import AssessmentResultV1

    essay_results = [
        {
            "essay_id": "essay_0",
            "normalized_score": 0.95,
            "letter_grade": "A",
            "confidence_score": 0.9,
            "confidence_label": "HIGH",
            "bt_score": 0.95,
            "rank": 1,
            "is_anchor": False,
        },
        {
            "essay_id": "essay_1",
            "normalized_score": 0.85,
            "letter_grade": "B",
            "confidence_score": 0.8,
            "confidence_label": "MID",
            "bt_score": 0.85,
            "rank": 2,
            "is_anchor": False,
        },
        {
            "essay_id": "essay_2",
            "normalized_score": 0.75,
            "letter_grade": "C",
            "confidence_score": 0.7,
            "confidence_label": "MID",
            "bt_score": 0.75,
            "rank": 3,
            "is_anchor": False,
        },
    ]

    envelope: EventEnvelope[AssessmentResultV1] = EventEnvelope(
        event_type="huleedu.assessment.results.v1",
        source_service="cj_assessment_service",
        correlation_id=correlation_id,
        data=AssessmentResultV1(
            entity_id=batch_id,
            entity_type="batch",
            batch_id=batch_id,
            cj_assessment_job_id=job_id,
            assessment_method="cj_assessment",
            model_used="gpt-4",
            model_provider="openai",
            essay_results=essay_results,
            assessment_metadata={
                "anchor_essays_used": 0,
                "calibration_method": "default",
                "comparison_count": 10,
                "processing_duration_seconds": 15.5,
            },
        ),
    )

    # Act
    await event_processor.process_assessment_result(envelope, envelope.data)

    # Assert
    mock_event_publisher.publish_batch_assessment_completed.assert_called_once()

    # Verify the event data
    call_args = mock_event_publisher.publish_batch_assessment_completed.call_args
    event_data: BatchAssessmentCompletedV1 = call_args.kwargs["event_data"]

    assert event_data.batch_id == batch_id
    assert event_data.user_id == user_id
    assert event_data.assessment_job_id == job_id
    assert call_args.kwargs["correlation_id"] == correlation_id

    # Verify rankings summary
    assert len(event_data.rankings_summary) == 3
    assert event_data.rankings_summary[0]["essay_id"] == "essay_0"
    assert event_data.rankings_summary[0]["rank"] == 1
    assert event_data.rankings_summary[0]["score"] == 0.95
    assert event_data.rankings_summary[0]["letter_grade"] == "A"
    assert event_data.rankings_summary[0]["confidence_score"] == 0.9


@pytest.mark.asyncio
async def test_batch_results_ready_with_partial_failures(
    event_processor: EventProcessorImpl,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test that BatchResultsReadyV1 handles partial failures correctly."""
    # Arrange
    batch_id = str(uuid4())
    user_id = str(uuid4())
    correlation_id = uuid4()

    # Create mock batch
    mock_batch = MagicMock()
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id
    # Use timezone-naive timestamps to match service duration calculations
    mock_batch.processing_started_at = datetime.utcnow()
    mock_batch.processing_completed_at = None

    # Create mock essays with some failures
    mock_essays = [
        MagicMock(
            essay_id="essay_0",
            spellcheck_status=ProcessingStage.COMPLETED,
            spellcheck_completed_at=datetime.utcnow(),
            cj_assessment_status=ProcessingStage.COMPLETED,
            cj_assessment_completed_at=datetime.utcnow(),
        ),
        MagicMock(
            essay_id="essay_1",
            spellcheck_status=ProcessingStage.FAILED,  # Failed spellcheck
            spellcheck_completed_at=datetime.utcnow(),
            cj_assessment_status=ProcessingStage.COMPLETED,
            cj_assessment_completed_at=datetime.utcnow(),
        ),
        MagicMock(
            essay_id="essay_2",
            spellcheck_status=ProcessingStage.COMPLETED,
            spellcheck_completed_at=datetime.now(timezone.utc),
            cj_assessment_status=ProcessingStage.FAILED,  # Failed CJ
            cj_assessment_completed_at=datetime.now(timezone.utc),
        ),
    ]

    # Setup repository mocks
    mock_batch_repository.get_batch.return_value = mock_batch
    mock_batch_repository.get_batch_essays.return_value = mock_essays
    mock_batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event
    envelope: EventEnvelope[ELSBatchPhaseOutcomeV1] = EventEnvelope(
        event_type="huleedu.els.batch.phase_outcome.v1",
        source_service="essay_lifecycle_service",
        correlation_id=correlation_id,
        data=ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=PhaseName.CJ_ASSESSMENT,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,
            processed_essays=[
                EssayProcessingInputRefV1(essay_id="essay_0", text_storage_id="storage_0"),
                EssayProcessingInputRefV1(essay_id="essay_2", text_storage_id="storage_2"),
            ],
            failed_essay_ids=["essay_1"],
        ),
    )

    # Act
    await event_processor.process_batch_phase_outcome(envelope, envelope.data)

    # Assert
    mock_event_publisher.publish_batch_results_ready.assert_called_once()

    # Verify the event data
    call_args = mock_event_publisher.publish_batch_results_ready.call_args
    event_data: BatchResultsReadyV1 = call_args.kwargs["event_data"]

    assert event_data.batch_id == batch_id
    assert event_data.overall_status == BatchStatus.COMPLETED_WITH_FAILURES

    # Verify phase results
    assert event_data.phase_results["spellcheck"].completed_count == 2
    assert event_data.phase_results["spellcheck"].failed_count == 1
    assert event_data.phase_results["cj_assessment"].completed_count == 2
    assert event_data.phase_results["cj_assessment"].failed_count == 1


@pytest.mark.asyncio
async def test_correlation_id_propagation(
    event_processor: EventProcessorImpl,
    mock_batch_repository: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> None:
    """Test that correlation_id is properly propagated through event publishing."""
    # Arrange
    batch_id = str(uuid4())
    user_id = str(uuid4())
    correlation_id = uuid4()
    job_id = str(uuid4())

    # Create mock batch
    mock_batch = MagicMock()
    mock_batch.batch_id = batch_id
    mock_batch.user_id = user_id

    # Setup repository mocks
    mock_batch_repository.get_batch.return_value = mock_batch
    mock_batch_repository.update_essay_cj_assessment_result = AsyncMock()

    # Create assessment result event with specific correlation_id (new pattern)
    from common_core.events.cj_assessment_events import AssessmentResultV1

    envelope: EventEnvelope[AssessmentResultV1] = EventEnvelope(
        event_type="huleedu.assessment.results.v1",
        source_service="cj_assessment_service",
        correlation_id=correlation_id,
        data=AssessmentResultV1(
            entity_id=batch_id,
            entity_type="batch",
            batch_id=batch_id,
            cj_assessment_job_id=job_id,
            assessment_method="cj_assessment",
            model_used="gpt-4",
            model_provider="openai",
            essay_results=[],  # Empty results for this test
            assessment_metadata={
                "anchor_essays_used": 0,
                "calibration_method": "default",
                "comparison_count": 0,
                "processing_duration_seconds": 0.0,
            },
        ),
    )

    # Act
    await event_processor.process_assessment_result(envelope, envelope.data)

    # Assert
    call_args = mock_event_publisher.publish_batch_assessment_completed.call_args
    assert call_args.kwargs["correlation_id"] == correlation_id

"""Integration test for Result Aggregator Service batch phase outcome processing.

Tests RAS's ability to:
1. Process ELSBatchPhaseOutcomeV1 events from Essay Lifecycle Service
2. Publish BatchResultsReadyV1 events when all phases complete
3. Handle timezone-aware processing_started_at field correctly
4. Follow DDD patterns with proper protocol-based dependency injection

Follows .cursor/rules/075-test-creation-methodology.md patterns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.events import ELSBatchPhaseOutcomeV1, EventEnvelope
from common_core.events.result_events import BatchResultsReadyV1
from common_core.metadata_models import EssayProcessingInputRefV1
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus, ProcessingStage

from services.result_aggregator_service.implementations.event_processor_impl import (
    EventProcessorImpl,
)
from services.result_aggregator_service.models_db import BatchResult, EssayResult


@pytest.mark.asyncio
async def test_batch_results_ready_published_when_all_phases_complete():
    """Test that BatchResultsReadyV1 is published when all phases are complete."""

    # Create mocks
    batch_repository = AsyncMock()
    event_publisher = AsyncMock()
    state_store = AsyncMock()
    cache_manager = AsyncMock()

    # Create processor
    processor = EventProcessorImpl(
        batch_repository=batch_repository,
        state_store=state_store,
        cache_manager=cache_manager,
        event_publisher=event_publisher,
    )

    # Setup test data
    batch_id = str(uuid4())
    user_id = "test-user-123"
    correlation_id = uuid4()

    # Mock batch data WITH processing_started_at already set (batch in progress)
    mock_batch = BatchResult(
        batch_id=batch_id,
        user_id=user_id,
        overall_status=BatchStatus.PROCESSING_PIPELINES,
        essay_count=2,
        completed_essay_count=0,
        requested_pipeline="cj_assessment",
        processing_started_at=datetime.now(UTC).replace(tzinfo=None),
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # Mock essay results - all completed
    mock_essays = [
        EssayResult(
            essay_id="essay-1",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.COMPLETED,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
        EssayResult(
            essay_id="essay-2",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.COMPLETED,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
    ]

    # Setup repository mocks
    batch_repository.get_batch.return_value = mock_batch
    batch_repository.get_batch_essays.return_value = mock_essays
    batch_repository.set_batch_processing_started = AsyncMock()
    batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event (final phase) with proper data structures
    processed_essays = [
        EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-corrected-1"),
        EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-corrected-2"),
    ]

    phase_outcome_event = ELSBatchPhaseOutcomeV1(
        batch_id=batch_id,
        phase_name=PhaseName.CJ_ASSESSMENT,  # Use proper enum
        phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
        processed_essays=processed_essays,
        failed_essay_ids=[],
        correlation_id=correlation_id,
    )

    envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
        event_type="huleedu.els.batch.phase.outcome.v1",
        event_timestamp=datetime.now(UTC),
        source_service="essay-lifecycle-service",
        correlation_id=correlation_id,
        data=phase_outcome_event,
        metadata={},
    )

    # Process the event
    await processor.process_batch_phase_outcome(envelope, phase_outcome_event)

    # Verify BatchResultsReadyV1 was published
    event_publisher.publish_batch_results_ready.assert_called_once()

    # Verify the event data with comprehensive assertions
    call_args = event_publisher.publish_batch_results_ready.call_args
    event_data = call_args.kwargs["event_data"]
    correlation_id_arg = call_args.kwargs["correlation_id"]

    assert isinstance(event_data, BatchResultsReadyV1)
    assert event_data.batch_id == batch_id
    assert event_data.user_id == user_id
    assert event_data.total_essays == 2
    assert event_data.completed_essays == 2
    assert event_data.overall_status == BatchStatus.COMPLETED_SUCCESSFULLY
    assert event_data.processing_duration_seconds >= 0
    assert correlation_id_arg == correlation_id

    # Verify phase results structure
    assert "spellcheck" in event_data.phase_results
    assert "cj_assessment" in event_data.phase_results
    assert event_data.phase_results["spellcheck"].completed_count == 2
    assert event_data.phase_results["cj_assessment"].completed_count == 2

    # Verify system metadata
    assert event_data.system_metadata.entity_id == batch_id
    assert event_data.system_metadata.entity_type == "batch"
    assert event_data.system_metadata.event == "results_ready"

    # Verify processing_started_at was NOT called (batch already had it set)
    batch_repository.set_batch_processing_started.assert_not_called()

    # Verify phase completion was updated
    batch_repository.update_batch_phase_completed.assert_called_once_with(
        batch_id=batch_id,
        phase="cj_assessment",
        completed_count=2,
        failed_count=0,
    )


@pytest.mark.asyncio
async def test_batch_results_not_published_when_phases_incomplete():
    """Test that BatchResultsReadyV1 is NOT published when phases are incomplete."""

    # Create mocks
    batch_repository = AsyncMock()
    event_publisher = AsyncMock()
    state_store = AsyncMock()
    cache_manager = AsyncMock()

    # Create processor
    processor = EventProcessorImpl(
        batch_repository=batch_repository,
        state_store=state_store,
        cache_manager=cache_manager,
        event_publisher=event_publisher,
    )

    # Setup test data
    batch_id = str(uuid4())
    user_id = "test-user-456"
    correlation_id = uuid4()

    # Mock batch data WITHOUT processing_started_at to trigger first-phase behavior
    mock_batch = BatchResult(
        batch_id=batch_id,
        user_id=user_id,
        overall_status=BatchStatus.PROCESSING_PIPELINES,
        essay_count=2,
        completed_essay_count=0,
        requested_pipeline="cj_assessment",
        processing_started_at=None,  # Not yet set
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # Mock essay results - CJ assessment not complete
    mock_essays = [
        EssayResult(
            essay_id="essay-1",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.PENDING,  # Not complete
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
        EssayResult(
            essay_id="essay-2",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.PENDING,  # Not complete
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
    ]

    # Setup repository mocks
    batch_repository.get_batch.return_value = mock_batch
    batch_repository.get_batch_essays.return_value = mock_essays
    batch_repository.set_batch_processing_started = AsyncMock()
    batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event (spellcheck phase) with proper data structures
    processed_essays = [
        EssayProcessingInputRefV1(essay_id="essay-1", text_storage_id="storage-corrected-1"),
        EssayProcessingInputRefV1(essay_id="essay-2", text_storage_id="storage-corrected-2"),
    ]

    phase_outcome_event = ELSBatchPhaseOutcomeV1(
        batch_id=batch_id,
        phase_name=PhaseName.SPELLCHECK,  # Use proper enum
        phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
        processed_essays=processed_essays,
        failed_essay_ids=[],
        correlation_id=correlation_id,
    )

    envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
        event_type="huleedu.els.batch.phase.outcome.v1",
        event_timestamp=datetime.now(UTC),
        source_service="essay-lifecycle-service",
        correlation_id=correlation_id,
        data=phase_outcome_event,
        metadata={},
    )

    # Process the event
    await processor.process_batch_phase_outcome(envelope, phase_outcome_event)

    # Verify BatchResultsReadyV1 was NOT published since CJ assessment is incomplete
    event_publisher.publish_batch_results_ready.assert_not_called()

    # Verify batch processing was still updated
    batch_repository.set_batch_processing_started.assert_called_once_with(batch_id)
    batch_repository.update_batch_phase_completed.assert_called_once_with(
        batch_id=batch_id,
        phase="spellcheck",
        completed_count=2,
        failed_count=0,
    )


@pytest.mark.asyncio
async def test_processing_started_at_timezone_handling():
    """Test that processing_started_at is set correctly without timezone errors.

    This test verifies the fix for the timezone bug where datetime.now(timezone.utc)
    was changed to datetime.now(UTC).replace(tzinfo=None) in batch_repository_postgres_impl.py.
    """
    # Create mocks
    batch_repository = AsyncMock()
    event_publisher = AsyncMock()
    state_store = AsyncMock()
    cache_manager = AsyncMock()

    # Create processor
    processor = EventProcessorImpl(
        batch_repository=batch_repository,
        state_store=state_store,
        cache_manager=cache_manager,
        event_publisher=event_publisher,
    )

    # Setup test data
    batch_id = str(uuid4())
    user_id = "test-user-timezone"
    correlation_id = uuid4()

    # Mock batch data WITHOUT processing_started_at to simulate first phase event
    mock_batch = BatchResult(
        batch_id=batch_id,
        user_id=user_id,
        overall_status=BatchStatus.PROCESSING_PIPELINES,
        essay_count=1,
        completed_essay_count=0,
        requested_pipeline="spellcheck",
        processing_started_at=None,  # Not yet set
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # Mock essay results - only spellcheck being processed, CJ assessment still pending
    mock_essays = [
        EssayResult(
            essay_id="essay-timezone-test",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.PENDING,  # Being processed now
            cj_assessment_status=ProcessingStage.PENDING,  # Not yet started
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
    ]

    # Setup repository mocks
    batch_repository.get_batch.return_value = mock_batch
    batch_repository.get_batch_essays.return_value = mock_essays
    batch_repository.set_batch_processing_started = AsyncMock()
    batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event (first phase event)
    processed_essays = [
        EssayProcessingInputRefV1(
            essay_id="essay-timezone-test", text_storage_id="storage-corrected-timezone"
        ),
    ]

    phase_outcome_event = ELSBatchPhaseOutcomeV1(
        batch_id=batch_id,
        phase_name=PhaseName.SPELLCHECK,
        phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
        processed_essays=processed_essays,
        failed_essay_ids=[],
        correlation_id=correlation_id,
    )

    envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
        event_type="huleedu.els.batch.phase.outcome.v1",
        event_timestamp=datetime.now(UTC),
        source_service="essay-lifecycle-service",
        correlation_id=correlation_id,
        data=phase_outcome_event,
        metadata={},
    )

    # Process the event - this should set processing_started_at without timezone errors
    await processor.process_batch_phase_outcome(envelope, phase_outcome_event)

    # Verify set_batch_processing_started was called (timezone fix verification)
    batch_repository.set_batch_processing_started.assert_called_once_with(batch_id)

    # Verify phase completion was updated
    batch_repository.update_batch_phase_completed.assert_called_once_with(
        batch_id=batch_id,
        phase="spellcheck",
        completed_count=1,
        failed_count=0,
    )

    # Verify cache invalidation
    state_store.invalidate_batch.assert_called_once_with(batch_id)

    # Verify BatchResultsReadyV1 was NOT published (CJ assessment still pending)
    event_publisher.publish_batch_results_ready.assert_not_called()


@pytest.mark.asyncio
async def test_batch_completion_with_mixed_phase_status():
    """Test BatchResultsReadyV1 publication with some failed essays.

    Verifies that the event is still published when both phases complete,
    even if some essays failed, and that the status reflects failures.
    """
    # Create mocks
    batch_repository = AsyncMock()
    event_publisher = AsyncMock()
    state_store = AsyncMock()
    cache_manager = AsyncMock()

    # Create processor
    processor = EventProcessorImpl(
        batch_repository=batch_repository,
        state_store=state_store,
        cache_manager=cache_manager,
        event_publisher=event_publisher,
    )

    # Setup test data
    batch_id = str(uuid4())
    user_id = "test-user-mixed-status"
    correlation_id = uuid4()

    # Mock batch data
    mock_batch = BatchResult(
        batch_id=batch_id,
        user_id=user_id,
        overall_status=BatchStatus.PROCESSING_PIPELINES,
        essay_count=3,
        completed_essay_count=0,
        requested_pipeline="cj_assessment",
        processing_started_at=datetime.now(UTC).replace(tzinfo=None),
        created_at=datetime.now(UTC).replace(tzinfo=None),
        updated_at=datetime.now(UTC).replace(tzinfo=None),
    )

    # Mock essay results - mixed success/failure status
    mock_essays = [
        EssayResult(
            essay_id="essay-success-1",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.COMPLETED,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
        EssayResult(
            essay_id="essay-success-2",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.COMPLETED,
            cj_assessment_status=ProcessingStage.COMPLETED,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
        EssayResult(
            essay_id="essay-failed-1",
            batch_id=batch_id,
            spellcheck_status=ProcessingStage.FAILED,
            cj_assessment_status=ProcessingStage.FAILED,
            created_at=datetime.now(UTC).replace(tzinfo=None),
            updated_at=datetime.now(UTC).replace(tzinfo=None),
        ),
    ]

    # Setup repository mocks
    batch_repository.get_batch.return_value = mock_batch
    batch_repository.get_batch_essays.return_value = mock_essays
    batch_repository.set_batch_processing_started = AsyncMock()
    batch_repository.update_batch_phase_completed = AsyncMock()

    # Create phase outcome event (final phase with failures)
    processed_essays = [
        EssayProcessingInputRefV1(
            essay_id="essay-success-1", text_storage_id="storage-corrected-1"
        ),
        EssayProcessingInputRefV1(
            essay_id="essay-success-2", text_storage_id="storage-corrected-2"
        ),
    ]

    phase_outcome_event = ELSBatchPhaseOutcomeV1(
        batch_id=batch_id,
        phase_name=PhaseName.CJ_ASSESSMENT,
        phase_status=BatchStatus.COMPLETED_WITH_FAILURES,  # Mixed status
        processed_essays=processed_essays,
        failed_essay_ids=["essay-failed-1"],
        correlation_id=correlation_id,
    )

    envelope = EventEnvelope[ELSBatchPhaseOutcomeV1](
        event_type="huleedu.els.batch.phase.outcome.v1",
        event_timestamp=datetime.now(UTC),
        source_service="essay-lifecycle-service",
        correlation_id=correlation_id,
        data=phase_outcome_event,
        metadata={},
    )

    # Process the event
    await processor.process_batch_phase_outcome(envelope, phase_outcome_event)

    # Verify BatchResultsReadyV1 was published despite failures
    event_publisher.publish_batch_results_ready.assert_called_once()

    # Verify the event data reflects mixed status
    call_args = event_publisher.publish_batch_results_ready.call_args
    event_data = call_args.kwargs["event_data"]

    assert event_data.overall_status == BatchStatus.COMPLETED_WITH_FAILURES
    assert event_data.total_essays == 3
    assert event_data.completed_essays == 2  # Only successful essays

    # Verify phase results show failures
    assert event_data.phase_results["spellcheck"].failed_count == 1
    assert event_data.phase_results["cj_assessment"].failed_count == 1

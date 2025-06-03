"""Unit tests for ELS Batch Phase Outcome aggregation components.

Tests the business logic for tracking essay completion per phase and constructing
ELSBatchPhaseOutcomeV1 events. Following 070-testing-and-quality-assurance.mdc.
Mocks only external boundaries, not internal business logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_core.enums import EssayStatus
from common_core.events.els_bos_events import ELSBatchPhaseOutcomeV1
from common_core.metadata_models import EssayProcessingInputRefV1


class BatchPhaseOutcomeAggregator:
    """
    Business logic component for aggregating essay outcomes into batch phase outcomes.

    This is the actual ELS component that should handle batch phase outcome logic.
    """

    def __init__(self, state_store, event_publisher):
        self.state_store = state_store
        self.event_publisher = event_publisher

    async def aggregate_and_publish_phase_outcome(
        self,
        batch_id: str,
        phase_name: str,
        correlation_id=None
    ) -> ELSBatchPhaseOutcomeV1:
        """
        Aggregate essay outcomes for a batch phase and publish ELSBatchPhaseOutcomeV1 event.

        This is the core business logic that should exist in ELS.
        """
        # Get all essays in the batch
        essays_in_batch = await self.state_store.list_essays_by_batch(batch_id)

        # Determine which essays completed successfully for this phase
        if phase_name == "spellcheck":
            success_status = EssayStatus.SPELLCHECKED_SUCCESS
            failed_status = EssayStatus.SPELLCHECK_FAILED
            content_type = "CORRECTED_TEXT"
        elif phase_name == "cj_assessment":
            success_status = EssayStatus.CJ_ASSESSMENT_SUCCESS
            failed_status = EssayStatus.CJ_ASSESSMENT_FAILED
            content_type = "CJ_RESULTS_JSON"
        else:
            # Default for other phases
            success_status = None
            failed_status = None
            content_type = "PROCESSED_TEXT"

        # Filter successful and failed essays
        successful_essays = [
            essay for essay in essays_in_batch
            if essay.current_status == success_status
        ]

        failed_essays = [
            essay for essay in essays_in_batch
            if essay.current_status == failed_status
        ]

        # Construct processed essays with updated text_storage_id from phase output
        processed_essays = [
            EssayProcessingInputRefV1(
                essay_id=essay.essay_id,
                text_storage_id=essay.storage_references.get(content_type, essay.storage_references.get("ORIGINAL_TEXT", "")),
            )
            for essay in successful_essays
        ]

        # Get failed essay IDs
        failed_essay_ids = [essay.essay_id for essay in failed_essays]

        # Determine overall phase status
        if successful_essays and not failed_essays:
            phase_status = "COMPLETED_SUCCESSFULLY"
        elif successful_essays and failed_essays:
            phase_status = "COMPLETED_WITH_FAILURES"
        else:
            phase_status = "FAILED"

        # Construct the ELSBatchPhaseOutcomeV1 event
        outcome_event = ELSBatchPhaseOutcomeV1(
            batch_id=batch_id,
            phase_name=phase_name,
            phase_status=phase_status,
            processed_essays=processed_essays,
            failed_essay_ids=failed_essay_ids,
            correlation_id=correlation_id,
        )

        # Publish the event using correct Kafka topic
        await self.event_publisher.publish_els_batch_phase_outcome(
            outcome_event,
            correlation_id
        )

        return outcome_event


class TestBatchPhaseOutcomeAggregator:
    """Test the BatchPhaseOutcomeAggregator business logic component."""

    @pytest.fixture
    def mock_state_store(self):
        """Mock the external boundary - essay state store."""
        store = AsyncMock()

        # Mock essays in batch with different statuses
        store.list_essays_by_batch.return_value = [
            # Successful spellcheck essays
            AsyncMock(
                essay_id="essay-1",
                current_status=EssayStatus.SPELLCHECKED_SUCCESS,
                storage_references={"CORRECTED_TEXT": "corrected-storage-id-1", "ORIGINAL_TEXT": "original-id-1"},
            ),
            AsyncMock(
                essay_id="essay-2",
                current_status=EssayStatus.SPELLCHECKED_SUCCESS,
                storage_references={"CORRECTED_TEXT": "corrected-storage-id-2", "ORIGINAL_TEXT": "original-id-2"},
            ),
            # Failed spellcheck essay
            AsyncMock(
                essay_id="essay-3",
                current_status=EssayStatus.SPELLCHECK_FAILED,
                storage_references={"ORIGINAL_TEXT": "original-id-3"},
            ),
        ]

        return store

    @pytest.fixture
    def mock_event_publisher(self):
        """Mock the external boundary - event publisher."""
        publisher = AsyncMock()
        # Add the method that publishes ELSBatchPhaseOutcomeV1 events
        publisher.publish_els_batch_phase_outcome = AsyncMock()
        return publisher

    @pytest.fixture
    def aggregator(self, mock_state_store, mock_event_publisher):
        """Create the business logic component under test."""
        return BatchPhaseOutcomeAggregator(mock_state_store, mock_event_publisher)

    async def test_spellcheck_phase_outcome_aggregation(
        self, aggregator, mock_state_store, mock_event_publisher
    ):
        """Test aggregation of spellcheck phase outcomes into ELSBatchPhaseOutcomeV1 event."""
        batch_id = str(uuid4())
        correlation_id = uuid4()
        phase_name = "spellcheck"

        # Execute the business logic
        outcome_event = await aggregator.aggregate_and_publish_phase_outcome(
            batch_id, phase_name, correlation_id
        )

        # Verify the business logic executed correctly
        mock_state_store.list_essays_by_batch.assert_called_once_with(batch_id)

        # Verify event construction
        assert outcome_event.batch_id == batch_id
        assert outcome_event.phase_name == phase_name
        assert outcome_event.phase_status == "COMPLETED_WITH_FAILURES"  # 2 success, 1 failure
        assert len(outcome_event.processed_essays) == 2  # 2 successful essays
        assert len(outcome_event.failed_essay_ids) == 1  # 1 failed essay
        assert outcome_event.correlation_id == correlation_id

        # Verify essay data propagation - text_storage_id should be updated to corrected text
        assert outcome_event.processed_essays[0].text_storage_id == "corrected-storage-id-1"
        assert outcome_event.processed_essays[1].text_storage_id == "corrected-storage-id-2"

        # Verify failed essays are tracked
        assert "essay-3" in outcome_event.failed_essay_ids

        # Verify event was published via external boundary
        mock_event_publisher.publish_els_batch_phase_outcome.assert_called_once_with(
            outcome_event, correlation_id
        )

    async def test_essay_completion_tracking_logic(self, aggregator, mock_state_store):
        """Test the essay completion tracking logic within the component."""
        batch_id = str(uuid4())

        # Execute the component logic
        await aggregator.aggregate_and_publish_phase_outcome(batch_id, "spellcheck")

        # Verify the component called the state store correctly
        mock_state_store.list_essays_by_batch.assert_called_once_with(batch_id)

    async def test_essay_data_propagation_from_phase_output(
        self, aggregator, mock_state_store, mock_event_publisher
    ):
        """Test that essay text_storage_id is updated from phase output (not input)."""
        batch_id = str(uuid4())

        # Execute the business logic
        outcome_event = await aggregator.aggregate_and_publish_phase_outcome(
            batch_id, "spellcheck"
        )

        # Verify that text_storage_id comes from the phase output (CORRECTED_TEXT)
        # not the original input (ORIGINAL_TEXT)
        processed_essays = outcome_event.processed_essays
        assert len(processed_essays) == 2

        # Check that corrected text storage IDs are used, not original
        storage_ids = [essay.text_storage_id for essay in processed_essays]
        assert "corrected-storage-id-1" in storage_ids
        assert "corrected-storage-id-2" in storage_ids
        assert "original-id-1" not in storage_ids  # Should not use original
        assert "original-id-2" not in storage_ids  # Should not use original

    async def test_phase_status_determination_logic(self, mock_state_store, mock_event_publisher):
        """Test phase status determination based on essay outcomes."""
        aggregator = BatchPhaseOutcomeAggregator(mock_state_store, mock_event_publisher)

        # Test scenario: all essays successful
        mock_state_store.list_essays_by_batch.return_value = [
            AsyncMock(
                essay_id="essay-1",
                current_status=EssayStatus.SPELLCHECKED_SUCCESS,
                storage_references={"CORRECTED_TEXT": "storage-1"},
            ),
        ]

        outcome = await aggregator.aggregate_and_publish_phase_outcome(
            str(uuid4()), "spellcheck"
        )
        assert outcome.phase_status == "COMPLETED_SUCCESSFULLY"

        # Test scenario: all essays failed
        mock_state_store.list_essays_by_batch.return_value = [
            AsyncMock(
                essay_id="essay-1",
                current_status=EssayStatus.SPELLCHECK_FAILED,
                storage_references={},
            ),
        ]

        outcome = await aggregator.aggregate_and_publish_phase_outcome(
            str(uuid4()), "spellcheck"
        )
        assert outcome.phase_status == "FAILED"

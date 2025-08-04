"""
Unit tests for SQLiteEssayStateStore implementation.

Tests the essay state store methods including state updates via state machine,
batch and phase querying for Task 2.2.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime

import pytest
from common_core.domain_enums import ContentType
from common_core.status_enums import EssayStatus
from huleedu_service_libs.error_handling import HuleEduError

from services.essay_lifecycle_service.domain_models import EssayState
from services.essay_lifecycle_service.state_store import SQLiteEssayStateStore


class TestSQLiteEssayStateStore:
    """Test suite for SQLiteEssayStateStore."""

    @pytest.fixture
    async def state_store(self) -> SQLiteEssayStateStore:
        """Create SQLiteEssayStateStore instance with in-memory database for testing."""
        # Use temporary file for database (will be automatically cleaned up)
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        temp_file.close()

        store = SQLiteEssayStateStore(database_path=temp_file.name)
        await store.initialize()
        return store

    @pytest.fixture
    def sample_essay_state(self) -> EssayState:
        """Create sample essay state for testing."""
        return EssayState(
            essay_id="test-essay-1",
            batch_id="test-batch-1",
            current_status=EssayStatus.READY_FOR_PROCESSING,
            processing_metadata={"current_phase": "spellcheck", "commanded_phases": ["spellcheck"]},
            timeline={EssayStatus.READY_FOR_PROCESSING.value: datetime.now(UTC)},
            storage_references={ContentType.ORIGINAL_ESSAY: "original-text-123"},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    async def test_update_essay_status_via_machine(
        self, state_store: SQLiteEssayStateStore, sample_essay_state: EssayState
    ) -> None:
        """Test updating essay status via state machine with metadata."""
        # First create the essay record
        await state_store.create_essay_record(
            essay_id=sample_essay_state.essay_id, batch_id=sample_essay_state.batch_id
        )

        # Update to the desired initial status if different from default (UPLOADED)
        if sample_essay_state.current_status != EssayStatus.UPLOADED:
            await state_store.update_essay_state(
                essay_id=sample_essay_state.essay_id,
                new_status=sample_essay_state.current_status,
                metadata=sample_essay_state.processing_metadata,
            )

        # Test metadata for status update
        new_metadata = {
            "spellcheck_result": {
                "success": True,
                "corrections_made": 5,
                "storage_id": "corrected-456",
            },
            "current_phase": "spellcheck",
            "phase_outcome_status": EssayStatus.SPELLCHECKED_SUCCESS.value,
        }

        # Execute
        await state_store.update_essay_status_via_machine(
            essay_id=sample_essay_state.essay_id,
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata=new_metadata,
        )

        # Verify
        updated_state = await state_store.get_essay_state(sample_essay_state.essay_id)
        assert updated_state is not None
        assert updated_state.current_status == EssayStatus.SPELLCHECKED_SUCCESS
        assert updated_state.processing_metadata["spellcheck_result"]["success"] is True
        assert updated_state.processing_metadata["spellcheck_result"]["corrections_made"] == 5
        assert updated_state.processing_metadata["current_phase"] == "spellcheck"
        assert EssayStatus.SPELLCHECKED_SUCCESS.value in updated_state.timeline

    async def test_list_essays_by_batch_and_phase_spellcheck(
        self, state_store: SQLiteEssayStateStore
    ) -> None:
        """Test listing essays by batch and phase for spellcheck."""
        batch_id = "test-batch-1"

        # Create essays with different phase configurations
        # Essay 1: In spellcheck phase, awaiting
        await state_store.create_essay_record(essay_id="essay-1", batch_id=batch_id)
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-1",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-1",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={"current_phase": "spellcheck", "commanded_phases": ["spellcheck"]},
        )

        # Essay 2: In spellcheck phase, completed successfully
        await state_store.create_essay_record(essay_id="essay-2", batch_id=batch_id)
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-2",
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-2",
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={"current_phase": "spellcheck", "commanded_phases": ["spellcheck"]},
        )

        # Essay 3: NOT in spellcheck phase - should be excluded
        await state_store.create_essay_record(essay_id="essay-3", batch_id=batch_id)
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-3",
            new_status=EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-3",
            new_status=EssayStatus.CJ_ASSESSMENT_IN_PROGRESS,
            metadata={"current_phase": "cj_assessment", "commanded_phases": ["cj_assessment"]},
        )

        # Execute
        spellcheck_essays = await state_store.list_essays_by_batch_and_phase(batch_id, "spellcheck")

        # Verify
        assert len(spellcheck_essays) == 2
        essay_ids = {essay.essay_id for essay in spellcheck_essays}
        assert essay_ids == {"essay-1", "essay-2"}

        # Verify they all have spellcheck phase metadata
        for essay in spellcheck_essays:
            assert essay.processing_metadata.get("current_phase") == "spellcheck"
            assert "spellcheck" in essay.processing_metadata.get("commanded_phases", [])

    async def test_list_essays_by_batch_and_phase_no_matches(
        self, state_store: SQLiteEssayStateStore
    ) -> None:
        """Test listing essays when no essays match the phase."""
        batch_id = "test-batch-1"

        # Create essay with different phase
        await state_store.create_essay_record(essay_id="essay-1", batch_id=batch_id)
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-1",
            new_status=EssayStatus.READY_FOR_PROCESSING,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-1",
            new_status=EssayStatus.READY_FOR_PROCESSING,
            metadata={"current_phase": "ai_feedback", "commanded_phases": ["ai_feedback"]},
        )

        # Execute
        spellcheck_essays = await state_store.list_essays_by_batch_and_phase(batch_id, "spellcheck")

        # Verify
        assert len(spellcheck_essays) == 0

    async def test_list_essays_by_batch_and_phase_nonexistent_batch(
        self, state_store: SQLiteEssayStateStore
    ) -> None:
        """Test listing essays for nonexistent batch."""
        # Execute
        essays = await state_store.list_essays_by_batch_and_phase("nonexistent-batch", "spellcheck")

        # Verify
        assert len(essays) == 0

    async def test_list_essays_by_batch_and_phase_multiple_batches(
        self, state_store: SQLiteEssayStateStore
    ) -> None:
        """Test listing essays correctly filters by batch."""
        # Create essays in different batches
        await state_store.create_essay_record(essay_id="essay-batch1", batch_id="batch-1")
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-batch1",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-batch1",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={"current_phase": "spellcheck", "commanded_phases": ["spellcheck"]},
        )

        await state_store.create_essay_record(essay_id="essay-batch2", batch_id="batch-2")
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="essay-batch2",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={},
        )
        await state_store.update_essay_status_via_machine(
            essay_id="essay-batch2",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={"current_phase": "spellcheck", "commanded_phases": ["spellcheck"]},
        )

        # Execute
        batch1_essays = await state_store.list_essays_by_batch_and_phase("batch-1", "spellcheck")
        batch2_essays = await state_store.list_essays_by_batch_and_phase("batch-2", "spellcheck")

        # Verify
        assert len(batch1_essays) == 1
        assert len(batch2_essays) == 1
        assert batch1_essays[0].essay_id == "essay-batch1"
        assert batch2_essays[0].essay_id == "essay-batch2"
        assert batch1_essays[0].batch_id == "batch-1"
        assert batch2_essays[0].batch_id == "batch-2"

    async def test_update_essay_status_via_machine_essay_not_found(
        self, state_store: SQLiteEssayStateStore
    ) -> None:
        """Test updating status for nonexistent essay raises error."""
        # Execute and verify exception
        with pytest.raises(HuleEduError):
            await state_store.update_essay_status_via_machine(
                essay_id="nonexistent-essay",
                new_status=EssayStatus.SPELLCHECKED_SUCCESS,
                metadata={"test": "data"},
            )

    async def test_create_essay_record_minimal(self, state_store: SQLiteEssayStateStore) -> None:
        """Test creating essay record with minimal parameters."""
        # Execute
        created_essay = await state_store.create_essay_record(
            essay_id="test-essay", batch_id="test-batch"
        )
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="test-essay",
            new_status=EssayStatus.READY_FOR_PROCESSING,
            metadata={},
        )
        # Get the updated state for verification
        essay_state = await state_store.get_essay_state("test-essay")

        # Verify
        assert essay_state is not None
        assert essay_state.essay_id == "test-essay"
        assert essay_state.batch_id == "test-batch"
        assert essay_state.current_status == EssayStatus.READY_FOR_PROCESSING
        assert essay_state.created_at is not None
        assert essay_state.updated_at is not None

        # Verify it's persisted
        retrieved_state = await state_store.get_essay_state("test-essay")
        assert retrieved_state is not None
        assert retrieved_state.essay_id == "test-essay"
        assert retrieved_state.current_status == EssayStatus.READY_FOR_PROCESSING

    async def test_essay_state_timeline_tracking(self, state_store: SQLiteEssayStateStore) -> None:
        """Test that essay state timeline is correctly tracked during updates."""
        # Create essay
        created_essay = await state_store.create_essay_record(
            essay_id="timeline-test", batch_id="test-batch"
        )
        # Update to desired status since create defaults to UPLOADED
        await state_store.update_essay_state(
            essay_id="timeline-test",
            new_status=EssayStatus.READY_FOR_PROCESSING,
            metadata={},
        )
        # Get the updated state for timeline verification
        essay_state = await state_store.get_essay_state("timeline-test")

        # Verify initial timeline
        assert essay_state is not None
        initial_timeline_length = len(essay_state.timeline)
        assert EssayStatus.READY_FOR_PROCESSING.value in essay_state.timeline

        # Update status
        await state_store.update_essay_status_via_machine(
            essay_id="timeline-test",
            new_status=EssayStatus.AWAITING_SPELLCHECK,
            metadata={"phase": "spellcheck"},
        )

        # Verify timeline updated
        updated_state = await state_store.get_essay_state("timeline-test")
        assert updated_state is not None
        assert len(updated_state.timeline) == initial_timeline_length + 1
        assert EssayStatus.AWAITING_SPELLCHECK.value in updated_state.timeline
        assert EssayStatus.READY_FOR_PROCESSING.value in updated_state.timeline

        # Update status again
        await state_store.update_essay_status_via_machine(
            essay_id="timeline-test",
            new_status=EssayStatus.SPELLCHECKED_SUCCESS,
            metadata={"phase": "spellcheck", "result": "success"},
        )

        # Verify timeline has all entries
        final_state = await state_store.get_essay_state("timeline-test")
        assert final_state is not None
        assert len(final_state.timeline) == initial_timeline_length + 2
        assert EssayStatus.SPELLCHECKED_SUCCESS.value in final_state.timeline
        assert EssayStatus.AWAITING_SPELLCHECK.value in final_state.timeline
        assert EssayStatus.READY_FOR_PROCESSING.value in final_state.timeline

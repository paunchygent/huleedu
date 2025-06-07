"""Integration tests for Pipeline State Management in BOS.

Tests the dynamic pipeline orchestration logic using real business logic components.
Validates ProcessingPipelineState management, phase progression, and pipeline completion.

Following 070-testing-and-quality-assurance.mdc:
- Mock only external boundaries (event publisher, specialized service clients)
- Test real business logic components (PipelinePhaseCoordinator, repository operations)
- Limited scope component interactions (not full E2E)

INTEGRATION BOUNDARIES TESTED:
- Real DefaultPipelinePhaseCoordinator business logic
- Real ProcessingPipelineState management and persistence
- Real pipeline sequence determination and progression logic
- Real next-phase command generation logic
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)


class TestPipelineStateManagement:
    """Test pipeline state management using real BOS orchestration logic."""

    @pytest.fixture
    def mock_cj_initiator(self):
        """Mock the external boundary - CJ assessment initiator."""
        return AsyncMock()

    @pytest.fixture
    def batch_repository(self):
        """Create real batch repository for state management testing."""
        return MockBatchRepositoryImpl()

    @pytest.fixture
    def pipeline_coordinator(self, batch_repository, mock_cj_initiator):
        """Create real DefaultPipelinePhaseCoordinator with mocked external dependencies."""
        # Create phase initiators map with the mock CJ initiator
        phase_initiators_map = {
            PhaseName.CJ_ASSESSMENT: mock_cj_initiator,
            # Add other phases as needed for testing
        }
        return DefaultPipelinePhaseCoordinator(
            batch_repo=batch_repository,
            phase_initiators_map=phase_initiators_map,
        )

    async def test_spellcheck_to_cj_assessment_pipeline_progression(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """
        Test complete pipeline progression from spellcheck completion
        to CJ assessment initiation.
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=3,
            course_code="SV101",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=True,  # Critical: CJ assessment enabled
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state with spellcheck in progress
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "IN_PROGRESS",
            "cj_assessment_status": "PENDING",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck completion handling
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",  # Successful completion
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Verify CJ assessment was initiated (with None processed_essays since
        # no data propagation from spellcheck)
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=UUID(correlation_id),
            essays_for_processing=[],
            batch_context=batch_context,
        )

    async def test_pipeline_progression_with_cj_assessment_disabled(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """
        Test pipeline handling when CJ assessment is disabled.

        Should not initiate next phase.
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment disabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code="ENG201",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=False,  # Critical: CJ assessment disabled
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck"],  # CJ assessment disabled, only spellcheck
            "spellcheck_status": "IN_PROGRESS",
            "cj_assessment_status": "PENDING",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck completion handling
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Verify CJ assessment was NOT initiated (disabled)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_failed_phase_handling(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """Test pipeline handling when a phase fails - should not proceed to next phase."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code="SV101",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "IN_PROGRESS",
            "cj_assessment_status": "PENDING",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck failure handling
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="failed",  # Phase failed
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated to reflect failure
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "FAILED"

        # Verify CJ assessment was NOT initiated (previous phase failed)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_completed_with_failures_phase_handling(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """
        Test pipeline handling when a phase completes with partial failures.

        COMPLETED_WITH_FAILURES should allow progression to next phase as it indicates
        successful completion with some non-critical essay failures (per common_core/enums.py).
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=3,
            course_code="SV101",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "IN_PROGRESS",
            "cj_assessment_status": "PENDING",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck completion with partial failures
        # Simulate some essays succeeded, some failed (e.g., 2 of 3 essays processed successfully)
        processed_essays = [
            {"essay_id": "essay-1", "status": "success"},
            {"essay_id": "essay-2", "status": "success"}
        ]

        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_WITH_FAILURES",  # Partial success
            correlation_id=correlation_id,
            processed_essays_for_next_phase=processed_essays,  # 2 successful essays to proceed
        )

        # Verify pipeline state was updated to reflect partial completion
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"  # Updated status

        # CRITICAL: Verify CJ assessment WAS initiated (should proceed with successful essays)
        # This is the behavior we want after the fix
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=UUID(correlation_id),
            essays_for_processing=processed_essays,
            batch_context=batch_context,
        )

    async def test_idempotency_handling_for_already_initiated_phase(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """Test idempotency - already initiated phases should not be re-initiated."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code="SV101",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup pipeline state with CJ assessment already initiated
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "COMPLETED",
            "cj_assessment_status": "DISPATCH_INITIATED",  # Already initiated
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck completion handling (should be idempotent)
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated (spellcheck marked as completed)
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Verify CJ assessment was NOT re-initiated (idempotency)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_missing_batch_context_error_handling(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """Test error handling when batch context is missing."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup pipeline state without batch context
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck"],
            "spellcheck_status": "IN_PROGRESS",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test handling when batch context is missing
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id,
        )

        # Verify pipeline state was still updated
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Verify CJ assessment was not initiated (missing context)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_missing_pipeline_state_error_handling(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """Test error handling when pipeline state is missing."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context but no pipeline state
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code="SV101",
            class_designation="Test Class",
            teacher_name="Test Teacher",
            essay_instructions="Test essay instructions",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Test handling when pipeline state is missing (should not crash)
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id,
        )

        # Verify CJ assessment was not initiated (missing pipeline state)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_real_world_24_of_25_essays_scenario(
        self, pipeline_coordinator, batch_repository, mock_cj_initiator
    ):
        """
        Test the specific root cause scenario: 24/25 essays complete successfully,
        1 fails due to service issues (e.g., Content Service disconnection during storage).

        BOS should proceed with the 24 successful essays to CJ assessment.
        This tests the exact issue described in the user's root cause analysis.
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context for 25 essays with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=25,
            course_code="ENG101",
            class_designation="Real World Test",
            teacher_name="Test Teacher",
            essay_instructions="Write about the given topic",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "IN_PROGRESS",
            "cj_assessment_status": "PENDING",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Simulate 24 successful essays and 1 failed
        # (e.g., essay 8de29880-6ede-4d72-ae53-3b18b8d86d99)
        successful_essays = [
            {"essay_id": f"essay-{i:02d}", "text_storage_id": f"storage-{i:02d}",
             "status": "success"}
            for i in range(1, 25)  # 24 successful essays
        ]

        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_WITH_FAILURES",  # 24/25 succeeded, 1 failed
            correlation_id=correlation_id,
            processed_essays_for_next_phase=successful_essays,  # 24 essays proceed to CJ assessment
        )

        # Verify pipeline state reflects progression
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # CRITICAL: Verify CJ assessment was initiated with the 24 successful essays
        # This ensures that partial failures don't block the entire batch
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=UUID(correlation_id),
            essays_for_processing=successful_essays,  # All 24 successful essays proceed
            batch_context=batch_context,
        )

        # Verify we're proceeding with exactly 24 essays (not 25)
        call_args = mock_cj_initiator.initiate_phase.call_args
        essays_for_processing = call_args.kwargs["essays_for_processing"]
        assert len(essays_for_processing) == 24, (
            f"Expected 24 essays, got {len(essays_for_processing)}"
        )

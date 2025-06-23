"""Pipeline State Management integration tests - Failure handling scenarios.

Tests failure handling logic including complete failures and partial failures,
ensuring proper pipeline state management in error conditions.
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


class TestPipelineFailureHandling:
    """Test failure handling scenarios in pipeline state management."""

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

    async def test_failed_phase_handling(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
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
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
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
            {"essay_id": "essay-2", "status": "success"},
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

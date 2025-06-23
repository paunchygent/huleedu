"""Pipeline State Management integration tests - Edge cases and error handling.

Tests boundary conditions, idempotency, and error scenarios to ensure robust
pipeline state management under various edge cases.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from common_core.enums import CourseCode
from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)


class TestPipelineEdgeCases:
    """Test edge cases and error handling in pipeline state management."""

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

    async def test_idempotency_handling_for_already_initiated_phase(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """Test idempotency - already initiated phases should not be re-initiated."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code=CourseCode.SV1,
            essay_instructions="Test essay instructions",
            user_id="user_123",
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
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
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
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """Test error handling when pipeline state is missing."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context but no pipeline state
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=2,
            course_code=CourseCode.SV2,
            essay_instructions="Test essay instructions",
            user_id="user_123",
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

    async def test_single_essay_batch_handling(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """Test handling of a single essay batch."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context for single essay
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=1,
            course_code=CourseCode.ENG5,
            essay_instructions="Write a single test essay",
            user_id="user_single",
            enable_cj_assessment=False,  # CJ assessment requires multiple essays
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup pipeline state with spellcheck completed
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck"],
            "spellcheck_status": "COMPLETED",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test handling of single essay batch
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

        # Verify CJ assessment was not initiated (single essay batch)
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_large_batch_handling(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """Test handling of a large batch."""
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context for large batch
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=100,
            course_code=CourseCode.SV1,
            essay_instructions="Write a comprehensive essay",
            user_id="user_large_batch",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup pipeline state with spellcheck completed
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck"],
            "spellcheck_status": "COMPLETED",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test handling of large batch
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

        # Verify CJ assessment was not initiated (large batch)
        mock_cj_initiator.initiate_phase.assert_not_called()

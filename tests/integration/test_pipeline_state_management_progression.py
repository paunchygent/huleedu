"""Pipeline State Management integration tests - Progression scenarios.

Tests core pipeline progression logic including successful phase transitions
and conditional phase enablement/disablement.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from common_core.enums import BatchStatus, CourseCode
from common_core.pipeline_models import PhaseName
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)


class TestPipelineProgressionScenarios:
    """Test core pipeline progression scenarios using real BOS orchestration logic."""

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
            course_code=CourseCode.SV1,
            essay_instructions="Test essay instructions",
            user_id="user_123",
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
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,  # Successful completion
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

        # Setup batch context for CJ assessment
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=3,
            course_code=CourseCode.ENG6,
            essay_instructions="Analyze the given text",
            user_id="user_456",
            enable_cj_assessment=True,
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
            phase_status=BatchStatus.COMPLETED_SUCCESSFULLY,
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Verify CJ assessment was NOT initiated (disabled)
        mock_cj_initiator.initiate_phase.assert_not_called()

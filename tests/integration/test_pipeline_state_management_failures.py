"""Pipeline State Management integration tests - Failure scenarios.

Tests failure handling in pipeline state management, including
retry logic, error propagation, and recovery mechanisms.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from common_core.domain_enums import CourseCode
from common_core.pipeline_models import PhaseName
from common_core.status_enums import BatchStatus
from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.notification_service import (
    NotificationService,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)
from services.batch_orchestrator_service.implementations.pipeline_state_manager import (
    PipelineStateManager,
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
    def mock_redis_client(self) -> AsyncMock:
        """Mock the Redis client for UI notifications."""
        return AsyncMock()

    @pytest.fixture
    def pipeline_coordinator(self, batch_repository, mock_cj_initiator, mock_redis_client):
        """Create real DefaultPipelinePhaseCoordinator with mocked external dependencies."""
        # Create phase initiators map with the mock CJ initiator
        phase_initiators_map = {
            PhaseName.CJ_ASSESSMENT: mock_cj_initiator,
            # Add other phases as needed for testing
        }
        notification_service = NotificationService(mock_redis_client, batch_repository)
        state_manager = PipelineStateManager(batch_repository)
        return DefaultPipelinePhaseCoordinator(
            batch_repo=batch_repository,
            phase_initiators_map=phase_initiators_map,
            redis_client=mock_redis_client,
            notification_service=notification_service,
            state_manager=state_manager,
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
            course_code=CourseCode.SV3,
            essay_instructions="Test essay instructions",
            user_id="user_123",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "in_progress",
            "cj_assessment_status": "pending",
        }
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Test spellcheck failure handling
        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.FAILED_CRITICALLY,  # Phase failed
            correlation_id=correlation_id,
        )

        # Verify pipeline state was updated to reflect failure
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "failed"

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
        successful completion with some non-critical essay failures (per status_enums.py).
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=3,
            course_code=CourseCode.SV2,
            essay_instructions="Write a test essay",
            user_id="user_123",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "in_progress",
            "cj_assessment_status": "pending",
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
            completed_phase=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,  # Partial success
            correlation_id=correlation_id,
            processed_essays_for_next_phase=processed_essays,  # 2 successful essays to proceed
        )

        # Verify pipeline state was updated to reflect partial completion
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "completed_successfully"  # Updated status

        # CRITICAL: Verify CJ assessment WAS initiated (should proceed with successful essays)
        # This is the behavior we want after the fix
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=UUID(correlation_id),
            essays_for_processing=processed_essays,
            batch_context=batch_context,
        )

    async def test_completed_with_failures_phase_handling_with_course_code(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """
        Test pipeline handling when a phase completes with partial failures.

        COMPLETED_WITH_FAILURES should allow progression to next phase as it indicates
        successful completion with some non-critical essay failures (per status_enums.py).
        """
        batch_id = str(uuid4())
        correlation_id = str(uuid4())

        # Setup batch context for CJ assessment
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=5,
            course_code=CourseCode.ENG7,
            essay_instructions="Analyze the given text",
            user_id="user_456",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = {
            "batch_id": batch_id,
            "requested_pipelines": ["spellcheck", "cj_assessment"],
            "spellcheck_status": "in_progress",
            "cj_assessment_status": "pending",
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
            completed_phase=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,  # Partial success
            correlation_id=correlation_id,
            processed_essays_for_next_phase=processed_essays,  # 2 successful essays to proceed
        )

        # Verify pipeline state was updated to reflect partial completion
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state["spellcheck_status"] == "completed_successfully"  # Updated status

        # CRITICAL: Verify CJ assessment WAS initiated (should proceed with successful essays)
        # This is the behavior we want after the fix
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=UUID(correlation_id),
            essays_for_processing=processed_essays,
            batch_context=batch_context,
        )

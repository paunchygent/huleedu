"""Pipeline State Management integration tests - Real-world scenarios.

Tests complex real-world scenarios including partial batch failures and
specific edge cases that have been encountered in production.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.domain_enums import CourseCode
from common_core.pipeline_models import (
    PhaseName,
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)
from common_core.status_enums import BatchStatus

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.implementations.batch_pipeline_state_manager import (
    BatchPipelineStateManager,
)
from services.batch_orchestrator_service.implementations.batch_repository_impl import (
    MockBatchRepositoryImpl,
)
from services.batch_orchestrator_service.implementations.notification_service import (
    NotificationService,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)


class TestPipelineRealWorldScenarios:
    """Test real-world scenarios in pipeline state management."""

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
        mock_redis_client = AsyncMock()
        notification_service = NotificationService(mock_redis_client, batch_repository)
        # Create a mock state manager that delegates to batch repository
        mock_state_manager = AsyncMock(spec=BatchPipelineStateManager)
        mock_state_manager.save_processing_pipeline_state = (
            batch_repository.save_processing_pipeline_state
        )
        mock_state_manager.get_processing_pipeline_state = (
            batch_repository.get_processing_pipeline_state
        )

        # Mock the update_phase_status_atomically method to perform actual updates
        async def mock_update_phase_status(
            batch_id, phase_name, expected_status, new_status, **kwargs
        ):
            # Get current state
            state = await batch_repository.get_processing_pipeline_state(batch_id)
            if state:
                pipeline_detail = state.get_pipeline(phase_name.value)
                if pipeline_detail and pipeline_detail.status == expected_status:
                    pipeline_detail.status = new_status
                    await batch_repository.save_processing_pipeline_state(batch_id, state)
                    return True
            return False

        mock_state_manager.update_phase_status_atomically.side_effect = mock_update_phase_status
        # Mock the record_phase_failure method to always succeed
        mock_state_manager.record_phase_failure.return_value = True
        
        # Create mock event publisher
        mock_event_publisher = AsyncMock()
        mock_event_publisher.publish_batch_event = AsyncMock()
        
        return DefaultPipelinePhaseCoordinator(
            batch_repo=batch_repository,
            phase_initiators_map=phase_initiators_map,
            redis_client=mock_redis_client,
            notification_service=notification_service,
            state_manager=mock_state_manager,
            event_publisher=mock_event_publisher,
        )

    async def test_real_world_24_of_25_essays_scenario(
        self,
        pipeline_coordinator,
        batch_repository,
        mock_cj_initiator,
    ):
        """
        Test the specific root cause scenario: 24/25 essays complete successfully,
        1 fails due to service issues (e.g., Content Service disconnection during storage).

        BOS should proceed with the 24 successful essays to CJ assessment.
        This tests the exact issue described in the user's root cause analysis.
        """
        batch_id = str(uuid4())
        correlation_id = uuid4()

        # Setup batch context for 25 essays with CJ assessment enabled
        batch_context = BatchRegistrationRequestV1(
            expected_essay_count=25,
            course_code=CourseCode.ENG5,
            essay_instructions="Write about the given topic",
            user_id="user_123",
            enable_cj_assessment=True,
        )
        batch_repository.batch_contexts[batch_id] = batch_context

        # Setup initial pipeline state
        initial_pipeline_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
            cj_assessment=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
        )
        await batch_repository.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # Simulate 24 successful essays and 1 failed
        # (e.g., essay 8de29880-6ede-4d72-ae53-3b18b8d86d99)
        successful_essays = [
            {
                "essay_id": f"essay-{i:02d}",
                "text_storage_id": f"storage-{i:02d}",
                "status": "success",
            }
            for i in range(1, 25)  # 24 successful essays
        ]

        await pipeline_coordinator.handle_phase_concluded(
            batch_id=batch_id,
            completed_phase=PhaseName.SPELLCHECK,
            phase_status=BatchStatus.COMPLETED_WITH_FAILURES,  # 24/25 succeeded, 1 failed
            correlation_id=correlation_id,
            processed_essays_for_next_phase=successful_essays,  # 24 essays proceed to CJ assessment
        )

        # Verify pipeline state reflects progression
        updated_state = await batch_repository.get_processing_pipeline_state(batch_id)
        assert updated_state is not None
        assert updated_state.spellcheck.status == PipelineExecutionStatus.COMPLETED_SUCCESSFULLY

        # CRITICAL: Verify CJ assessment was initiated with the 24 successful essays
        # This ensures that partial failures don't block the entire batch
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=correlation_id,
            essays_for_processing=successful_essays,  # All 24 successful essays proceed
            batch_context=batch_context,
        )

        # Verify we're proceeding with exactly 24 essays (not 25)
        call_args = mock_cj_initiator.initiate_phase.call_args
        essays_for_processing = call_args.kwargs["essays_for_processing"]
        assert len(essays_for_processing) == 24, (
            f"Expected 24 essays, got {len(essays_for_processing)}"
        )

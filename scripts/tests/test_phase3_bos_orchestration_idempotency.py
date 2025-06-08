"""
Tests for BOS idempotency and edge case handling.

This module tests idempotent behavior for duplicate events and various edge cases
in the Batch Orchestrator Service (BOS).
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from common_core.pipeline_models import (
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)

# Import shared utilities
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)

# Import all fixtures from shared utilities
pytest_plugins = ("scripts.tests.test_phase3_bos_orchestration_utils",)

pytestmark = pytest.mark.asyncio


class TestBOSIdempotency:
    """Tests for BOS idempotency and edge case handling."""

    async def test_idempotency_in_phase_initiation(
        self,
        pipeline_phase_coordinator: DefaultPipelinePhaseCoordinator,
        mock_batch_repo: AsyncMock,
        mock_cj_initiator: AsyncMock,
        sample_batch_id: str,
        sample_correlation_id: uuid.UUID,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
    ) -> None:
        """
        Tests that a phase (e.g., CJ assessment) is not re-initiated if already processed,
        when a duplicate phase completion event (e.g., spellcheck completed) is received.
        """
        correlation_id_str = str(sample_correlation_id)

        # Initial state: spellcheck in progress, CJ pending
        initial_pipeline_state_dict = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
            cj_assessment=PipelineStateDetail(status=PipelineExecutionStatus.PENDING_DEPENDENCIES),
        ).model_dump()

        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = initial_pipeline_state_dict

        # First "spellcheck completed" event
        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id_str,
        )

        # CJ initiator should have been called once
        mock_cj_initiator.initiate_phase.assert_called_once()
        # Pipeline state should be updated to reflect CJ initiated
        # The coordinator makes multiple calls:
        # first for spellcheck completion, then for CJ initiation
        assert mock_batch_repo.save_processing_pipeline_state.call_count >= 2

        # Check the first call (spellcheck completion)
        first_update_args = mock_batch_repo.save_processing_pipeline_state.call_args_list[0].args[1]
        assert first_update_args.get("spellcheck_status") == "COMPLETED_SUCCESSFULLY"

        # Setup repo mock to return the state where CJ is already initiated
        state_after_first_cj_init = initial_pipeline_state_dict.copy()
        state_after_first_cj_init["spellcheck_status"] = "COMPLETED_SUCCESSFULLY"
        # BOS internal status
        state_after_first_cj_init["cj_assessment_status"] = "DISPATCH_INITIATED"

        mock_batch_repo.get_processing_pipeline_state.return_value = state_after_first_cj_init
        mock_cj_initiator.initiate_phase.reset_mock() # Reset for the next assertion


        # Second, duplicate "spellcheck completed" event
        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id_str + "_dup", # Different correlation for the event itself
        )

        # CJ initiator should NOT have been called again
        mock_cj_initiator.initiate_phase.assert_not_called()

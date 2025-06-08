"""
Tests for BOS phase coordination and event handling functionality.

This module tests phase outcome consumption, next phase determination, and
pipeline state updates in the Batch Orchestrator Service (BOS).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from common_core.pipeline_models import (
    PhaseName,
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)

# Import all fixtures from shared utilities
pytest_plugins = ("scripts.tests.test_phase3_bos_orchestration_utils",)

pytestmark = pytest.mark.asyncio


class TestBOSPhaseCoordination:
    """Tests for BOS phase coordination and event handling."""

    async def test_phase_outcome_consumption_and_next_phase_determination(
        self,
        pipeline_phase_coordinator: DefaultPipelinePhaseCoordinator,
        mock_batch_repo: AsyncMock,
        mock_cj_initiator: AsyncMock,
        sample_batch_id: str,
        sample_correlation_id: uuid.UUID,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
        sample_batch_registration_request_cj_disabled: BatchRegistrationRequestV1,
    ) -> None:
        """
        Tests that phase outcome events are consumed correctly and the next phase is determined.
        """
        correlation_id_str = str(sample_correlation_id)

        # Test case 1: CJ assessment enabled,
        # spellcheck completes -> CJ assessment should be triggered
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            ProcessingPipelineState(
                batch_id=sample_batch_id,
                requested_pipelines=["spellcheck", "cj_assessment"],
                spellcheck=PipelineStateDetail(
                    status=PipelineExecutionStatus.IN_PROGRESS
                ),
                cj_assessment=PipelineStateDetail(
                    status=PipelineExecutionStatus.PENDING_DEPENDENCIES
                ),
            ).model_dump()
        )

        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id_str,
        )

        # Should update spellcheck to completed
        mock_batch_repo.save_processing_pipeline_state.assert_called()
        spellcheck_update_args = (
            mock_batch_repo.save_processing_pipeline_state.call_args_list[0][0][1]
        )
        assert spellcheck_update_args["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Should initiate CJ assessment
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=sample_batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=sample_correlation_id,  # Expected as UUID object, not string
            essays_for_processing=[],  # Empty when no processed essays provided
            batch_context=sample_batch_registration_request_cj_enabled,
        )

        # Reset mocks for next test
        mock_batch_repo.reset_mock()
        mock_cj_initiator.reset_mock()

        # Test case 2: CJ assessment disabled,
        # spellcheck completes -> no CJ assessment should be triggered
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_disabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            ProcessingPipelineState(
                batch_id=sample_batch_id,
                requested_pipelines=["spellcheck"],
                spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
            ).model_dump()
        )

        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="COMPLETED_SUCCESSFULLY",
            correlation_id=correlation_id_str,
        )

        # Should update spellcheck to completed
        mock_batch_repo.save_processing_pipeline_state.assert_called()
        spellcheck_update_args = (
            mock_batch_repo.save_processing_pipeline_state.call_args_list[0][0][1]
        )
        assert spellcheck_update_args["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Should NOT initiate CJ assessment
        mock_cj_initiator.initiate_phase.assert_not_called()

    async def test_pipeline_state_updates_on_phase_status_change(
        self,
        pipeline_phase_coordinator: DefaultPipelinePhaseCoordinator,
        mock_batch_repo: AsyncMock,
        sample_batch_id: str,
    ) -> None:
        """
        Tests the direct update_phase_status method for pipeline state changes.
        """
        timestamp_now = datetime.now(timezone.utc).isoformat()
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            ProcessingPipelineState(
                batch_id=sample_batch_id,
                requested_pipelines=["spellcheck"]
            ).model_dump()
        )

        await pipeline_phase_coordinator.update_phase_status(
            batch_id=sample_batch_id,
            phase="spellcheck",
            status="COMPLETED",
            completion_timestamp=timestamp_now,
        )

        mock_batch_repo.save_processing_pipeline_state.assert_called_once()
        saved_state_args = mock_batch_repo.save_processing_pipeline_state.call_args[0][1]
        assert saved_state_args["spellcheck_status"] == "COMPLETED"
        assert saved_state_args["spellcheck_completed_at"] == timestamp_now

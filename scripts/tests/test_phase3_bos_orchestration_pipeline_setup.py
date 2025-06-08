"""
Tests for BOS pipeline setup and batch registration functionality.

This module tests the batch registration process and initial pipeline state setup
in the Batch Orchestrator Service (BOS).
"""

from __future__ import annotations

import uuid

import pytest

from common_core.pipeline_models import (
    PipelineExecutionStatus,
    ProcessingPipelineState,
)
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.implementations.batch_processing_service_impl import (
    BatchProcessingServiceImpl,
)

# Import all fixtures from shared utilities
pytest_plugins = ("scripts.tests.test_phase3_bos_orchestration_utils",)

pytestmark = pytest.mark.asyncio


class TestBOSPipelineSetup:
    """Tests for BOS pipeline setup and batch registration."""

    async def test_batch_registration_pipeline_setup(
        self,
        batch_processing_service: BatchProcessingServiceImpl,
        mock_batch_repo,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
        sample_batch_registration_request_cj_disabled: BatchRegistrationRequestV1,
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """
        Tests that batch registration correctly sets up the ProcessingPipelineState
        based on whether CJ assessment is enabled or disabled.
        """
        # Test case 1: CJ enabled
        batch_id_cj_enabled = await batch_processing_service.register_new_batch(
            sample_batch_registration_request_cj_enabled,
            sample_correlation_id,
        )

        # Check that batch context and pipeline state were stored
        mock_batch_repo.store_batch_context.assert_called()
        mock_batch_repo.save_processing_pipeline_state.assert_called()

        # Get the pipeline state that was saved for CJ enabled batch
        cj_enabled_args = mock_batch_repo.save_processing_pipeline_state.call_args_list[-1]
        cj_enabled_state = ProcessingPipelineState.model_validate(cj_enabled_args[0][1])

        # Should include CJ assessment in requested pipelines
        assert "cj_assessment" in cj_enabled_state.requested_pipelines
        assert "spellcheck" in cj_enabled_state.requested_pipelines
        assert cj_enabled_state.spellcheck is not None
        assert cj_enabled_state.spellcheck.status == PipelineExecutionStatus.PENDING_DEPENDENCIES
        assert cj_enabled_state.cj_assessment is not None
        assert cj_enabled_state.cj_assessment.status == PipelineExecutionStatus.PENDING_DEPENDENCIES

        # Reset mocks for next test
        mock_batch_repo.reset_mock()

        # Test case 2: CJ disabled
        batch_id_cj_disabled = await batch_processing_service.register_new_batch(
            sample_batch_registration_request_cj_disabled,
            sample_correlation_id,
        )

        # Check that batch context and pipeline state were stored
        mock_batch_repo.store_batch_context.assert_called()
        mock_batch_repo.save_processing_pipeline_state.assert_called()

        # Get the pipeline state that was saved for CJ disabled batch
        cj_disabled_args = mock_batch_repo.save_processing_pipeline_state.call_args_list[-1]
        cj_disabled_state = ProcessingPipelineState.model_validate(cj_disabled_args[0][1])

        # Should NOT include CJ assessment in requested pipelines
        assert "cj_assessment" not in cj_disabled_state.requested_pipelines
        assert "spellcheck" in cj_disabled_state.requested_pipelines
        assert cj_disabled_state.spellcheck is not None
        assert cj_disabled_state.spellcheck.status == PipelineExecutionStatus.PENDING_DEPENDENCIES

        # Different batch IDs should be generated
        assert batch_id_cj_enabled != batch_id_cj_disabled

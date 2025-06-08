"""
Tests for BOS command generation functionality.

This module tests command generation for various phases, specifically focusing
on CJ assessment command creation and validation.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from common_core.batch_service_models import (
    BatchServiceCJAssessmentInitiateCommandDataV1,
)
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import (
    EssayProcessingInputRefV1,
)
from common_core.pipeline_models import (
    PhaseName,
    ProcessingPipelineState,
)
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.implementations.cj_assessment_initiator_impl import (
    DefaultCJAssessmentInitiator,
)

# Import all fixtures from shared utilities
pytest_plugins = ("scripts.tests.test_phase3_bos_orchestration_utils",)

pytestmark = pytest.mark.asyncio


class TestBOSCommandGeneration:
    """Tests for BOS command generation functionality."""

    async def test_command_generation_for_cj_assessment(
        self,
        cj_assessment_initiator: DefaultCJAssessmentInitiator,
        mock_event_publisher: AsyncMock,
        mock_batch_repo: AsyncMock,
        sample_batch_id: str,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
        sample_correlation_id: uuid.UUID,
        sample_essay_refs: list[EssayProcessingInputRefV1],
    ) -> None:
        """
        Tests that DefaultCJAssessmentInitiator generates and publishes the correct command.
        """
        mock_batch_repo.get_processing_pipeline_state.return_value = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"],
        ).model_dump()  # Needed for _update_cj_assessment_status

        await cj_assessment_initiator.initiate_phase(
            batch_id=sample_batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_registration_request_cj_enabled,
        )

        mock_event_publisher.publish_batch_event.assert_called_once()
        published_envelope: EventEnvelope[BatchServiceCJAssessmentInitiateCommandDataV1] = (
            mock_event_publisher.publish_batch_event.call_args[0][0]
        )

        assert isinstance(published_envelope.data, BatchServiceCJAssessmentInitiateCommandDataV1)
        assert published_envelope.event_type == topic_name(
            ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND
        )
        assert published_envelope.data.entity_ref.entity_id == sample_batch_id
        assert published_envelope.data.language == "en"  # Inferred by initiator
        assert (
            published_envelope.data.course_code
            == sample_batch_registration_request_cj_enabled.course_code
        )
        assert (
            published_envelope.data.essay_instructions
            == sample_batch_registration_request_cj_enabled.essay_instructions
        )
        assert published_envelope.data.essays_to_process == sample_essay_refs

        # Verify that the CJ initiator no longer updates pipeline state
        # (this is now handled by the coordinator)
        mock_batch_repo.save_processing_pipeline_state.assert_not_called()

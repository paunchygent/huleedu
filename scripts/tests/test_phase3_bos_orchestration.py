"""
Unit tests for Phase 3 Batch Orchestrator Service (BOS) dynamic pipeline orchestration.

These tests validate the BOS's ability to:
- Define and manage processing pipeline sequences.
- Integrate pipeline setup with batch registration.
- Consume ELSBatchPhaseOutcomeV1 events for event-driven orchestration.
- Determine the next processing phase based on pipeline definition and current state.
- Generate appropriate commands for downstream services to initiate the next phase.
- Update and manage the ProcessingPipelineState accurately.
- Propagate essay lists and relevant data correctly between phases.
- Handle events idempotently.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

# Models from common_core
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
    PipelineExecutionStatus,
    PipelineStateDetail,
    ProcessingPipelineState,
)

# BOS specific models
from services.batch_orchestrator_service.api_models import (
    BatchRegistrationRequestV1,
)
from services.batch_orchestrator_service.config import (
    settings as bos_settings,
)

# BOS implementations and protocols
from services.batch_orchestrator_service.implementations.batch_processing_service_impl import (
    BatchProcessingServiceImpl,
)
from services.batch_orchestrator_service.implementations.cj_assessment_initiator_impl import (
    DefaultCJAssessmentInitiator,
)
from services.batch_orchestrator_service.implementations.pipeline_phase_coordinator_impl import (
    DefaultPipelinePhaseCoordinator,
)
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    CJAssessmentInitiatorProtocol,
    PipelinePhaseInitiatorProtocol,
)

# Pytest asyncio marker
pytestmark = pytest.mark.asyncio


@pytest.fixture
def sample_correlation_id() -> uuid.UUID:
    """Provides a sample correlation ID."""
    return uuid.uuid4()


@pytest.fixture
def sample_batch_id(sample_correlation_id: uuid.UUID) -> str:
    """Provides a sample batch ID, derived from correlation_id for consistency if needed."""
    # Or simply return str(uuid.uuid4()) if independent ID is preferred
    return str(sample_correlation_id)


@pytest.fixture
def mock_batch_repo() -> AsyncMock:
    """Mocks the BatchRepositoryProtocol."""
    mock = AsyncMock(spec=BatchRepositoryProtocol)
    mock.get_batch_context.return_value = None
    mock.get_processing_pipeline_state.return_value = None
    mock.store_batch_context = AsyncMock(return_value=True)
    mock.save_processing_pipeline_state = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_event_publisher() -> AsyncMock:
    """Mocks the BatchEventPublisherProtocol."""
    return AsyncMock(spec=BatchEventPublisherProtocol)


@pytest.fixture
def mock_cj_initiator() -> AsyncMock:
    """Mocks the CJAssessmentInitiatorProtocol."""
    mock = AsyncMock(spec=CJAssessmentInitiatorProtocol)
    mock.initiate_phase = AsyncMock()
    return mock


@pytest.fixture
def batch_processing_service(
    mock_batch_repo: AsyncMock,
    mock_event_publisher: AsyncMock,
) -> BatchProcessingServiceImpl:
    """Provides an instance of BatchProcessingServiceImpl with mocked dependencies."""
    return BatchProcessingServiceImpl(
        batch_repo=mock_batch_repo,
        event_publisher=mock_event_publisher,
        settings=bos_settings,
    )


@pytest.fixture
def pipeline_phase_coordinator(
    mock_batch_repo: AsyncMock,
    mock_cj_initiator: AsyncMock,
) -> DefaultPipelinePhaseCoordinator:
    """Provides an instance of DefaultPipelinePhaseCoordinator with mocked dependencies."""
    # Create mock phase_initiators_map for dynamic phase coordination
    mock_phase_initiators_map = {
        PhaseName.SPELLCHECK: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
        PhaseName.CJ_ASSESSMENT: mock_cj_initiator,
        PhaseName.AI_FEEDBACK: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
        PhaseName.NLP: AsyncMock(spec=PipelinePhaseInitiatorProtocol),
    }
    return DefaultPipelinePhaseCoordinator(
        batch_repo=mock_batch_repo, phase_initiators_map=mock_phase_initiators_map
    )


@pytest.fixture
def cj_assessment_initiator(
    mock_event_publisher: AsyncMock,
    mock_batch_repo: AsyncMock,
) -> DefaultCJAssessmentInitiator:
    """Provides an instance of DefaultCJAssessmentInitiator with mocked dependencies."""
    return DefaultCJAssessmentInitiator(
        event_publisher=mock_event_publisher, batch_repo=mock_batch_repo
    )


@pytest.fixture
def sample_batch_registration_request_cj_enabled() -> BatchRegistrationRequestV1:
    """Provides a sample BatchRegistrationRequestV1 with CJ assessment enabled."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code="ENG101",
        class_designation="Class A",
        teacher_name="Dr. Smith",
        essay_instructions="Write an essay on the impact of AI.",
        enable_cj_assessment=True,
        cj_default_llm_model="gpt-4o-mini",
        cj_default_temperature=0.5,
    )


@pytest.fixture
def sample_batch_registration_request_cj_disabled() -> BatchRegistrationRequestV1:
    """Provides a sample BatchRegistrationRequestV1 with CJ assessment disabled."""
    return BatchRegistrationRequestV1(
        expected_essay_count=2,
        course_code="SCI202",
        class_designation="Class B",
        teacher_name="Mr. Jones",
        essay_instructions="Submit your lab report on photosynthesis.",
        enable_cj_assessment=False,
    )


@pytest.fixture
def sample_essay_refs() -> list[EssayProcessingInputRefV1]:
    """Provides a list of sample EssayProcessingInputRefV1 objects."""
    return [
        EssayProcessingInputRefV1(
            essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())
        ),
        EssayProcessingInputRefV1(
            essay_id=str(uuid.uuid4()), text_storage_id=str(uuid.uuid4())
        ),
    ]


class TestBOSOrchestration:
    """Tests for Batch Orchestrator Service pipeline orchestration logic."""

    async def test_batch_registration_pipeline_setup(
        self,
        batch_processing_service: BatchProcessingServiceImpl,
        mock_batch_repo: AsyncMock,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
        sample_batch_registration_request_cj_disabled: BatchRegistrationRequestV1,
        sample_correlation_id: uuid.UUID,
    ) -> None:
        """
        Tests that batch registration correctly sets up the ProcessingPipelineState
        with the appropriate requested_pipelines.
        """
        # Scenario 1: CJ Assessment Enabled
        batch_id_cj_enabled = await batch_processing_service.register_new_batch(
            sample_batch_registration_request_cj_enabled, sample_correlation_id
        )

        # Find the call to save_processing_pipeline_state for this batch_id
        saved_state_cj_call = next(
            (
                call
                for call in mock_batch_repo.save_processing_pipeline_state.call_args_list
                if call.args[0] == batch_id_cj_enabled
            ),
            None,
        )
        assert saved_state_cj_call is not None
        saved_state_cj_enabled: ProcessingPipelineState = saved_state_cj_call.args[1]

        assert isinstance(saved_state_cj_enabled, ProcessingPipelineState)
        assert "spellcheck" in saved_state_cj_enabled.requested_pipelines
        assert "cj_assessment" in saved_state_cj_enabled.requested_pipelines
        assert saved_state_cj_enabled.batch_id == batch_id_cj_enabled

        # Reset mock for next scenario if necessary, or ensure calls are distinguishable
        mock_batch_repo.save_processing_pipeline_state.reset_mock()

        # Scenario 2: CJ Assessment Disabled
        batch_id_cj_disabled = await batch_processing_service.register_new_batch(
            sample_batch_registration_request_cj_disabled, sample_correlation_id
        )
        saved_state_no_cj_call = next(
            (
                call
                for call in mock_batch_repo.save_processing_pipeline_state.call_args_list
                if call.args[0] == batch_id_cj_disabled
            ),
            None,
        )
        assert saved_state_no_cj_call is not None
        saved_state_cj_disabled: ProcessingPipelineState = (
            saved_state_no_cj_call.args[1]
        )

        assert isinstance(saved_state_cj_disabled, ProcessingPipelineState)
        assert "spellcheck" in saved_state_cj_disabled.requested_pipelines
        assert "cj_assessment" not in saved_state_cj_disabled.requested_pipelines
        assert saved_state_cj_disabled.batch_id == batch_id_cj_disabled

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
        Tests consumption of ELSBatchPhaseOutcomeV1 and determination of the next phase.
        """
        correlation_id_str = str(sample_correlation_id)

        # Scenario 1: Spellcheck completes, CJ enabled
        initial_state_cj_enabled = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
            cj_assessment=PipelineStateDetail(status=PipelineExecutionStatus.REQUESTED_BY_USER),
        )
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            initial_state_cj_enabled.model_dump()
        )

        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="completed",
            correlation_id=correlation_id_str,
        )
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=sample_batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=correlation_id_str,
            essays_for_processing=[],  # Empty list when no processed essays provided
            batch_context=sample_batch_registration_request_cj_enabled,
        )
        # Check that pipeline state was updated for spellcheck completion
        # The coordinator makes multiple calls: first for spellcheck completion, then for CJ initiation
        assert mock_batch_repo.save_processing_pipeline_state.call_count >= 2

        # Check the first call (spellcheck completion)
        first_call_args = mock_batch_repo.save_processing_pipeline_state.call_args_list[0][0][1]
        assert first_call_args["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"

        # Check the second call (CJ initiation)
        second_call_args = mock_batch_repo.save_processing_pipeline_state.call_args_list[1][0][1]
        assert second_call_args["cj_assessment_status"] == "DISPATCH_INITIATED"

        mock_cj_initiator.initiate_phase.reset_mock()
        mock_batch_repo.save_processing_pipeline_state.reset_mock()

        # Scenario 2: Spellcheck completes, CJ disabled
        initial_state_cj_disabled = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck"],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
        )
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_disabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            initial_state_cj_disabled.model_dump()
        )

        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="completed",
            correlation_id=correlation_id_str,
        )
        mock_cj_initiator.initiate_phase.assert_not_called()
        saved_state_args_cj_disabled = (
            mock_batch_repo.save_processing_pipeline_state.call_args[0][1]
        )
        assert saved_state_args_cj_disabled["spellcheck_status"] == "COMPLETED_SUCCESSFULLY"
        # CJ assessment status not in pipeline state when disabled
        assert "cj_assessment_status" not in saved_state_args_cj_disabled

        mock_cj_initiator.initiate_phase.reset_mock()
        mock_batch_repo.save_processing_pipeline_state.reset_mock()

        # Scenario 3: Spellcheck fails
        initial_state_spellcheck_fails = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"], # CJ enabled to see if it's skipped
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
        )
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled # CJ enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            initial_state_spellcheck_fails.model_dump()
        )
        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="failed", # Phase failed
            correlation_id=correlation_id_str,
        )
        mock_cj_initiator.initiate_phase.assert_not_called()
        saved_state_args_spell_failed = (
            mock_batch_repo.save_processing_pipeline_state.call_args[0][1]
        )
        assert saved_state_args_spell_failed["spellcheck_status"] == "FAILED"


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
        correlation_id_str = str(sample_correlation_id)
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            ProcessingPipelineState(
                batch_id=sample_batch_id,
                requested_pipelines=["spellcheck", "cj_assessment"],
            ).model_dump()
        ) # Needed for _update_cj_assessment_status

        await cj_assessment_initiator.initiate_phase(
            batch_id=sample_batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=sample_correlation_id,
            essays_for_processing=sample_essay_refs,
            batch_context=sample_batch_registration_request_cj_enabled,
        )

        mock_event_publisher.publish_batch_event.assert_called_once()
        published_envelope: EventEnvelope[
            BatchServiceCJAssessmentInitiateCommandDataV1
        ] = mock_event_publisher.publish_batch_event.call_args[0][0]

        assert isinstance(
            published_envelope.data, BatchServiceCJAssessmentInitiateCommandDataV1
        )
        assert (
            published_envelope.event_type
            == topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND)
        )
        assert published_envelope.data.entity_ref.entity_id == sample_batch_id
        assert published_envelope.data.language == "en" # Inferred by initiator
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
        saved_state_args = mock_batch_repo.save_processing_pipeline_state.call_args[0][
            1
        ]
        assert saved_state_args["spellcheck_status"] == "COMPLETED"
        assert saved_state_args["spellcheck_completed_at"] == timestamp_now

    async def test_essay_list_propagation_to_next_phase_command(
        self,
        pipeline_phase_coordinator: DefaultPipelinePhaseCoordinator,
        mock_batch_repo: AsyncMock,
        mock_cj_initiator: AsyncMock,
        sample_batch_id: str,
        sample_correlation_id: uuid.UUID,
        sample_batch_registration_request_cj_enabled: BatchRegistrationRequestV1,
        sample_essay_refs: list[EssayProcessingInputRefV1],
    ) -> None:
        """
        Tests if processed_essays from ELSBatchPhaseOutcomeV1 are passed to the next phase command.
        Current BOS implementation does NOT pass these explicitly to the CJ initiator.
        """
        correlation_id_str = str(sample_correlation_id)
        initial_state = ProcessingPipelineState(
            batch_id=sample_batch_id,
            requested_pipelines=["spellcheck", "cj_assessment"],
            spellcheck=PipelineStateDetail(status=PipelineExecutionStatus.IN_PROGRESS),
        )
        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = (
            initial_state.model_dump()
        )

        # This outcome_event_data would come from ELS, containing processed essays
        # However, the current DefaultPipelinePhaseCoordinator doesn't use
        # outcome_event_data.processed_essays when calling the cj_initiator.
        # So, we don't need to construct the full event here.
        # We only care about the call to mock_cj_initiator.initiate_cj_assessment.

        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="completed", # This triggers next phase logic
            correlation_id=correlation_id_str,
        )

        # Assert that initiate_phase was called with correct parameters
        mock_cj_initiator.initiate_phase.assert_called_once_with(
            batch_id=sample_batch_id,
            phase_to_initiate=PhaseName.CJ_ASSESSMENT,
            correlation_id=correlation_id_str,
            essays_for_processing=[],  # Empty list when no processed essays provided
            batch_context=sample_batch_registration_request_cj_enabled,
        )

        # To further test the command generated by the initiator if essays_to_process was None:
        # We'd need to inspect the event_publisher mock from within a
        # DefaultCJAssessmentInitiator test.
        # This test focuses on what PipelinePhaseCoordinator passes.
        # If the design intent is for processed_essays to be passed, this reveals the gap.


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
            cj_assessment=PipelineStateDetail(status=PipelineExecutionStatus.REQUESTED_BY_USER),
        ).model_dump()

        mock_batch_repo.get_batch_context.return_value = (
            sample_batch_registration_request_cj_enabled
        )
        mock_batch_repo.get_processing_pipeline_state.return_value = initial_pipeline_state_dict

        # First "spellcheck completed" event
        await pipeline_phase_coordinator.handle_phase_concluded(
            batch_id=sample_batch_id,
            completed_phase="spellcheck",
            phase_status="completed",
            correlation_id=correlation_id_str,
        )

        # CJ initiator should have been called once
        mock_cj_initiator.initiate_phase.assert_called_once()
        # Pipeline state should be updated to reflect CJ initiated
        # The coordinator makes multiple calls: first for spellcheck completion, then for CJ initiation
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
            phase_status="completed",
            correlation_id=correlation_id_str + "_dup", # Different correlation for the event itself
        )

        # CJ initiator should NOT have been called again
        mock_cj_initiator.initiate_phase.assert_not_called()

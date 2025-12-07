"""Integration tests validating CJ metadata persistence and rehydration."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from common_core.events.cj_assessment_events import LLMConfigOverrides

from services.cj_assessment_service.cj_core_logic import comparison_processing
from services.cj_assessment_service.cj_core_logic.grade_projection.context_service import (
    ProjectionContextService,
)
from services.cj_assessment_service.cj_core_logic.grade_projection.projection_repository import (
    GradeProjectionRepository,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    FairComplementOrientationStrategy,
)
from services.cj_assessment_service.cj_core_logic.workflow_orchestrator import (
    run_cj_assessment_workflow,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.implementations.anchor_repository import (
    PostgreSQLAnchorRepository,
)
from services.cj_assessment_service.implementations.assessment_instruction_repository import (
    PostgreSQLAssessmentInstructionRepository,
)
from services.cj_assessment_service.implementations.essay_repository import (
    PostgreSQLCJEssayRepository,
)
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayToProcess,
)
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)


def _make_grade_projector(
    *,
    session_provider: SessionProviderProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    anchor_repository: AnchorRepositoryProtocol,
) -> GradeProjector:
    """Create a properly initialized GradeProjector for integration tests."""
    context_service = ProjectionContextService(
        session_provider=session_provider,
        instruction_repository=instruction_repository,
        anchor_repository=anchor_repository,
    )
    return GradeProjector(
        session_provider=session_provider,
        context_service=context_service,
        repository=GradeProjectionRepository(),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_original_request_metadata_persists_and_rehydrates(
    postgres_session_provider: SessionProviderProtocol,
    postgres_batch_repository: CJBatchRepositoryProtocol,
    postgres_essay_repository: PostgreSQLCJEssayRepository,
    postgres_instruction_repository: PostgreSQLAssessmentInstructionRepository,
    postgres_anchor_repository: PostgreSQLAnchorRepository,
    mock_content_client: ContentClientProtocol,
    mock_event_publisher: CJEventPublisherProtocol,
    mock_llm_interaction_async: LLMInteractionProtocol,
    mock_matching_strategy: MagicMock,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure original runner metadata is stored and reused during continuation."""

    test_settings.MAX_PAIRWISE_COMPARISONS = 500

    essays = [
        EssayToProcess(els_essay_id=f"essay-{i}", text_storage_id=f"storage-{i}") for i in range(4)
    ]

    request_data = CJAssessmentRequestData(
        bos_batch_id="batch-metadata-001",
        assignment_id="assignment-meta",
        essays_to_process=essays,
        language="en",
        course_code="ENG5",
        student_prompt_text="Prompt from runner",
        student_prompt_storage_id="prompt-storage",
        judge_rubric_text="Rubric from runner",
        judge_rubric_storage_id="rubric-storage",
        llm_config_overrides=LLMConfigOverrides(
            model_override="claude-3-sonnet",
            temperature_override=0.4,
            max_tokens_override=1500,
        ),
        batch_config_overrides={"batch_size": 12},
        max_comparisons_override=150,
        user_id="runner-user",
        org_id="runner-org",
    )

    correlation_id = uuid4()

    workflow_result = await run_cj_assessment_workflow(
        request_data=request_data,
        correlation_id=correlation_id,
        session_provider=postgres_session_provider,
        batch_repository=postgres_batch_repository,
        essay_repository=postgres_essay_repository,
        instruction_repository=postgres_instruction_repository,
        anchor_repository=postgres_anchor_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        content_client=mock_content_client,
        llm_interaction=mock_llm_interaction_async,
        event_publisher=mock_event_publisher,
        matching_strategy=mock_matching_strategy,
        grade_projector=_make_grade_projector(
            session_provider=postgres_session_provider,
            instruction_repository=postgres_instruction_repository,
            anchor_repository=postgres_anchor_repository,
        ),
        settings=test_settings,
        orientation_strategy=FairComplementOrientationStrategy(),
    )

    batch_id = int(workflow_result.batch_id)

    async with postgres_session_provider.session() as session:
        batch_upload = await session.get(CJBatchUpload, batch_id)
        assert batch_upload is not None
        assert batch_upload.processing_metadata is not None
        original_request = batch_upload.processing_metadata.get("original_request")
        assert original_request is not None
        assert original_request["max_comparisons_override"] == 150
        assert batch_upload.processing_metadata["student_prompt_text"] == "Prompt from runner"

        batch_state = await session.get(CJBatchState, batch_id)
        assert batch_state is not None
        assert batch_state.processing_metadata is not None
        assert batch_state.processing_metadata.get("original_request") == original_request

    submit_patch = AsyncMock(return_value=True)
    monkeypatch.setattr(
        comparison_processing,
        "submit_comparisons_for_async_processing",
        submit_patch,
    )

    state_metadata = batch_state.processing_metadata  # type: ignore[union-attr]
    continuation_log = {"cj_batch_id": batch_id, "phase": "continuation"}

    continuation_result = await comparison_processing.request_additional_comparisons_for_batch(
        cj_batch_id=batch_id,
        session_provider=postgres_session_provider,
        batch_repository=postgres_batch_repository,
        essay_repository=postgres_essay_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        llm_interaction=mock_llm_interaction_async,
        matching_strategy=mock_matching_strategy,
        orientation_strategy=FairComplementOrientationStrategy(),
        settings=test_settings,
        correlation_id=uuid4(),
        log_extra=continuation_log,
        llm_overrides_payload=state_metadata.get("llm_overrides"),
        config_overrides_payload=state_metadata.get("config_overrides"),
        original_request_payload=state_metadata.get("original_request"),
    )

    assert continuation_result is True
    submit_patch.assert_awaited_once()
    await_args = submit_patch.await_args
    assert await_args is not None
    request_args = await_args.kwargs["request_data"]
    assert request_args.max_comparisons_override == 150
    assert request_args.student_prompt_text == "Prompt from runner"
    assert request_args.llm_config_overrides is not None
    assert request_args.llm_config_overrides.model_override == "claude-3-sonnet"
    assert request_args.cj_request_type == "cj_retry"


@pytest.fixture
def mock_matching_strategy() -> MagicMock:
    """Provide real optimal graph matching strategy wrapped for protocol compliance."""

    return make_real_matching_strategy_mock()

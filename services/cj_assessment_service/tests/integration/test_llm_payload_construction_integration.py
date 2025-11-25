"""Integration tests for verifying LLM payload construction and prompts."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from aioresponses import aioresponses
from common_core.events.cj_assessment_events import LLMConfigOverrides
from sqlalchemy import select

from services.cj_assessment_service.cj_core_logic.comparison_processing import (
    submit_comparisons_for_async_processing,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
    EssayToProcess,
)
from services.cj_assessment_service.models_db import (
    AssessmentInstruction,
    CJBatchUpload,
    ComparisonPair,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.fixtures.database_fixtures import PostgresDataAccess

if TYPE_CHECKING:
    from .llm_payload_fixtures import CapturedRequestExtractor
else:  # pragma: no cover - runtime fallback for postponed evaluation
    CapturedRequestExtractor = Any

pytest_plugins = [
    "services.cj_assessment_service.tests.integration.llm_payload_fixtures",
]

DEFAULT_LANGUAGE = "en"
DEFAULT_COURSE_CODE = "ENG5"


@pytest.mark.asyncio
class TestLLMPayloadConstructionIntegration:
    async def test_user_prompt_contains_formatted_essays(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Ensure essays appear in the user prompt with IDs and content."""

        log_label = "formatted-essays"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
        )
        essays = _build_mock_essays("formatted")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        user_prompt = http_request["user_prompt"]
        assert f"**Essay A (ID: {essays[0].id}):**" in user_prompt
        assert essays[0].text_content in user_prompt
        assert f"**Essay B (ID: {essays[1].id}):**" in user_prompt
        assert essays[1].text_content in user_prompt
        assert "prompt_blocks" in http_request
        assert len(http_request["prompt_blocks"]) == 3  # essay A, essay B, instructions

    async def test_user_prompt_with_full_assessment_context(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Verify instructions, rubric, and student prompt are included when stored."""

        instructions = "Mock teacher instructions for testing."
        rubric = "Mock rubric criteria for testing."
        student_prompt = "Mock student assignment prompt."
        assignment_id = f"assignment-{uuid.uuid4()}"

        log_label = "full-context"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            assignment_id=assignment_id,
            teacher_instructions=instructions,
            judge_rubric=rubric,
            student_prompt=student_prompt,
            label=log_label,
        )
        essays = _build_mock_essays("full-context")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        user_prompt = http_request["user_prompt"]
        assert "**Student Assignment:**" in user_prompt
        assert student_prompt in user_prompt
        assert "**Assessment Criteria:**" in user_prompt
        assert instructions in user_prompt
        assert "**Judge Instructions:**" in user_prompt
        assert rubric in user_prompt
        assert "prompt_blocks" in http_request
        assert http_request["prompt_blocks"][0]["cacheable"] is True
        assert http_request["prompt_blocks"][0]["ttl"] == "5m"

    async def test_user_prompt_with_partial_context(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Ensure only available rubric context is included."""

        rubric = "Only rubric text should appear in the prompt."
        log_label = "partial-context"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            judge_rubric=rubric,
            label=log_label,
        )
        essays = _build_mock_essays("partial-context")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        user_prompt = http_request["user_prompt"]
        assert rubric in user_prompt
        assert "**Judge Instructions:**" in user_prompt
        assert "**Student Assignment:**" not in user_prompt
        assert "**Assessment Criteria:**" not in user_prompt
        assert len(http_request["prompt_blocks"]) == 4  # rubric block + essays + instructions

    async def test_user_prompt_without_assessment_context(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Prompt should fall back to essays plus comparison guidance when no context exists."""

        log_label = "no-context"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
        )
        essays = _build_mock_essays("no-context")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        user_prompt = http_request["user_prompt"]
        assert "**Student Assignment:**" not in user_prompt
        assert "**Assessment Criteria:**" not in user_prompt
        assert "**Judge Instructions:**" not in user_prompt
        assert "determine which essay better fulfills the requirements" in user_prompt
        assert len(http_request["prompt_blocks"]) == 3

    async def test_user_prompt_matches_blocks_joined_text(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Ensure the rendered string matches concatenated prompt blocks."""

        log_label = "block-parity"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
            teacher_instructions="Assess clarity",
            judge_rubric="Rubric text",
            student_prompt="Student assignment text",
        )
        essays = _build_mock_essays("block-parity")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        blocks = http_request["prompt_blocks"]
        rendered = "\n\n".join(block["content"] for block in blocks)
        assert http_request["user_prompt"] == rendered

    async def test_complete_http_payload_structure(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Validate all required HTTP payload fields are populated."""

        log_label = "payload-structure"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
        )
        essays = _build_mock_essays("payload-structure")

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
        )

        assert http_request["user_prompt"]

        llm_config = http_request["llm_config_overrides"]
        assert llm_config["provider_override"] == test_settings.DEFAULT_LLM_PROVIDER.value
        assert llm_config["model_override"] == test_settings.DEFAULT_LLM_MODEL
        assert llm_config["temperature_override"] == test_settings.DEFAULT_LLM_TEMPERATURE
        assert llm_config.get("max_tokens_override") is None
        assert llm_config["system_prompt_override"] == test_settings.SYSTEM_PROMPT

        metadata = http_request["metadata"]
        assert metadata["essay_a_id"] == essays[0].id
        assert metadata["essay_b_id"] == essays[1].id
        assert metadata["bos_batch_id"] == bos_batch_id

        assert http_request["callback_topic"] == test_settings.LLM_PROVIDER_CALLBACK_TOPIC
        assert isinstance(http_request["correlation_id"], str)

    async def test_eng5_overrides_reach_llm_provider(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """ENG5 runner overrides propagate unchanged through CJ → LPS."""

        log_label = "eng5-overrides"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
        )
        essays = _build_mock_essays(log_label)
        overrides = LLMConfigOverrides(
            provider_override="anthropic",
            model_override="claude-haiku-4-5-20251001",
            temperature_override=0.35,
            max_tokens_override=2048,
            system_prompt_override="ENG5 custom system prompt",
        )

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            log_label=log_label,
            llm_overrides=overrides,
        )

        llm_config = http_request["llm_config_overrides"]
        assert llm_config == {
            "provider_override": "anthropic",
            "model_override": "claude-haiku-4-5-20251001",
            "temperature_override": 0.35,
            "max_tokens_override": 2048,
            "system_prompt_override": "ENG5 custom system prompt",
        }

    async def test_metadata_correlation_id_flow(
        self,
        postgres_session_provider: SessionProviderProtocol,
        postgres_repository: PostgresDataAccess,
        postgres_batch_repository: CJBatchRepositoryProtocol,
        real_llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
        capture_requests_from_mocker: CapturedRequestExtractor,
        test_settings: Settings,
    ) -> None:
        """Ensure tracking-map correlation IDs match HTTP request payloads and DB records."""

        log_label = "correlation-flow"
        cj_batch_id, bos_batch_id = await _create_batch_with_context(
            postgres_repository,
            label=log_label,
        )
        essays = _build_mock_essays("correlation-flow")
        explicit_correlation_id = uuid.uuid4()

        http_request = await _submit_and_capture_request(
            postgres_session_provider=postgres_session_provider,
            postgres_repository=postgres_repository,
            postgres_batch_repository=postgres_batch_repository,
            llm_interaction=real_llm_interaction,
            capture_requests_from_mocker=capture_requests_from_mocker,
            test_settings=test_settings,
            essays=essays,
            cj_batch_id=cj_batch_id,
            bos_batch_id=bos_batch_id,
            correlation_id=explicit_correlation_id,
            log_label=log_label,
        )

        async with postgres_repository.session() as session:
            result = await session.execute(
                select(ComparisonPair).where(ComparisonPair.cj_batch_id == cj_batch_id)
            )
            comparison_pair = result.scalars().one()

        assert http_request["correlation_id"] == str(comparison_pair.request_correlation_id)
        assert comparison_pair.request_correlation_id is not None
        metadata = http_request["metadata"]
        assert metadata["essay_a_id"] == comparison_pair.essay_a_els_id
        assert metadata["essay_b_id"] == comparison_pair.essay_b_els_id
        assert comparison_pair.prompt_text == http_request["user_prompt"]


def _build_mock_essays(tag: str) -> list[EssayForComparison]:
    """Create deterministic essay objects for testing."""

    return [
        EssayForComparison(
            id=f"{tag}-essay-a",
            text_content="Mock essay A content for testing prompt construction.",
            current_bt_score=0.0,
        ),
        EssayForComparison(
            id=f"{tag}-essay-b",
            text_content="Mock essay B content for testing prompt construction.",
            current_bt_score=0.0,
        ),
    ]


async def _create_batch_with_context(
    repository: PostgresDataAccess,
    *,
    assignment_id: str | None = None,
    teacher_instructions: str | None = None,
    student_prompt: str | None = None,
    judge_rubric: str | None = None,
    label: str = "batch-context",
) -> tuple[int, str]:
    """Create a CJ batch with optional assignment context persisted."""

    bos_batch_id = str(uuid.uuid4())
    batch_assignment_id = assignment_id or (teacher_instructions and f"assignment-{uuid.uuid4()}")
    metadata: dict[str, Any] = {}
    if student_prompt:
        metadata["student_prompt_text"] = student_prompt
    if judge_rubric:
        metadata["judge_rubric_text"] = judge_rubric
    if batch_assignment_id:
        metadata["assignment_id"] = batch_assignment_id

    async with repository.session() as session:
        batch = await repository.create_new_cj_batch(
            session=session,
            bos_batch_id=bos_batch_id,
            event_correlation_id=str(uuid.uuid4()),
            language=DEFAULT_LANGUAGE,
            course_code=DEFAULT_COURSE_CODE,
            initial_status=CJBatchStatusEnum.PENDING,
            expected_essay_count=2,
        )

        if batch_assignment_id:
            batch.assignment_id = batch_assignment_id
        if metadata:
            batch.processing_metadata = metadata
        if teacher_instructions and batch_assignment_id:
            await repository.upsert_assessment_instruction(
                session=session,
                assignment_id=batch_assignment_id,
                course_id=None,
                instructions_text=teacher_instructions,
                grade_scale=DEFAULT_COURSE_CODE,
                student_prompt_storage_id=None,
                judge_rubric_storage_id=None,
            )

        await session.commit()

    created_batch_id = batch.id

    await _print_context_records(
        repository=repository,
        cj_batch_id=created_batch_id,
        assignment_id=batch_assignment_id,
        label=label,
    )
    return created_batch_id, bos_batch_id


async def _persist_essays(
    repository: PostgresDataAccess,
    cj_batch_id: int,
    essays: list[EssayForComparison],
) -> None:
    """Store essays in the database so pair generation can proceed."""

    async with repository.session() as session:
        for essay in essays:
            await repository.create_or_update_cj_processed_essay(
                session=session,
                cj_batch_id=cj_batch_id,
                els_essay_id=essay.id,
                text_storage_id=f"storage-{essay.id}",
                assessment_input_text=essay.text_content,
            )
        await session.commit()


async def _submit_and_capture_request(
    *,
    postgres_session_provider: SessionProviderProtocol,
    postgres_repository: PostgresDataAccess,
    postgres_batch_repository: CJBatchRepositoryProtocol,
    llm_interaction: tuple[LLMInteractionProtocol, aioresponses],
    capture_requests_from_mocker: CapturedRequestExtractor,
    test_settings: Settings,
    essays: list[EssayForComparison],
    cj_batch_id: int,
    bos_batch_id: str,
    log_label: str,
    correlation_id: UUID | None = None,
    llm_overrides: LLMConfigOverrides | None = None,
) -> dict[str, Any]:
    """Submit comparisons and return the captured HTTP request body."""

    llm_interaction_impl, http_mocker = llm_interaction
    await _persist_essays(postgres_repository, cj_batch_id, essays)

    request_data = CJAssessmentRequestData(
        bos_batch_id=bos_batch_id,
        assignment_id="test-assign",
        essays_to_process=[
            EssayToProcess(els_essay_id=essay.id, text_storage_id=f"storage-{essay.id}")
            for essay in essays
        ],
        language=DEFAULT_LANGUAGE,
        course_code=DEFAULT_COURSE_CODE,
        llm_config_overrides=llm_overrides,
    )

    await submit_comparisons_for_async_processing(
        essays_for_api_model=essays,
        cj_batch_id=cj_batch_id,
        session_provider=postgres_session_provider,
        batch_repository=postgres_batch_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        request_data=request_data,
        llm_interaction=llm_interaction_impl,
        settings=test_settings,
        correlation_id=correlation_id or uuid.uuid4(),
        log_extra={"test": log_label},
    )

    captured_http_requests = capture_requests_from_mocker(http_mocker)
    assert captured_http_requests, "No HTTP requests captured"
    request_body = captured_http_requests[0]
    _print_prompt(log_label, request_body["user_prompt"])
    return request_body


def _print_prompt(label: str, prompt: str) -> None:
    """Print the generated prompt for debugging visibility."""

    print(f"\n===== {label} user prompt =====\n{prompt}\n===== end user prompt =====\n")


async def _print_context_records(
    *,
    repository: PostgresDataAccess,
    cj_batch_id: int,
    assignment_id: str | None,
    label: str,
) -> None:
    """Log the batch metadata and assessment instruction rows backing the prompt."""

    async with repository.session() as session:
        batch = await session.get(CJBatchUpload, cj_batch_id)
        if batch:
            batch_summary = {
                "cj_batch_id": batch.id,
                "bos_batch_id": batch.bos_batch_id,
                "assignment_id": batch.assignment_id,
                "processing_metadata": batch.processing_metadata,
            }
            print(
                "\n====="
                f" {label} batch record =====\n"
                f"{json.dumps(batch_summary, indent=2)}\n"
                "===== end batch record =====\n"
            )

        if assignment_id:
            stmt = select(AssessmentInstruction).where(
                AssessmentInstruction.assignment_id == assignment_id
            )
            result = await session.execute(stmt)
            instruction = result.scalar_one_or_none()
            if instruction:
                instruction_summary = {
                    "assignment_id": instruction.assignment_id,
                    "grade_scale": instruction.grade_scale,
                    "instructions_text": instruction.instructions_text,
                }
                print(
                    "\n====="
                    f" {label} assessment instruction =====\n"
                    f"{json.dumps(instruction_summary, indent=2)}\n"
                    "===== end assessment instruction =====\n"
                )

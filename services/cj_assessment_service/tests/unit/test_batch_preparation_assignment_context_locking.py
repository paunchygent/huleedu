"""Unit tests for assignment-owned prompt/rubric semantics in batch preparation."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.events.cj_assessment_events import LLMConfigOverrides
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_preparation import create_cj_batch
from services.cj_assessment_service.models_api import CJAssessmentRequestData, EssayToProcess
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    ContentClientProtocol,
    SessionProviderProtocol,
)


@pytest.mark.asyncio
async def test_create_cj_batch_requires_instruction_for_assignment_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_repository = AsyncMock()
    instruction_repository = AsyncMock()
    instruction_repository.get_assessment_instruction.return_value = None
    content_client = AsyncMock(spec=ContentClientProtocol)

    mock_batch = Mock(spec=CJBatchUpload)
    mock_batch.id = 123
    mock_batch.processing_metadata = {}
    mock_batch.assignment_id = None
    batch_repository.create_new_cj_batch.return_value = mock_batch

    session = AsyncMock(spec=AsyncSession)

    class Provider(AsyncMock, SessionProviderProtocol):  # type: ignore[misc]
        @asynccontextmanager
        async def session(self) -> AsyncGenerator[AsyncSession, None]:
            yield session

    session_provider = Provider()

    # Avoid side effects after the exception (metadata merge should not be reached).
    monkeypatch.setattr(
        "services.cj_assessment_service.cj_core_logic.batch_preparation.merge_batch_upload_metadata",
        AsyncMock(),
    )

    request_data = CJAssessmentRequestData(
        bos_batch_id="bos-1",
        assignment_id="assignment-missing",
        language="en",
        course_code="ENG5",
        essays_to_process=[EssayToProcess(els_essay_id="e1", text_storage_id="s1")],
        user_id="user-1",
        org_id=None,
    )

    with pytest.raises(ValueError, match="Unknown assignment_id 'assignment-missing'"):
        await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=session_provider,
            batch_repository=batch_repository,
            instruction_repository=instruction_repository,
            content_client=content_client,
            log_extra={},
        )


@pytest.mark.asyncio
async def test_create_cj_batch_rejects_judge_rubric_override_for_canonical_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_repository = AsyncMock()
    instruction_repository = AsyncMock()
    content_client = AsyncMock(spec=ContentClientProtocol)

    mock_batch = Mock(spec=CJBatchUpload)
    mock_batch.id = 555
    mock_batch.processing_metadata = {}
    mock_batch.assignment_id = None
    batch_repository.create_new_cj_batch.return_value = mock_batch

    instruction_repository.get_assessment_instruction.return_value = SimpleNamespace(
        student_prompt_storage_id="prompt-from-instruction",
        judge_rubric_storage_id="rubric-from-instruction",
        context_origin="canonical_national",
    )

    content_client.fetch_content = AsyncMock(
        side_effect=["Prompt text from instruction", "Rubric text from instruction"]
    )

    session = AsyncMock(spec=AsyncSession)

    class Provider(AsyncMock, SessionProviderProtocol):  # type: ignore[misc]
        @asynccontextmanager
        async def session(self) -> AsyncGenerator[AsyncSession, None]:
            yield session

    session_provider = Provider()

    # Avoid side effects after the exception (metadata merge should not be reached).
    monkeypatch.setattr(
        "services.cj_assessment_service.cj_core_logic.batch_preparation.merge_batch_upload_metadata",
        AsyncMock(),
    )

    request_data = CJAssessmentRequestData(
        bos_batch_id="bos-2",
        assignment_id="assignment-locked",
        language="en",
        course_code="ENG5",
        essays_to_process=[EssayToProcess(els_essay_id="e1", text_storage_id="s1")],
        student_prompt_storage_id="prompt-from-event",
        student_prompt_text="Prompt text from event",
        judge_rubric_storage_id="rubric-from-event",
        judge_rubric_text="Rubric text from event",
        llm_config_overrides=LLMConfigOverrides(judge_rubric_override="OVERRIDE"),
        user_id="user-2",
        org_id=None,
    )

    with pytest.raises(ValueError, match="judge_rubric_override is not allowed"):
        await create_cj_batch(
            request_data=request_data,
            correlation_id=uuid4(),
            session_provider=session_provider,
            batch_repository=batch_repository,
            instruction_repository=instruction_repository,
            content_client=content_client,
            log_extra={},
        )


@pytest.mark.asyncio
async def test_create_cj_batch_allows_judge_rubric_override_for_non_canonical_assignment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    batch_repository = AsyncMock()
    instruction_repository = AsyncMock()
    content_client = AsyncMock(spec=ContentClientProtocol)

    mock_batch = Mock(spec=CJBatchUpload)
    mock_batch.id = 777
    mock_batch.processing_metadata = {}
    mock_batch.assignment_id = None
    batch_repository.create_new_cj_batch.return_value = mock_batch

    instruction_repository.get_assessment_instruction.return_value = SimpleNamespace(
        student_prompt_storage_id="prompt-from-instruction",
        judge_rubric_storage_id="rubric-from-instruction",
        context_origin="research_experiment",
    )

    content_client.fetch_content = AsyncMock(side_effect=["Prompt text from instruction"])

    session = AsyncMock(spec=AsyncSession)

    class Provider(AsyncMock, SessionProviderProtocol):  # type: ignore[misc]
        @asynccontextmanager
        async def session(self) -> AsyncGenerator[AsyncSession, None]:
            yield session

    session_provider = Provider()

    captured: dict[str, object] = {}

    async def fake_merge_batch_upload_metadata(
        *,
        session_provider: SessionProviderProtocol,
        cj_batch_id: int,
        metadata_updates: dict,
        correlation_id: object,
    ) -> None:
        captured["cj_batch_id"] = cj_batch_id
        captured["metadata_updates"] = metadata_updates

    monkeypatch.setattr(
        "services.cj_assessment_service.cj_core_logic.batch_preparation.merge_batch_upload_metadata",
        fake_merge_batch_upload_metadata,
    )

    request_data = CJAssessmentRequestData(
        bos_batch_id="bos-3",
        assignment_id="assignment-experiment",
        language="en",
        course_code="ENG5",
        essays_to_process=[EssayToProcess(els_essay_id="e1", text_storage_id="s1")],
        llm_config_overrides=LLMConfigOverrides(judge_rubric_override="OVERRIDE RUBRIC"),
        user_id="user-3",
        org_id=None,
    )

    result = await create_cj_batch(
        request_data=request_data,
        correlation_id=uuid4(),
        session_provider=session_provider,
        batch_repository=batch_repository,
        instruction_repository=instruction_repository,
        content_client=content_client,
        log_extra={},
    )
    assert result == 777

    metadata_updates = captured["metadata_updates"]
    assert isinstance(metadata_updates, dict)

    assert metadata_updates["student_prompt_storage_id"] == "prompt-from-instruction"
    assert metadata_updates["student_prompt_text"] == "Prompt text from instruction"
    assert metadata_updates["judge_rubric_text"] == "OVERRIDE RUBRIC"
    assert "judge_rubric_storage_id" not in metadata_updates

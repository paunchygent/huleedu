"""Unit tests for comparison_processing helper utilities.

Covers per-request budget helpers and continuation submission logic.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic import comparison_processing as cp
from services.cj_assessment_service.cj_core_logic.batch_config import BatchConfigOverrides
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import (
    CJAssessmentRequestData,
    EssayForComparison,
    EssayToProcess,
)


@pytest.mark.parametrize(
    "settings_cap,override,expected",
    [
        (100, 50, 50),  # override smaller than cap
        (100, 250, 100),  # override capped by service default
        (100, None, 100),  # no override -> service default
        (None, 200, 200),  # service uncapped -> honor override
        (80, "not-an-int", 80),  # invalid override -> default
    ],
)
def test_resolve_requested_max_pairs(
    settings_cap: int | None,
    override: int | str | None,
    expected: int,
) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = settings_cap
    request_data = CJAssessmentRequestData(
        bos_batch_id="test-batch",
        assignment_id="test-assign",
        essays_to_process=[EssayToProcess(els_essay_id="essay1", text_storage_id="storage1")],
        language="en",
        course_code="ENG5",
        max_comparisons_override=override if isinstance(override, int) else None,
    )

    assert cp._resolve_requested_max_pairs(settings, request_data) == expected


def test_build_budget_metadata_with_overrides() -> None:
    overrides = BatchConfigOverrides(batch_size=25)

    metadata = cp._build_budget_metadata(
        max_pairs_cap=120,
        source="runner_override",
        batch_config_overrides=overrides,
    )

    assert metadata["comparison_budget"] == {
        "max_pairs_requested": 120,
        "source": "runner_override",
    }
    assert metadata["config_overrides"] == overrides.model_dump(exclude_none=True)


def test_build_budget_metadata_without_overrides() -> None:
    metadata = cp._build_budget_metadata(
        max_pairs_cap=90,
        source="service_default",
        batch_config_overrides=None,
    )

    assert metadata["comparison_budget"] == {
        "max_pairs_requested": 90,
        "source": "service_default",
    }
    assert "config_overrides" not in metadata


@pytest.mark.asyncio
async def test_request_additional_comparisons_no_essays(monkeypatch: pytest.MonkeyPatch) -> None:
    database = AsyncMock()
    llm_interaction = AsyncMock()
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 500

    load_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(cp, "_load_essays_for_batch", load_mock)
    submit_mock = AsyncMock()
    monkeypatch.setattr(cp, "submit_comparisons_for_async_processing", submit_mock)

    result = await cp.request_additional_comparisons_for_batch(
        cj_batch_id=7,
        database=database,
        llm_interaction=llm_interaction,
        settings=settings,
        correlation_id=uuid4(),
        log_extra={"batch_id": 7},
        llm_overrides_payload=None,
        config_overrides_payload=None,
        original_request_payload=None,
    )

    assert result is False
    load_mock.assert_awaited_once_with(database=database, cj_batch_id=7)
    submit_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_additional_comparisons_submits_new_iteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    essays = [
        EssayForComparison(
            id="essay-1",
            text_content="text",
            current_bt_score=0.0,
        )
    ]
    load_mock = AsyncMock(return_value=essays)
    monkeypatch.setattr(cp, "_load_essays_for_batch", load_mock)

    submit_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(cp, "submit_comparisons_for_async_processing", submit_mock)

    # Mock database with proper async context manager support for session()
    database = AsyncMock()
    mock_session = AsyncMock()

    # Create a proper async context manager mock
    class AsyncContextManagerMock:
        async def __aenter__(self) -> AsyncMock:
            return mock_session

        async def __aexit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
            pass

    database.session = Mock(return_value=AsyncContextManagerMock())

    # Mock batch metadata that will be retrieved from database
    mock_batch = Mock()
    mock_batch.bos_batch_id = "batch-123"
    mock_batch.language = "en"
    mock_batch.course_code = "ENG5"
    mock_batch.assignment_id = "assignment-42"
    mock_batch.user_id = "user-1"
    mock_batch.org_id = "org-99"
    mock_batch.processing_metadata = {"student_prompt_text": "Prompt from batch"}

    database.get_cj_batch_upload = AsyncMock(return_value=mock_batch)

    llm_interaction = AsyncMock()
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 500

    llm_overrides_payload = {
        "model_override": "claude-3-sonnet",
        "temperature_override": 0.2,
    }
    config_overrides_payload = {"batch_size": 30}
    original_request_payload = {
        "assignment_id": "assignment-42",
        "language": "en",
        "course_code": "ENG5",
        "max_comparisons_override": 150,
        "llm_config_overrides": llm_overrides_payload,
        "batch_config_overrides": config_overrides_payload,
        "student_prompt_text": "Original prompt",
    }

    result = await cp.request_additional_comparisons_for_batch(
        cj_batch_id=42,
        database=database,
        llm_interaction=llm_interaction,
        settings=settings,
        correlation_id=uuid4(),
        log_extra={"batch_id": 42},
        llm_overrides_payload=llm_overrides_payload,
        config_overrides_payload=config_overrides_payload,
        original_request_payload=original_request_payload,
    )

    assert result is True
    load_mock.assert_awaited_once_with(database=database, cj_batch_id=42)
    submit_mock.assert_awaited_once()

    assert submit_mock.await_args is not None
    submit_kwargs = submit_mock.await_args.kwargs
    assert submit_kwargs["cj_batch_id"] == 42
    assert submit_kwargs["database"] is database
    assert submit_kwargs["llm_interaction"] is llm_interaction

    request_data = submit_kwargs["request_data"]
    assert (
        request_data.max_comparisons_override
        == original_request_payload["max_comparisons_override"]
    )
    assert isinstance(request_data.llm_config_overrides, cp.LLMConfigOverrides)
    assert request_data.batch_config_overrides == config_overrides_payload
    assert request_data.assignment_id == original_request_payload["assignment_id"]
    assert request_data.student_prompt_text == original_request_payload["student_prompt_text"]

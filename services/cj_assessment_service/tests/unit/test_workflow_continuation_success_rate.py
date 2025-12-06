"""Unit tests for success-rate based continuation semantics.

These tests focus on:
- Zero-success high-failure batches → failure finalization
- Low success rate despite some successes → failure finalization
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)


def _make_upload(expected_count: int) -> CJBatchUpload:
    return CJBatchUpload(
        bos_batch_id="bos-test",
        event_correlation_id="00000000-0000-0000-0000-000000000000",
        language="en",
        course_code="eng5",
        expected_essay_count=expected_count,
        status=None,
    )


@pytest.mark.asyncio
async def test_high_failure_rate_does_not_finalize_with_zero_successes(
    monkeypatch: Any,
) -> None:
    """Zero successful comparisons must not yield COMPLETE_* finalization."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 1
    settings.SCORE_STABILITY_THRESHOLD = 0.05
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 42
    batch_state.submitted_comparisons = 10
    batch_state.completed_comparisons = 0
    batch_state.failed_comparisons = 10
    batch_state.total_comparisons = 10
    batch_state.total_budget = 10
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 10, "source": "service_default"},
        "bt_scores": {},
    }
    batch_state.batch_upload = _make_upload(expected_count=10)

    essays = [
        AsyncMock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(10)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.11, "b": -0.09}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.2),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    request_additional = AsyncMock(return_value=False)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    finalize_scoring_called = AsyncMock()
    finalize_failure_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_scoring_called()

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_failure_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncSession, None]:
        yield AsyncMock(spec=AsyncSession)

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock(spec=CJEssayRepositoryProtocol)
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)
    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()
    mock_orientation_strategy = AsyncMock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=42,
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        essay_repository=mock_essay_repository,
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        event_publisher=event_publisher,
        settings=settings,
        content_client=content_client,
        correlation_id=uuid4(),
        llm_interaction=llm_interaction,
        matching_strategy=mock_matching_strategy,
        grade_projector=mock_grade_projector,
        orientation_strategy=mock_orientation_strategy,
    )

    finalize_failure_called.assert_awaited_once()
    finalize_scoring_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_success_rate_does_not_finalize_despite_some_successes(
    monkeypatch: Any,
) -> None:
    """Few successes with many failures must not yield COMPLETE_* finalization."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 1
    settings.SCORE_STABILITY_THRESHOLD = 0.05
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 43
    batch_state.submitted_comparisons = 10
    batch_state.completed_comparisons = 2
    batch_state.failed_comparisons = 8
    batch_state.total_comparisons = 10
    batch_state.total_budget = 10
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 10, "source": "service_default"},
        "bt_scores": {"a": 0.1, "b": -0.1},
    }
    batch_state.batch_upload = _make_upload(expected_count=10)

    essays = [
        AsyncMock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(10)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.11, "b": -0.09}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.2),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    request_additional = AsyncMock(return_value=False)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    finalize_scoring_called = AsyncMock()
    finalize_failure_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_scoring_called()

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_failure_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncSession, None]:
        yield AsyncMock(spec=AsyncSession)

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock(spec=CJEssayRepositoryProtocol)
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)
    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()
    mock_orientation_strategy = AsyncMock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=43,
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repository,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        essay_repository=mock_essay_repository,
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        event_publisher=event_publisher,
        settings=settings,
        content_client=content_client,
        correlation_id=uuid4(),
        llm_interaction=llm_interaction,
        matching_strategy=mock_matching_strategy,
        grade_projector=mock_grade_projector,
        orientation_strategy=mock_orientation_strategy,
    )

    finalize_failure_called.assert_awaited_once()
    finalize_scoring_called.assert_not_awaited()

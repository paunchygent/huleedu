"""Unit tests for BT metadata and quality-flag updates in continuation.

These tests focus on:
- Metadata JSON-safety when no previous scores exist.
- BT SE summary threading and bt_quality_flags derivation.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.cj_core_logic.scoring_ranking import BTScoringResult
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


@asynccontextmanager
async def _session_ctx() -> AsyncGenerator[AsyncSession, None]:
    yield AsyncMock(spec=AsyncSession)


@pytest.mark.asyncio
async def test_trigger_continuation_metadata_serializable_without_previous_scores(
    monkeypatch: Any,
) -> None:
    """last_score_change and metadata must remain JSON-safe when no previous scores."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 1
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 11
    batch_state.submitted_comparisons = 1
    batch_state.completed_comparisons = 1
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 1
    batch_state.total_budget = 1
    batch_state.current_iteration = 0
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 1, "source": "service_default"}
    }
    batch_state.batch_upload = _make_upload(expected_count=2)

    essays = [
        AsyncMock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(2)
    ]

    current_scores = {"essay-1": 0.2, "essay-2": -0.2}

    async def _fake_record_comparisons_and_update_scores(
        *args: Any,
        scoring_result_container: list[BTScoringResult] | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        if scoring_result_container is not None:
            scoring_result_container.append(
                BTScoringResult(
                    scores=current_scores,
                    ses={"essay-1": 0.1, "essay-2": 0.1},
                    per_essay_counts={"essay-1": 1, "essay-2": 1},
                    se_summary={
                        "mean_se": 0.1,
                        "max_se": 0.1,
                        "min_se": 0.1,
                        "item_count": 2,
                        "comparison_count": 1,
                        "items_at_cap": 0,
                        "isolated_items": 0,
                        "mean_comparisons_per_item": 1.0,
                        "min_comparisons_per_item": 1,
                        "max_comparisons_per_item": 1,
                    },
                )
            )
        return current_scores

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(side_effect=_fake_record_comparisons_and_update_scores),
    )
    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

    finalize_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

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
        batch_id=11,
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

    merge_metadata.assert_awaited_once()
    await_args = merge_metadata.await_args
    assert await_args is not None
    metadata_updates = await_args.kwargs["metadata_updates"]
    assert metadata_updates["last_score_change"] is None
    assert "bt_se_summary" in metadata_updates
    se_summary = metadata_updates["bt_se_summary"]
    assert se_summary["item_count"] == 2
    assert se_summary["comparison_count"] == 1
    json.dumps(metadata_updates)


@pytest.mark.asyncio
async def test_bt_quality_flags_derived_from_bt_se_summary(monkeypatch: Any) -> None:
    """BT SE diagnostics should derive batch quality flags safely."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 1
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05
    settings.BT_MEAN_SE_WARN_THRESHOLD = 0.4
    settings.BT_MAX_SE_WARN_THRESHOLD = 0.8
    settings.BT_MIN_MEAN_COMPARISONS_PER_ITEM = 1.0

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 21
    batch_state.submitted_comparisons = 1
    batch_state.completed_comparisons = 1
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 1
    batch_state.total_budget = 1
    batch_state.current_iteration = 0
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 1, "source": "service_default"}
    }
    batch_state.batch_upload = _make_upload(expected_count=2)

    essays = [
        AsyncMock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(2)
    ]

    current_scores = {"essay-1": 0.2, "essay-2": -0.2}

    se_summaries: list[dict[str, Any]] = [
        {
            "mean_se": 0.2,
            "max_se": 0.3,
            "min_se": 0.1,
            "item_count": 2,
            "comparison_count": 1,
            "items_at_cap": 0,
            "isolated_items": 0,
            "mean_comparisons_per_item": 2.0,
            "min_comparisons_per_item": 1,
            "max_comparisons_per_item": 3,
        },
        {
            "mean_se": 0.5,
            "max_se": 0.9,
            "min_se": 0.1,
            "item_count": 2,
            "comparison_count": 1,
            "items_at_cap": 0,
            "isolated_items": 0,
            "mean_comparisons_per_item": 2.0,
            "min_comparisons_per_item": 1,
            "max_comparisons_per_item": 3,
        },
        {
            "mean_se": 0.1,
            "max_se": 0.2,
            "min_se": 0.05,
            "item_count": 2,
            "comparison_count": 1,
            "items_at_cap": 0,
            "isolated_items": 0,
            "mean_comparisons_per_item": 0.5,
            "min_comparisons_per_item": 0,
            "max_comparisons_per_item": 1,
        },
        {
            "mean_se": 0.1,
            "max_se": 0.2,
            "min_se": 0.05,
            "item_count": 2,
            "comparison_count": 1,
            "items_at_cap": 0,
            "isolated_items": 2,
            "mean_comparisons_per_item": 2.0,
            "min_comparisons_per_item": 0,
            "max_comparisons_per_item": 3,
        },
    ]

    expected_flags = [
        {
            "bt_se_inflated": False,
            "comparison_coverage_sparse": False,
            "has_isolated_items": False,
        },
        {
            "bt_se_inflated": True,
            "comparison_coverage_sparse": False,
            "has_isolated_items": False,
        },
        {
            "bt_se_inflated": False,
            "comparison_coverage_sparse": True,
            "has_isolated_items": False,
        },
        {
            "bt_se_inflated": False,
            "comparison_coverage_sparse": False,
            "has_isolated_items": True,
        },
    ]

    call_index = 0

    async def _fake_record_comparisons_and_update_scores(
        *args: Any,
        scoring_result_container: list[BTScoringResult] | None = None,
        **kwargs: Any,
    ) -> dict[str, float]:
        nonlocal call_index
        if scoring_result_container is not None:
            scoring_result_container.append(
                BTScoringResult(
                    scores=current_scores,
                    ses={"essay-1": 0.1, "essay-2": 0.1},
                    per_essay_counts={"essay-1": 1, "essay-2": 1},
                    se_summary=se_summaries[call_index],
                )
            )
        call_index += 1
        return current_scores

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(side_effect=_fake_record_comparisons_and_update_scores),
    )
    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            return None

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            return None

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

    for _ in se_summaries:
        await wc.trigger_existing_workflow_continuation(
            batch_id=21,
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

    assert merge_metadata.await_count == len(se_summaries)

    for idx, expected in enumerate(expected_flags):
        await_args = merge_metadata.await_args_list[idx]
        metadata_updates = await_args.kwargs["metadata_updates"]
        assert "bt_quality_flags" in metadata_updates
        flags = metadata_updates["bt_quality_flags"]
        assert flags == expected
        json.dumps(metadata_updates)

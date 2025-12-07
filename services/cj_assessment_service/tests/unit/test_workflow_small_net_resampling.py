"""Unit tests for small-net Phase-2 resampling semantics.

These tests focus on:
- Coverage and small-net flags derived from processing_metadata.
- The small-net resampling predicate.
- The continuation branch that requests additional comparisons in RESAMPLING mode.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.cj_core_logic.workflow_context import ContinuationContext
from services.cj_assessment_service.cj_core_logic.workflow_decision import (
    _can_attempt_small_net_resampling,
    _derive_small_net_flags,
)
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
async def test_small_net_phase2_requests_additional_comparisons_before_resampling_cap(
    monkeypatch: Any,
) -> None:
    """Small-net Phase 2 should prefer resampling to immediate finalization."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 100
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 3
    settings.SCORE_STABILITY_THRESHOLD = 0.01
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.0
    settings.MIN_RESAMPLING_NET_SIZE = 5
    settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET = 2

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    # Small net: 3 essays, all pairs covered at least once (3 pairs).
    batch_state = CJBatchState()
    batch_state.batch_id = 50
    batch_state.submitted_comparisons = 6  # two rounds of 3 pairs
    batch_state.completed_comparisons = 6
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 6
    batch_state.total_budget = 100
    batch_state.current_iteration = 2
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 100, "source": "service_default"},
        "bt_scores": {"e1": 0.1, "e2": -0.1},
        "successful_pairs_count": 3,
        "max_possible_pairs": 3,
        "unique_coverage_complete": True,
        "resampling_pass_count": 0,
    }
    batch_state.batch_upload = _make_upload(expected_count=3)

    essays = [
        Mock(
            els_essay_id=f"essay-{i}",
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=2,
            is_anchor=False,
        )
        for i in range(3)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"e1": 0.12, "e2": -0.08}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.05),  # > SCORE_STABILITY_THRESHOLD → not stable
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    request_additional = AsyncMock(return_value=True)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

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
        batch_id=50,
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

    request_additional.assert_awaited_once()
    finalize_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_small_net_phase2_tracks_resampling_pass_count(monkeypatch: Any) -> None:
    """Small-net Phase 2 should track resampling passes and use RESAMPLING mode."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 100
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 3
    settings.SCORE_STABILITY_THRESHOLD = 0.01
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.0
    settings.MIN_RESAMPLING_NET_SIZE = 5
    settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET = 2

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 51
    batch_state.submitted_comparisons = 2
    batch_state.completed_comparisons = 2
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 2
    batch_state.total_budget = 100
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 100, "source": "service_default"},
        "bt_scores": {"e1": 0.1, "e2": -0.1},
        "successful_pairs_count": 3,
        "max_possible_pairs": 3,
        "unique_coverage_complete": True,
        "resampling_pass_count": 0,
    }
    batch_state.batch_upload = _make_upload(expected_count=3)

    essays = [
        Mock(
            els_essay_id=f"essay-{i}",
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
            is_anchor=False,
        )
        for i in range(3)
    ]

    comparison_repo_for_flags = AsyncMock(spec=CJComparisonRepositoryProtocol)
    dummy_session = AsyncMock(spec=AsyncSession)

    (
        expected_essay_count,
        is_small_net,
        max_possible_pairs,
        successful_pairs_count,
        unique_coverage_complete,
        resampling_pass_count,
        small_net_resampling_cap,
        small_net_cap_reached,
    ) = await _derive_small_net_flags(
        batch_id=batch_state.batch_id,
        batch_state=batch_state,
        metadata=batch_state.processing_metadata,
        settings=settings,
        comparison_repository=comparison_repo_for_flags,
        session=dummy_session,
        log_extra={},
    )

    assert expected_essay_count == 3
    assert is_small_net is True
    assert max_possible_pairs == 3
    assert successful_pairs_count == 3
    assert unique_coverage_complete is True
    assert resampling_pass_count == 0
    assert small_net_resampling_cap == settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET
    assert small_net_cap_reached is False

    ctx = ContinuationContext(
        batch_id=batch_state.batch_id,
        callbacks_received=batch_state.completed_comparisons + batch_state.failed_comparisons,
        pending_callbacks=0,
        denominator=batch_state.completion_denominator(),
        completed=batch_state.completed_comparisons,
        failed=batch_state.failed_comparisons,
        pairs_submitted=batch_state.submitted_comparisons,
        max_pairs_cap=settings.MAX_PAIRWISE_COMPARISONS,
        pairs_remaining=settings.MAX_PAIRWISE_COMPARISONS - batch_state.submitted_comparisons,
        budget_exhausted=False,
        callbacks_reached_cap=False,
        success_rate=1.0,
        success_rate_threshold=settings.MIN_SUCCESS_RATE_THRESHOLD,
        zero_successes=False,
        below_success_threshold=False,
        should_fail_due_to_success_rate=False,
        max_score_change=None,
        stability_passed=False,
        should_finalize=False,
        expected_essay_count=expected_essay_count,
        is_small_net=is_small_net,
        max_possible_pairs=max_possible_pairs,
        successful_pairs_count=successful_pairs_count,
        unique_coverage_complete=unique_coverage_complete,
        resampling_pass_count=resampling_pass_count,
        small_net_resampling_cap=small_net_resampling_cap,
        small_net_cap_reached=small_net_cap_reached,
        regular_batch_resampling_cap=0,
        regular_batch_cap_reached=False,
        bt_se_summary=None,
        bt_quality_flags=None,
        bt_se_inflated=False,
        comparison_coverage_sparse=False,
        has_isolated_items=False,
        metadata_updates={},
    )

    assert _can_attempt_small_net_resampling(ctx) is True

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"e1": 0.12, "e2": -0.08}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.05),
    )
    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

    request_additional = AsyncMock(return_value=True)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    class _Finalizer:  # pragma: no cover - future Phase-2 semantics
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

    await wc.trigger_existing_workflow_continuation(
        batch_id=51,
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
    assert metadata_updates.get("resampling_pass_count") == 1

    request_additional.assert_awaited_once()
    cont_args = request_additional.await_args
    assert cont_args is not None
    assert cont_args.kwargs["mode"] == wc.PairGenerationMode.RESAMPLING


@pytest.mark.asyncio
async def test_small_net_resampling_respects_resampling_pass_cap(monkeypatch: Any) -> None:
    """Small-net Phase 2 should stop resampling once the pass cap is hit."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 100
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 3
    settings.SCORE_STABILITY_THRESHOLD = 0.01
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.0
    settings.MIN_RESAMPLING_NET_SIZE = 5
    settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET = 2

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 52
    batch_state.submitted_comparisons = 2
    batch_state.completed_comparisons = 2
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 2
    batch_state.total_budget = 100
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 100, "source": "service_default"},
        "bt_scores": {"e1": 0.1, "e2": -0.1},
        "successful_pairs_count": 3,
        "max_possible_pairs": 3,
        "unique_coverage_complete": True,
        "resampling_pass_count": 2,
    }
    batch_state.batch_upload = _make_upload(expected_count=3)

    essays = [
        Mock(
            els_essay_id=f"essay-{i}",
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
            is_anchor=False,
        )
        for i in range(3)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"e1": 0.12, "e2": -0.08}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.05),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    request_additional = AsyncMock(return_value=True)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    finalize_scoring_called = AsyncMock()
    finalize_failure_called = AsyncMock()

    class _Finalizer:  # pragma: no cover - small-net Phase-2 finalization
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
        batch_id=52,
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

    assert request_additional.await_count == 0
    total_finalize_calls = finalize_scoring_called.await_count + finalize_failure_called.await_count
    assert total_finalize_calls == 1


@pytest.mark.asyncio
async def test_regular_batch_resampling_branch_requests_resampling(monkeypatch: Any) -> None:
    """Non-small nets should be able to enter RESAMPLING with a separate cap."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 200
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 3
    settings.SCORE_STABILITY_THRESHOLD = 0.01
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.0
    settings.MIN_RESAMPLING_NET_SIZE = 5
    settings.MAX_RESAMPLING_PASSES_FOR_SMALL_NET = 3
    settings.MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH = 1

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    # Regular net: expected_essay_count > MIN_RESAMPLING_NET_SIZE with partial but
    # substantial coverage (successful_pairs_count / max_possible_pairs >= 0.6).
    batch_state = CJBatchState()
    batch_state.batch_id = 200
    batch_state.submitted_comparisons = 40
    batch_state.completed_comparisons = 40
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 40
    batch_state.total_budget = 200
    batch_state.current_iteration = 2
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 200, "source": "service_default"},
        "bt_scores": {"e1": 0.1, "e2": -0.1},
        "successful_pairs_count": 60,
        "max_possible_pairs": 80,
        "unique_coverage_complete": False,
        "resampling_pass_count": 0,
    }
    batch_state.batch_upload = _make_upload(expected_count=20)

    essays = [
        Mock(
            els_essay_id=f"essay-{i}",
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=2,
            is_anchor=False,
        )
        for i in range(20)
    ]

    # Keep stability pending so continuation prefers more work.
    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"e1": 0.12, "e2": -0.08}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.05),
    )

    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

    request_additional = AsyncMock(return_value=True)
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

    comparison_repo = AsyncMock(spec=CJComparisonRepositoryProtocol)
    # Full coverage for regular net: 80 possible pairs, all successful.
    comparison_repo.get_coverage_metrics_for_batch = AsyncMock(return_value=(80, 80))

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()
    mock_orientation_strategy = AsyncMock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=200,
        session_provider=mock_session_provider,
        batch_repository=mock_batch_repository,
        comparison_repository=comparison_repo,
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

    # Regular-batch resampling should be attempted once, using RESAMPLING mode.
    merge_metadata.assert_awaited_once()
    merge_call: Any = merge_metadata.await_args
    metadata_updates = merge_call.kwargs["metadata_updates"]
    assert metadata_updates.get("resampling_pass_count") == 1
    assert metadata_updates.get("successful_pairs_count") == 80
    assert metadata_updates.get("max_possible_pairs") == 80

    request_additional.assert_awaited_once()
    cont_args: Any = request_additional.await_args
    assert cont_args is not None
    assert cont_args.kwargs["mode"] == wc.PairGenerationMode.RESAMPLING

    # The configured regular-batch cap must be respected.
    assert settings.MAX_RESAMPLING_PASSES_FOR_REGULAR_BATCH == 1

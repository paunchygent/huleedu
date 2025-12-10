"""Unit tests for trigger_existing_workflow_continuation orchestration (core flows).

This module keeps to:
- Budget/cap finalization
- Stability-based early finalization vs requesting more comparisons
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
async def test_trigger_continuation_finalizes_when_callbacks_hit_cap(monkeypatch: Any) -> None:
    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 6

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 9
    batch_state.submitted_comparisons = 6
    batch_state.completed_comparisons = 6
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 6
    batch_state.total_budget = 6
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {}
    batch_state.batch_upload = _make_upload(expected_count=4)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=3,
        )
        for i in range(4)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.1, "b": 0.2}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.01),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    finalize_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    mock_session_provider = AsyncMock()

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncSession, None]:
        yield AsyncMock(spec=AsyncSession)

    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock(spec=CJBatchRepositoryProtocol)
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock(spec=CJEssayRepositoryProtocol)
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)
    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()
    mock_orientation_strategy = AsyncMock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=9,
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

    finalize_called.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_continuation_requests_more_when_not_finalized(
    monkeypatch: Any,
) -> None:
    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 10
    batch_state.submitted_comparisons = 4
    batch_state.completed_comparisons = 4
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 4
    batch_state.total_budget = 10
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 10, "source": "service_default"},
        "config_overrides": {"batch_size": 25},
        "llm_overrides": {"model_override": "claude"},
        "original_request": {"assignment_id": "assignment-123"},
    }
    batch_state.batch_upload = _make_upload(expected_count=5)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(5)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.1, "b": 0.3}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.2),
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
        batch_id=10,
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
    await_args = request_additional.await_args
    assert await_args is not None
    assert await_args.kwargs["mode"] == wc.PairGenerationMode.COVERAGE
    finalize_called.assert_not_awaited()


class _DummyContinuationContext:
    """Minimal continuation context for finalization guard tests."""

    def __init__(self) -> None:
        self.metadata_updates: dict[str, Any] = {}
        self.max_possible_pairs = 0
        self.successful_pairs_count = 0
        self.unique_coverage_complete = False
        self.resampling_pass_count = 0
        self.small_net_resampling_cap = 0
        self.regular_batch_resampling_cap = 0
        self.is_small_net = False
        self.small_net_cap_reached = False
        self.bt_se_inflated = False
        self.comparison_coverage_sparse = False
        self.has_isolated_items = False
        self.callbacks_received = 4
        self.denominator = 4
        self.max_score_change = 0.0
        self.success_rate = 1.0
        self.success_rate_threshold = 0.8
        self.callbacks_reached_cap = True
        self.budget_exhausted = False
        self.pairs_remaining = 0
        self.completed = 4
        self.failed = 0
        self.expected_essay_count = 4


@pytest.mark.asyncio
async def test_finalization_skipped_when_fresh_pending_callbacks_detected(
    monkeypatch: Any,
) -> None:
    """Fresh pending callbacks guard should skip FINALIZE_SCORING."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 4

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 11
    batch_state.submitted_comparisons = 4
    batch_state.completed_comparisons = 4
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 4
    batch_state.total_budget = 4
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {}
    batch_state.batch_upload = _make_upload(expected_count=4)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(4)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.0),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    dummy_ctx = _DummyContinuationContext()
    monkeypatch.setattr(
        wc,
        "_build_continuation_context",
        AsyncMock(return_value=dummy_ctx),
    )
    monkeypatch.setattr(wc, "_can_attempt_resampling", Mock(return_value=False))
    monkeypatch.setattr(wc, "record_workflow_decision", Mock())
    monkeypatch.setattr(
        wc,
        "decide",
        Mock(return_value=wc.ContinuationDecision.FINALIZE_SCORING),
    )

    has_fresh_pending = AsyncMock(return_value=True)
    monkeypatch.setattr(wc, "_has_fresh_pending_callbacks", has_fresh_pending)

    finalize_scoring_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_scoring_called()

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("finalize_failure should not be called in this test")

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
        batch_id=batch_state.batch_id,
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

    assert has_fresh_pending.await_count == 1
    finalize_scoring_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_finalization_proceeds_when_no_fresh_pending_callbacks(
    monkeypatch: Any,
) -> None:
    """FINALIZE_SCORING should proceed when guard reports no pending callbacks."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 4

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 12
    batch_state.submitted_comparisons = 4
    batch_state.completed_comparisons = 4
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 4
    batch_state.total_budget = 4
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {}
    batch_state.batch_upload = _make_upload(expected_count=4)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(4)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.0),
    )
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", AsyncMock())

    dummy_ctx = _DummyContinuationContext()
    monkeypatch.setattr(
        wc,
        "_build_continuation_context",
        AsyncMock(return_value=dummy_ctx),
    )
    monkeypatch.setattr(wc, "_can_attempt_resampling", Mock(return_value=False))
    monkeypatch.setattr(wc, "record_workflow_decision", Mock())
    monkeypatch.setattr(
        wc,
        "decide",
        Mock(return_value=wc.ContinuationDecision.FINALIZE_SCORING),
    )

    has_fresh_pending = AsyncMock(return_value=False)
    monkeypatch.setattr(wc, "_has_fresh_pending_callbacks", has_fresh_pending)

    finalize_scoring_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_scoring_called()

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("finalize_failure should not be called in this test")

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
        batch_id=batch_state.batch_id,
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

    assert has_fresh_pending.await_count == 1
    finalize_scoring_called.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_continuation_provider_batch_api_finalizes_without_requesting_more(
    monkeypatch: Any,
) -> None:
    """provider_batch_api mode should finalize on caps without new waves."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 6

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 21
    batch_state.submitted_comparisons = 6
    batch_state.completed_comparisons = 6
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 6
    batch_state.total_budget = 6
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {"llm_batching_mode": "provider_batch_api"}
    batch_state.batch_upload = _make_upload(expected_count=4)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=3,
        )
        for i in range(4)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.1, "b": 0.2}),
    )
    # Force an "unstable" delta to verify stability is ignored for provider_batch_api.
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.5),
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

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("finalize_failure should not be used in this test")

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)
    monkeypatch.setattr(wc, "_has_fresh_pending_callbacks", AsyncMock(return_value=False))

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
        batch_id=batch_state.batch_id,
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

    finalize_called.assert_awaited_once()
    request_additional.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_continuation_provider_batch_api_ignores_stability_flag(
    monkeypatch: Any,
) -> None:
    """provider_batch_api should not request more comparisons even when unstable."""

    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 22
    batch_state.submitted_comparisons = 4
    batch_state.completed_comparisons = 4
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 4
    batch_state.total_budget = 10
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {
        "llm_batching_mode": "provider_batch_api",
        "comparison_budget": {"max_pairs_requested": 10, "source": "service_default"},
    }
    batch_state.batch_upload = _make_upload(expected_count=5)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(5)
    ]

    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value={"a": 0.1, "b": 0.3}),
    )
    # Large delta keeps stability_passed=False but should not trigger new waves.
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.5),
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

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
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
        batch_id=batch_state.batch_id,
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

    # In provider_batch_api mode, no additional comparisons should be requested.
    request_additional.assert_not_awaited()

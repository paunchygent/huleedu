"""Unit tests for workflow_continuation.check_workflow_continuation.

Validates periodic and threshold-based continuation logic with minimal mocks.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncContextManager, AsyncGenerator, cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum as CoreCJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.cj_core_logic.scoring_ranking import BTScoringResult
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import (
    AssessmentInstruction,
    CJBatchState,
    CJBatchUpload,
    ComparisonPair,
)
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)
from services.cj_assessment_service.tests.unit.test_mocks import AssessmentInstructionStore


class _FakeSession:
    def __init__(self, completed_count: int) -> None:
        self._completed_count = completed_count

    async def execute(self, _stmt: Any) -> Any:
        class _Res:
            def __init__(self, n: int) -> None:
                self._n = n

            def scalar_one(self) -> int:
                return self._n

            def scalars(self) -> Any:
                class _Scalars:
                    def __init__(self, n: int) -> None:
                        self._n = n

                    def all(self) -> list[int]:
                        return list(range(self._n))

                return _Scalars(self._n)

        return _Res(self._completed_count)


@asynccontextmanager
async def _session_ctx(session: _FakeSession) -> AsyncGenerator[AsyncSession, None]:
    yield cast(AsyncSession, session)


class _Repo:
    def __init__(self, session: _FakeSession, batch_state: CJBatchState | None = None) -> None:
        self._session = session
        self._instruction_store = AssessmentInstructionStore()
        self._batch_state = batch_state

    def session(self) -> Any:
        return _session_ctx(self._session)

    # Unused protocol methods for these tests
    async def get_assessment_instruction(
        self, session: Any, assignment_id: str | None, course_id: str | None
    ) -> AssessmentInstruction | None:
        return self._instruction_store.get(assignment_id=assignment_id, course_id=course_id)

    async def get_cj_batch_upload(self, *args: Any, **kwargs: Any) -> Any | None:
        return None

    async def get_assignment_context(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return {
            "assignment_id": "test-assignment",
            "instructions_text": "Mock instructions",
            "grade_scale": "swedish_8_anchor",
        }

    async def get_anchor_essay_references(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def store_grade_projections(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def create_new_cj_batch(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def create_or_update_cj_processed_essay(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def get_essays_for_cj_batch(self, *args: Any, **kwargs: Any) -> list[Any]:
        return []

    async def get_comparison_pair_by_essays(self, *args: Any, **kwargs: Any) -> Any | None:
        return None

    async def get_comparison_pair_by_correlation_id(
        self, *args: Any, **kwargs: Any
    ) -> ComparisonPair | None:
        return None

    async def store_comparison_results(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_essay_scores_in_batch(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_cj_batch_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def get_final_cj_rankings(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def get_batch_state(
        self, session: Any, cj_batch_id: int, *, for_update: bool = False
    ) -> CJBatchState | None:
        return self._batch_state

    async def upsert_assessment_instruction(
        self,
        session: Any,
        *,
        assignment_id: str | None,
        course_id: str | None,
        instructions_text: str,
        grade_scale: str,
        student_prompt_storage_id: str | None = None,
        judge_rubric_storage_id: str | None = None,
    ) -> AssessmentInstruction:
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
            judge_rubric_storage_id=judge_rubric_storage_id,
        )

    async def list_assessment_instructions(
        self,
        session: Any,
        *,
        limit: int,
        offset: int,
        grade_scale: str | None = None,
    ) -> tuple[list[AssessmentInstruction], int]:
        return self._instruction_store.list(limit=limit, offset=offset, grade_scale=grade_scale)

    async def delete_assessment_instruction(
        self,
        session: Any,
        *,
        assignment_id: str | None,
        course_id: str | None,
    ) -> bool:
        return self._instruction_store.delete(
            assignment_id=assignment_id,
            course_id=course_id,
        )

    async def initialize_db_schema(self) -> None:
        return None

    async def upsert_anchor_reference(
        self,
        session: Any,
        *,
        assignment_id: str,
        anchor_label: str,
        grade: str,
        grade_scale: str,
        text_storage_id: str,
    ) -> int:
        """Stub implementation for test mocks."""
        return 1  # Return a mock anchor ID

    async def get_stuck_batches(
        self,
        session: Any,
        states: list[CoreCJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list[CJBatchState]:
        """Get batches stuck in specified states beyond threshold."""
        return []

    async def get_batches_ready_for_completion(
        self,
        session: Any,
    ) -> list[CJBatchState]:
        """Get batches ready for final completion."""
        return []

    async def get_batch_state_for_update(
        self,
        session: Any,
        batch_id: int,
        for_update: bool = False,
    ) -> CJBatchState | None:
        """Get batch state with optional row locking."""
        return None

    async def update_batch_state(
        self,
        session: Any,
        batch_id: int,
        state: CoreCJBatchStateEnum,
    ) -> None:
        """Update batch state."""
        pass


class _SessionProvider(SessionProviderProtocol):
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> AsyncContextManager[AsyncSession]:
        return _session_ctx(self._session)


def _make_upload(expected_count: int) -> CJBatchUpload:
    return CJBatchUpload(
        bos_batch_id="bos-test",
        event_correlation_id="00000000-0000-0000-0000-000000000000",
        language="en",
        course_code="eng5",
        expected_essay_count=expected_count,
        status=CJBatchStatusEnum.PENDING,
    )


@pytest.mark.asyncio
async def test_check_continuation_true_when_all_callbacks_arrived() -> None:
    session = _FakeSession(completed_count=10)

    batch_state = CJBatchState()
    batch_state.batch_id = 1
    batch_state.submitted_comparisons = 5
    batch_state.completed_comparisons = 3
    batch_state.failed_comparisons = 2

    repo = _Repo(session, batch_state=batch_state)

    session_provider = _SessionProvider(session)
    should_continue = await wc.check_workflow_continuation(
        batch_id=1,
        session_provider=session_provider,
        batch_repository=repo,
        correlation_id=uuid4(),
    )

    assert should_continue is True


@pytest.mark.asyncio
async def test_check_continuation_false_when_pending() -> None:
    session = _FakeSession(completed_count=3)

    batch_state = CJBatchState()
    batch_state.batch_id = 2
    batch_state.submitted_comparisons = 6
    batch_state.completed_comparisons = 4
    batch_state.failed_comparisons = 1

    repo = _Repo(session, batch_state=batch_state)

    session_provider = _SessionProvider(session)
    should_continue = await wc.check_workflow_continuation(
        batch_id=2,
        session_provider=session_provider,
        batch_repository=repo,
        correlation_id=uuid4(),
    )

    assert should_continue is False


@pytest.mark.asyncio
async def test_check_continuation_false_when_nothing_submitted() -> None:
    session = _FakeSession(completed_count=0)

    batch_state = CJBatchState()
    batch_state.batch_id = 3
    batch_state.submitted_comparisons = 0
    batch_state.completed_comparisons = 0
    batch_state.failed_comparisons = 0

    repo = _Repo(session, batch_state=batch_state)

    session_provider = _SessionProvider(session)
    should_continue = await wc.check_workflow_continuation(
        batch_id=3,
        session_provider=session_provider,
        batch_repository=repo,
        correlation_id=uuid4(),
    )

    assert should_continue is False


@pytest.mark.parametrize(
    "metadata,max_pairs_expected",
    [
        ({"comparison_budget": {"max_pairs_requested": 120, "source": "runner_override"}}, 120),
        ({"comparison_budget": {"max_pairs_requested": 75, "source": "service_default"}}, 75),
        (None, 150),
        ({"comparison_budget": {"max_pairs_requested": 0, "source": "service_default"}}, 150),
    ],
)
def test_resolve_comparison_budget(
    metadata: dict[str, Any] | None, max_pairs_expected: int
) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 150

    max_pairs = wc._resolve_comparison_budget(metadata, settings)

    assert max_pairs == max_pairs_expected


@pytest.mark.asyncio
async def test_trigger_continuation_finalizes_when_callbacks_hit_cap(monkeypatch: Any) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 150

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 9
    batch_state.submitted_comparisons = 6
    batch_state.completed_comparisons = 6
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 6
    batch_state.total_budget = 150
    batch_state.current_iteration = 1
    batch_state.processing_metadata = {}

    # Provide essay count for nC2 = 6
    batch_state.batch_upload = _make_upload(expected_count=4)

    # Mock essays with comparison counts that meet fairness criteria
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

    # Mock BatchFinalizer (grade projector is passed explicitly in call)
    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    finalize_called.assert_awaited_once()


@pytest.mark.asyncio
async def test_trigger_continuation_metadata_serializable_without_previous_scores(
    monkeypatch: Any,
) -> None:
    """Regression: last_score_change should be JSON-serializable when no previous scores."""

    settings = Mock(spec=Settings)
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
        Mock(
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
        """Populate scoring_result_container to simulate BTScoringResult propagation."""
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

    # Mock BatchFinalizer (grade projector passed explicitly)
    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    merge_metadata.assert_awaited_once()
    await_args = merge_metadata.await_args
    assert await_args is not None
    metadata_updates = await_args.kwargs["metadata_updates"]
    assert metadata_updates["last_score_change"] is None
    # SE summary should be threaded into processing metadata when available
    assert "bt_se_summary" in metadata_updates
    se_summary = metadata_updates["bt_se_summary"]
    assert se_summary["item_count"] == 2
    assert se_summary["comparison_count"] == 1
    # Ensure metadata can be JSON serialized without Infinity/NaN
    json.dumps(metadata_updates)


@pytest.mark.asyncio
async def test_bt_quality_flags_derived_from_bt_se_summary(monkeypatch: Any) -> None:
    """BT SE diagnostics should derive batch quality flags safely."""

    settings = Mock(spec=Settings)
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
        Mock(
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
            # Normal SE and coverage → all flags False
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
            # Inflated SE → only bt_se_inflated=True
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
            # Sparse coverage → comparison_coverage_sparse=True
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
            # Isolated items → has_isolated_items=True
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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
        )

    assert merge_metadata.await_count == len(se_summaries)

    for idx, expected in enumerate(expected_flags):
        await_args = merge_metadata.await_args_list[idx]
        metadata_updates = await_args.kwargs["metadata_updates"]
        assert "bt_quality_flags" in metadata_updates
        flags = metadata_updates["bt_quality_flags"]
        assert flags == expected
        # Ensure metadata (including flags) is JSON-serializable
        json.dumps(metadata_updates)


@pytest.mark.asyncio
async def test_trigger_continuation_requests_more_when_not_finalized(monkeypatch: Any) -> None:
    settings = Mock(spec=Settings)
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

    # Mock BatchFinalizer (grade projector passed explicitly)
    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    request_additional.assert_awaited_once()
    # Phase-1 / large-net semantics should continue using COVERAGE mode.
    await_args = request_additional.await_args
    assert await_args is not None
    assert await_args.kwargs["mode"] == wc.PairGenerationMode.COVERAGE
    finalize_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_high_failure_rate_does_not_finalize_with_zero_successes(
    monkeypatch: Any,
) -> None:
    """Zero successful comparisons must not yield COMPLETE_* finalization.

    This is the strictest form of the EPIC-005 / US-005.2 guardrail:
    when all attempts have failed and callbacks/budget are exhausted, the
    workflow should not call BatchFinalizer.finalize_scoring(). PR-2 will
    introduce explicit failure semantics for this case; until then this test
    is marked xfail and serves as a behavioural spec.
    """

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 1
    settings.SCORE_STABILITY_THRESHOLD = 0.05
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    # Simulate 10 attempts, all failed, with budget and denominator both hit.
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
    # expected_essay_count large enough that nC2 >= total_budget → denominator = 10
    batch_state.batch_upload = _make_upload(expected_count=10)

    essays = [
        Mock(
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
    # Keep stability failing so finalization is driven purely by caps.
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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    # PR-2 behaviour: BatchFinalizer.finalize_failure must be invoked
    # when there are zero successful comparisons and caps are reached.
    finalize_failure_called.assert_awaited_once()
    finalize_scoring_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_success_rate_does_not_finalize_despite_some_successes(
    monkeypatch: Any,
) -> None:
    """Few successes with many failures must not yield COMPLETE_* finalization.

    EPIC-005 / US-005.2 guardrail: when callbacks/budget are exhausted but the
    success rate is below MIN_SUCCESS_RATE_THRESHOLD, the workflow should not
    call BatchFinalizer.finalize_scoring(). Instead, PR-2 semantics will route
    this through an explicit failure path. Until then this test is xfail and
    serves as a behavioural spec.
    """

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 10
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 1
    settings.SCORE_STABILITY_THRESHOLD = 0.05
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.8

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    # Simulate 10 attempts with a low success rate: 2 successes, 8 failures.
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
    # expected_essay_count large enough that nC2 >= total_budget → denominator = 10
    batch_state.batch_upload = _make_upload(expected_count=10)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=1,
        )
        for i in range(10)
    ]

    # Recompute scores and keep stability failing so that finalization is
    # driven purely by caps and the success-rate guard.
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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    # PR-2 behaviour: BatchFinalizer.finalize_failure must be invoked
    # when the success rate is below MIN_SUCCESS_RATE_THRESHOLD and caps
    # are reached.
    finalize_failure_called.assert_awaited_once()
    finalize_scoring_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_small_net_phase2_requests_additional_comparisons_before_resampling_cap(
    monkeypatch: Any,
) -> None:
    """Small-net Phase 2 should prefer resampling to immediate finalization.

    Behavioural spec for PR-7 Phase-2 semantics (not PR-2):
    - For nets with n_essays < MIN_RESAMPLING_NET_SIZE and unique coverage
      complete (every unordered pair seen at least once), continuation
      should keep requesting additional comparisons (resampling existing
      pairs) while:
        * Stability has not passed
        * Global budget remains
        * resampling_pass_count < MAX_RESAMPLING_PASSES_FOR_SMALL_NET
    - This test encodes that expectation for a 3-essay batch; the metadata
      fields (successful_pairs_count, max_possible_pairs,
      unique_coverage_complete, resampling_pass_count) illustrate the
      future contract.
    - Under current PR-2 semantics, callbacks reaching
      completion_denominator() cause immediate finalization instead of
      resampling, so this assertion fails and the test remains xfail as a
      forward-looking spec.
    """

    # Settings including future small-net guards
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 100
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 3
    settings.SCORE_STABILITY_THRESHOLD = 0.01
    settings.MIN_SUCCESS_RATE_THRESHOLD = 0.0
    # Future Phase-2 knobs (not yet used in implementation)
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
        # Coverage metadata for future semantics
        "successful_pairs_count": 3,
        "max_possible_pairs": 3,
        "unique_coverage_complete": True,
        "resampling_pass_count": 0,
    }
    # expected_count=3 → nC2 = 3 possible pairs
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

    # Recompute scores; keep stability failing so behaviour is driven by caps
    # and (future) resampling semantics.
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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    # Future Phase-2 behaviour: small nets should request additional
    # comparisons (resampling) before hitting the resampling cap and must
    # not finalize immediately just because caps are reached.
    request_additional.assert_awaited_once()
    finalize_called.assert_not_awaited()


@pytest.mark.asyncio
async def test_small_net_phase2_tracks_resampling_pass_count(monkeypatch: Any) -> None:
    """Small-net Phase 2 should track resampling passes in metadata.

    Forward-looking PR-7 behavioural spec:
    - Once unique coverage is complete for a small net and continuation
      chooses to resample, `resampling_pass_count` should be incremented
      and persisted alongside BT scores for the iteration.
    - This test uses a simplified 3-essay scenario where coverage metadata
      indicates `unique_coverage_complete=True` even though the raw
      counters are not fully aligned; the focus is on the metadata update
      contract, not on exact pair counts.
    - Under current PR-2 semantics, continuation recomputes scores and
      persists only `bt_scores`, `last_scored_iteration`, and
      `last_score_change`, so the expectation on `resampling_pass_count`
      fails and the test remains xfail.
    """

    # Settings including future small-net guards
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

    # Small net: 3 essays, coverage metadata says complete, but we keep
    # callback counters below the completion denominator so that PR-2
    # semantics still request more comparisons.
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
        # Coverage metadata for future semantics
        "successful_pairs_count": 3,
        "max_possible_pairs": 3,
        "unique_coverage_complete": True,
        "resampling_pass_count": 0,
    }
    # expected_count=3 -> nC2 = 3 possible pairs; callbacks_received=2 < 3
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
        Mock(return_value=0.05),  # > threshold -> not stable
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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    # PR-7 expectation: metadata should reflect that a resampling pass
    # occurred when unique coverage was already complete.
    merge_metadata.assert_awaited_once()
    merge_args = merge_metadata.await_args
    assert merge_args is not None
    metadata_updates = merge_args.kwargs["metadata_updates"]
    assert metadata_updates.get("resampling_pass_count") == 1
    # Small-net Phase-2 semantics must call continuation in RESAMPLING mode.
    request_additional.assert_awaited_once()
    cont_args = request_additional.await_args
    assert cont_args is not None
    assert cont_args.kwargs["mode"] == wc.PairGenerationMode.RESAMPLING


@pytest.mark.asyncio
async def test_small_net_resampling_respects_resampling_pass_cap(monkeypatch: Any) -> None:
    """Small-net Phase 2 should stop resampling once the pass cap is hit.

    Forward-looking PR-7 spec for small nets:
    - When `resampling_pass_count` reaches `MAX_RESAMPLING_PASSES_FOR_SMALL_NET`
      for a net with `n_essays < MIN_RESAMPLING_NET_SIZE`, continuation should
      *not* request additional comparisons even if stability has not passed.
    - Instead, it should finalize (either via scoring or failure), relying on
      the small-net-specific cap rather than continuing to spend budget.
    - Under current PR-2 semantics, the resampling cap is ignored and the
      implementation continues to request additional comparisons while budget
      remains, so this test remains xfail.
    """

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

    class _Finalizer:  # pragma: no cover - future Phase-2 semantics
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_scoring_called()

        async def finalize_failure(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_failure_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

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
    )

    # PR-7 expectation: once the small-net resampling cap is hit, no further
    # resampling requests should be enqueued and the batch should finalize
    # via either scoring or failure.
    assert request_additional.await_count == 0
    total_finalize_calls = finalize_scoring_called.await_count + finalize_failure_called.await_count
    assert total_finalize_calls == 1


@pytest.mark.asyncio
async def test_trigger_continuation_finalizes_on_stability_before_budget(monkeypatch: Any) -> None:
    """Batch should finalize early on stability even when budget remains."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 20
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 12
    batch_state.submitted_comparisons = 10
    batch_state.completed_comparisons = 10
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 10
    batch_state.total_budget = 20  # More budget remains
    batch_state.current_iteration = 2
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 20, "source": "service_default"},
        "bt_scores": {"a": 0.1, "b": -0.1},
    }
    batch_state.batch_upload = _make_upload(expected_count=5)

    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=3,
        )
        for i in range(5)
    ]

    # Recompute scores and report a small max change below threshold
    new_scores = {"a": 0.11, "b": -0.11}
    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value=new_scores),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.01),
    )
    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=12,
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
    )

    finalize_called.assert_awaited_once()
    request_additional.assert_not_awaited()


@pytest.mark.asyncio
async def test_trigger_continuation_finalizes_despite_unfairness(monkeypatch: Any) -> None:
    """Batch SHOULD finalize if stable, even if fairness criteria not met (policy change)."""

    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 20
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    batch_state = CJBatchState()
    batch_state.batch_id = 13
    batch_state.submitted_comparisons = 10
    batch_state.completed_comparisons = 10
    batch_state.failed_comparisons = 0
    batch_state.total_comparisons = 10
    batch_state.total_budget = 20
    batch_state.current_iteration = 2
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 20, "source": "service_default"},
        "bt_scores": {"a": 0.1, "b": -0.1},
    }
    # Increase expected count so budget/cap is not hit (5 essays = 10 pairs, 10 submitted = done)
    # 10 essays = 45 pairs. 10 submitted < 20 budget < 45 cap.
    batch_state.batch_upload = _make_upload(expected_count=10)

    # Mock essays with insufficient comparison counts (min=3 < req=6)
    essays = [
        Mock(
            els_essay_id=str(i),
            assessment_input_text=f"essay-{i}",
            current_bt_score=0.0,
            comparison_count=3,
        )
        for i in range(5)
    ]

    # Recompute scores and report stable
    new_scores = {"a": 0.11, "b": -0.11}
    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value=new_scores),
    )
    monkeypatch.setattr(
        wc.scoring_ranking,
        "check_score_stability",
        Mock(return_value=0.01),
    )
    merge_metadata = AsyncMock()
    monkeypatch.setattr(wc, "merge_batch_processing_metadata", merge_metadata)

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
    async def mock_session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    mock_session_provider = AsyncMock()
    mock_session_provider.session = mock_session_ctx
    mock_batch_repository = AsyncMock()
    mock_batch_repository.get_batch_state = AsyncMock(return_value=batch_state)
    mock_essay_repository = AsyncMock()
    mock_essay_repository.get_essays_for_cj_batch = AsyncMock(return_value=essays)

    mock_grade_projector = AsyncMock()
    mock_matching_strategy = make_real_matching_strategy_mock()

    await wc.trigger_existing_workflow_continuation(
        batch_id=13,
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
    )

    # Should finalize now (request_additional NOT called)
    finalize_called.assert_awaited_once()
    request_additional.assert_not_awaited()

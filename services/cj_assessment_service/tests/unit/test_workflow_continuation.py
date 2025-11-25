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
    "metadata,max_pairs_expected,enforce_full_budget",
    [
        (
            {"comparison_budget": {"max_pairs_requested": 120, "source": "runner_override"}},
            120,
            True,
        ),
        (
            {"comparison_budget": {"max_pairs_requested": 75, "source": "service_default"}},
            75,
            False,
        ),
        (None, 150, False),
        (
            {"comparison_budget": {"max_pairs_requested": 0, "source": "service_default"}},
            150,
            False,
        ),
    ],
)
def test_resolve_comparison_budget(
    metadata: dict[str, Any] | None, max_pairs_expected: int, enforce_full_budget: bool
) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 150

    max_pairs, enforce_budget = wc._resolve_comparison_budget(metadata, settings)

    assert max_pairs == max_pairs_expected
    assert enforce_budget is enforce_full_budget


@pytest.mark.asyncio
async def test_trigger_continuation_finalizes_when_callbacks_hit_cap(monkeypatch: Any) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 150
    settings.MIN_COMPARISONS_FOR_STABILITY_CHECK = 5
    settings.SCORE_STABILITY_THRESHOLD = 0.05

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

    essays = [
        Mock(els_essay_id=str(i), assessment_input_text=f"essay-{i}", current_bt_score=0.0)
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
        Mock(els_essay_id=str(i), assessment_input_text=f"essay-{i}", current_bt_score=0.0)
        for i in range(2)
    ]

    current_scores = {"essay-1": 0.2, "essay-2": -0.2}
    monkeypatch.setattr(
        wc.scoring_ranking,
        "record_comparisons_and_update_scores",
        AsyncMock(return_value=current_scores),
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
        grade_projector=mock_grade_projector,
    )

    merge_metadata.assert_awaited_once()
    await_args = merge_metadata.await_args
    assert await_args is not None
    metadata_updates = await_args.kwargs["metadata_updates"]
    assert metadata_updates["last_score_change"] is None
    # Ensure metadata can be JSON serialized without Infinity/NaN
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
        Mock(els_essay_id=str(i), assessment_input_text=f"essay-{i}", current_bt_score=0.0)
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
        grade_projector=mock_grade_projector,
    )

    request_additional.assert_awaited_once()
    finalize_called.assert_not_awaited()

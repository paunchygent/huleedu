"""Unit tests for workflow_continuation.check_workflow_continuation.

Validates periodic and threshold-based continuation logic with minimal mocks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_db import AssessmentInstruction, CJBatchState
from services.cj_assessment_service.protocols import CJRepositoryProtocol
from services.cj_assessment_service.tests.unit.instruction_store import AssessmentInstructionStore


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
async def _session_ctx(session: _FakeSession) -> AsyncIterator[_FakeSession]:
    yield session


class _Repo(CJRepositoryProtocol):
    def __init__(self, session: _FakeSession) -> None:
        self._session = session
        self._instruction_store = AssessmentInstructionStore()

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

    async def store_comparison_results(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_essay_scores_in_batch(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def update_cj_batch_status(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def get_final_cj_rankings(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

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


@pytest.mark.asyncio
async def test_check_continuation_periodic_every_5(monkeypatch: Any) -> None:
    # Arrange: 10 completed out of 100 => periodic rule applies (every 5)
    session = _FakeSession(completed_count=10)
    repo = _Repo(session)

    batch_state = CJBatchState()
    batch_state.batch_id = 1
    batch_state.total_comparisons = 100
    batch_state.completion_threshold_pct = 95

    async def _fake_get_batch_state(
        _s: Any, _bid: int, _cid: Any, _for_update: bool = False
    ) -> Any:
        return batch_state

    monkeypatch.setattr(wc, "get_batch_state", _fake_get_batch_state)

    # Act
    should_continue = await wc.check_workflow_continuation(
        batch_id=1, database=repo, correlation_id=uuid4()
    )

    # Assert
    assert should_continue is True


@pytest.mark.asyncio
async def test_check_continuation_threshold(monkeypatch: Any) -> None:
    # Arrange: 18/20 => 90% completed, threshold set to 80 => continuation by threshold
    session = _FakeSession(completed_count=18)
    repo = _Repo(session)

    batch_state = CJBatchState()
    batch_state.batch_id = 2
    batch_state.total_comparisons = 20
    batch_state.completion_threshold_pct = 80

    async def _fake_get_batch_state(
        _s: Any, _bid: int, _cid: Any, _for_update: bool = False
    ) -> Any:
        return batch_state

    monkeypatch.setattr(wc, "get_batch_state", _fake_get_batch_state)

    # Act
    should_continue = await wc.check_workflow_continuation(
        batch_id=2, database=repo, correlation_id=uuid4()
    )

    # Assert
    assert should_continue is True


@pytest.mark.asyncio
async def test_check_continuation_false(monkeypatch: Any) -> None:
    # Arrange: 3/20 => 15%, below periodic rule and below threshold
    session = _FakeSession(completed_count=3)
    repo = _Repo(session)

    batch_state = CJBatchState()
    batch_state.batch_id = 3
    batch_state.total_comparisons = 20
    batch_state.completion_threshold_pct = 95

    async def _fake_get_batch_state(
        _s: Any, _bid: int, _cid: Any, _for_update: bool = False
    ) -> Any:
        return batch_state

    monkeypatch.setattr(wc, "get_batch_state", _fake_get_batch_state)

    # Act
    should_continue = await wc.check_workflow_continuation(
        batch_id=3, database=repo, correlation_id=uuid4()
    )

    # Assert
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
        (None, 350, False),
        (
            {"comparison_budget": {"max_pairs_requested": 0, "source": "service_default"}},
            350,
            False,
        ),
    ],
)
def test_resolve_comparison_budget(
    metadata: dict[str, Any] | None, max_pairs_expected: int, enforce_full_budget: bool
) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 350

    max_pairs, enforce_budget = wc._resolve_comparison_budget(metadata, settings)

    assert max_pairs == max_pairs_expected
    assert enforce_budget is enforce_full_budget


@pytest.mark.asyncio
async def test_trigger_continuation_enqueues_additional_pairs(monkeypatch: Any) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 500
    repo = _Repo(_FakeSession(completed_count=15))
    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    async def fake_completion_conditions(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(wc, "check_batch_completion_conditions", fake_completion_conditions)

    batch_state = Mock()
    batch_state.total_comparisons = 40
    batch_state.completion_threshold_pct = 95
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 100, "source": "runner_override"},
        "config_overrides": {"batch_size": 25},
        "llm_overrides": {"model_override": "claude"},
        "original_request": {
            "assignment_id": "assignment-123",
            "language": "en",
            "course_code": "ENG5",
            "max_comparisons_override": 175,
        },
    }

    async def fake_get_batch_state(*_args: Any, **_kwargs: Any) -> Any:
        return batch_state

    monkeypatch.setattr(wc, "get_batch_state", fake_get_batch_state)

    class _Checker:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def check_batch_completion(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    monkeypatch.setattr(wc, "BatchCompletionChecker", _Checker)

    finalizer_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalizer_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    request_additional = AsyncMock(return_value=True)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    await wc.trigger_existing_workflow_continuation(
        batch_id=7,
        database=repo,
        event_publisher=event_publisher,
        settings=settings,
        content_client=content_client,
        correlation_id=uuid4(),
        llm_interaction=llm_interaction,
    )

    request_additional.assert_awaited_once()
    assert request_additional.await_args is not None
    _, kwargs = request_additional.await_args
    assert kwargs["config_overrides_payload"] == {"batch_size": 25}
    assert kwargs["llm_overrides_payload"] == {"model_override": "claude"}
    assert kwargs["original_request_payload"] == batch_state.processing_metadata["original_request"]
    finalizer_called.assert_not_called()


@pytest.mark.asyncio
async def test_trigger_continuation_finalizes_when_budget_exhausted(monkeypatch: Any) -> None:
    settings = Mock(spec=Settings)
    settings.MAX_PAIRWISE_COMPARISONS = 200
    repo = _Repo(_FakeSession(completed_count=50))
    event_publisher = AsyncMock()
    content_client = AsyncMock()
    llm_interaction = AsyncMock()

    async def fake_completion_conditions(*_args: Any, **_kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(wc, "check_batch_completion_conditions", fake_completion_conditions)

    batch_state = Mock()
    batch_state.total_comparisons = 200
    batch_state.completion_threshold_pct = 95
    batch_state.processing_metadata = {
        "comparison_budget": {"max_pairs_requested": 200, "source": "service_default"},
    }

    async def fake_get_batch_state(*_args: Any, **_kwargs: Any) -> Any:
        return batch_state

    monkeypatch.setattr(wc, "get_batch_state", fake_get_batch_state)

    class _Checker:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def check_batch_completion(self, *_args: Any, **_kwargs: Any) -> bool:
            return False

    monkeypatch.setattr(wc, "BatchCompletionChecker", _Checker)

    finalize_called = AsyncMock()

    class _Finalizer:
        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            pass

        async def finalize_scoring(self, *_args: Any, **_kwargs: Any) -> None:
            await finalize_called()

    monkeypatch.setattr(wc, "BatchFinalizer", _Finalizer)

    request_additional = AsyncMock(return_value=False)
    monkeypatch.setattr(
        wc.comparison_processing,
        "request_additional_comparisons_for_batch",
        request_additional,
    )

    await wc.trigger_existing_workflow_continuation(
        batch_id=9,
        database=repo,
        event_publisher=event_publisher,
        settings=settings,
        content_client=content_client,
        correlation_id=uuid4(),
        llm_interaction=llm_interaction,
    )

    request_additional.assert_not_awaited()
    finalize_called.assert_awaited_once()

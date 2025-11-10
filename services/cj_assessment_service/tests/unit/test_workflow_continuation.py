"""Unit tests for workflow_continuation.check_workflow_continuation.

Validates periodic and threshold-based continuation logic with minimal mocks.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator
from uuid import uuid4

import pytest

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
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
    ) -> AssessmentInstruction:
        return self._instruction_store.upsert(
            assignment_id=assignment_id,
            course_id=course_id,
            instructions_text=instructions_text,
            grade_scale=grade_scale,
            student_prompt_storage_id=student_prompt_storage_id,
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

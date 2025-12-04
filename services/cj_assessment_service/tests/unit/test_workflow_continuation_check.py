"""Unit tests for check_workflow_continuation and comparison budget resolution.

These tests cover the small, pure continuation-gate helper and its immediate
dependency on batch state counters and comparison budget metadata.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, AsyncContextManager, AsyncGenerator, cast
from uuid import uuid4

import pytest
from common_core.status_enums import CJBatchStateEnum as CoreCJBatchStateEnum
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import workflow_continuation as wc
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
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


class _Repo(CJBatchRepositoryProtocol):
    def __init__(self, session: _FakeSession, batch_state: CJBatchState | None = None) -> None:
        self._session = session
        self._instruction_store = AssessmentInstructionStore()
        self._batch_state = batch_state

    def session(self) -> Any:
        return _session_ctx(self._session)

    async def get_batch_state(
        self, session: Any, cj_batch_id: int, *, for_update: bool = False
    ) -> CJBatchState | None:
        return self._batch_state

    async def get_stuck_batches(
        self,
        session: Any,
        states: list[CoreCJBatchStateEnum],
        stuck_threshold: datetime,
    ) -> list[CJBatchState]:
        return []

    async def get_batches_ready_for_completion(
        self,
        session: Any,
    ) -> list[CJBatchState]:
        return []

    async def get_batch_state_for_update(
        self,
        session: Any,
        batch_id: int,
        for_update: bool = False,
    ) -> CJBatchState | None:
        return None

    # Unused abstract methods for these tests
    async def create_new_cj_batch(
        self,
        session: Any,
        bos_batch_id: str,
        event_correlation_id: str,
        language: str,
        course_code: str,
        initial_status: Any,
        expected_essay_count: int,
        user_id: str | None = None,
        org_id: str | None = None,
    ) -> Any:
        return None

    async def get_cj_batch_upload(
        self,
        session: Any,
        cj_batch_id: int,
    ) -> Any | None:
        return None

    async def update_cj_batch_status(
        self,
        session: Any,
        cj_batch_id: int,
        status: Any,
    ) -> None:
        return None

    async def update_batch_state(
        self,
        session: Any,
        batch_id: int,
        state: CoreCJBatchStateEnum,
    ) -> None:
        return None


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
    settings = Settings()
    settings.MAX_PAIRWISE_COMPARISONS = 150

    max_pairs = wc._resolve_comparison_budget(metadata, settings)

    assert max_pairs == max_pairs_expected

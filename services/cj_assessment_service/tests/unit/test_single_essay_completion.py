"""Unit tests for single-essay completion finalizer.

Verifies that batches with fewer than 2 student essays are finalized
without comparisons, with proper status updates and event publishing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.events.cj_assessment_events import GradeProjectionSummary
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.batch_finalizer import (
    BatchFinalizer,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload, ProcessedEssay
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
)


@asynccontextmanager
async def session_ctx(session: AsyncMock) -> AsyncIterator[AsyncMock]:
    yield session


class RepoMock(CJRepositoryProtocol):
    def __init__(self, session: AsyncMock, essays: list[ProcessedEssay]) -> None:
        self._session = session
        self._essays = essays
        self.status_updates: list[tuple[int, CJBatchStatusEnum]] = []
        self.score_updates: list[dict[str, float]] = []

    def session(self) -> Any:
        return session_ctx(self._session)

    async def get_essays_for_cj_batch(self, session: Any, cj_batch_id: int) -> list[Any]:
        return self._essays

    async def update_cj_batch_status(self, session: Any, cj_batch_id: int, status: Any) -> None:
        self.status_updates.append((cj_batch_id, status))

    async def update_essay_scores_in_batch(
        self, session: Any, cj_batch_id: int, scores: dict[str, float]
    ) -> None:
        self.score_updates.append(scores)

    # Unused protocol methods for this test
    async def get_assessment_instruction(
        self, session: Any, assignment_id: str | None, course_id: str | None
    ) -> Any | None:  # noqa: E501
        return None

    async def get_cj_batch_upload(self, session: Any, cj_batch_id: int) -> Any | None:
        return self._session._batch

    async def get_assignment_context(
        self,
        session: Any,
        assignment_id: str,
    ) -> dict[str, Any] | None:
        return {
            "assignment_id": assignment_id,
            "instructions_text": "Mock",
            "grade_scale": "swedish_8_anchor",
        }

    async def get_anchor_essay_references(
        self,
        session: Any,
        assignment_id: str,
        grade_scale: str | None = None,
    ) -> list[Any]:
        return []

    async def store_grade_projections(self, session: Any, projections: list[Any]) -> None:
        return None

    async def create_new_cj_batch(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def create_or_update_cj_processed_essay(self, *args: Any, **kwargs: Any) -> Any:
        return None

    async def get_comparison_pair_by_essays(self, *args: Any, **kwargs: Any) -> Any | None:
        return None

    async def store_comparison_results(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def get_final_cj_rankings(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return []

    async def initialize_db_schema(self) -> None:
        return None


@pytest.mark.asyncio
async def test_finalize_single_essay_publishes_and_updates(monkeypatch: Any) -> None:
    # Arrange
    correlation_id = uuid4()

    batch = CJBatchUpload()
    batch.id = 101
    batch.bos_batch_id = "bos-xyz"
    batch.event_correlation_id = str(correlation_id)
    batch.language = "sv"
    batch.course_code = "SV2"
    batch.essay_instructions = "Assess writing"
    batch.expected_essay_count = 1
    batch.status = CJBatchStatusEnum.PENDING
    batch.created_at = datetime.now(UTC)
    batch.user_id = "test-user"
    batch.org_id = "test-org"
    batch.assignment_id = None

    essay = ProcessedEssay()
    essay.els_essay_id = "student_1"
    essay.cj_batch_id = batch.id
    essay.assessment_input_text = "Lorem ipsum"
    essay.is_anchor = False
    essay.current_bt_score = None

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = batch
    repo = RepoMock(session, [essay])

    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    content_client = AsyncMock(spec=ContentClientProtocol)

    # Settings required by publisher
    settings = Mock(spec=Settings)
    settings.SERVICE_NAME = "cj_assessment_service"
    settings.CJ_ASSESSMENT_COMPLETED_TOPIC = "processing.cj.assessment.completed.v1"
    settings.ASSESSMENT_RESULT_TOPIC = "processing.assessment.result.v1"
    settings.DEFAULT_LLM_MODEL = "test-model"
    settings.DEFAULT_LLM_PROVIDER = Mock(value="test-provider")
    settings.DEFAULT_LLM_TEMPERATURE = 0.0

    # Mock ranking and projections to avoid heavy dependencies
    from services.cj_assessment_service.cj_core_logic import batch_finalizer as bf

    class _FakeSR:
        async def get_essay_rankings(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            return [
                {
                    "rank": 1,
                    "els_essay_id": "student_1",
                    "bradley_terry_score": 0.0,
                    "bradley_terry_se": None,
                    "comparison_count": 0,
                    "is_anchor": False,
                }
            ]

    class _FakeGP:
        class GradeProjector:
            async def calculate_projections(
                self, *args: Any, **kwargs: Any
            ) -> GradeProjectionSummary:
                return GradeProjectionSummary(
                    projections_available=False,
                    primary_grades={},
                    confidence_labels={},
                    confidence_scores={},
                )

    monkeypatch.setattr(bf, "scoring_ranking", _FakeSR())
    monkeypatch.setattr(bf, "grade_projector", _FakeGP())

    log_extra = {"correlation_id": str(correlation_id)}

    # Act
    finalizer = BatchFinalizer(
        database=repo,
        event_publisher=event_publisher,
        content_client=content_client,
        settings=settings,
    )
    await finalizer.finalize_single_essay(
        batch_id=batch.id,
        correlation_id=correlation_id,
        session=session,
        log_extra=log_extra,
    )

    # Assert: status updated, minimal score set, events published
    assert repo.status_updates[-1][1] == CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS
    assert any(
        "student_1" in scores and scores["student_1"] == 0.0 for scores in repo.score_updates
    )
    event_publisher.publish_assessment_completed.assert_called_once()
    event_publisher.publish_assessment_result.assert_called_once()

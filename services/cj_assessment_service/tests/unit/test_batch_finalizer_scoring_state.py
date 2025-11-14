"""Unit tests for the scoring finalizer flow."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.status_enums import CJBatchStateEnum as CoreCJState

from services.cj_assessment_service.cj_core_logic import batch_finalizer as bf
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
)


@pytest.mark.asyncio
async def test_finalize_scoring_transitions_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoring finalization should move the CJ state machine into SCORING -> COMPLETED."""

    repo = AsyncMock(spec=CJRepositoryProtocol)
    repo.get_essays_for_cj_batch.return_value = [
        SimpleNamespace(els_essay_id="ANCHOR_A", assessment_input_text="A", current_bt_score=0.0),
        SimpleNamespace(els_essay_id="student-1", assessment_input_text="S1", current_bt_score=0.0),
    ]
    repo.update_cj_batch_status = AsyncMock()

    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    content_client = AsyncMock(spec=ContentClientProtocol)
    settings = Mock()

    batch = CJBatchUpload()
    batch.id = 42
    batch.bos_batch_id = "bos-42"
    batch.event_correlation_id = str(uuid4())
    batch.language = "en"
    batch.course_code = "ENG5"
    batch.expected_essay_count = 2
    batch.status = CJBatchStatusEnum.PERFORMING_COMPARISONS
    batch.created_at = datetime.now(UTC)
    batch.user_id = "user-123"
    batch.org_id = "org-abc"
    batch.assignment_id = "assignment-xyz"

    session = AsyncMock()
    session.get.return_value = batch

    class _FakeScoring:
        async def record_comparisons_and_update_scores(
            self, *args: object, **kwargs: object
        ) -> None:
            return None

        async def get_essay_rankings(
            self, *args: object, **kwargs: object
        ) -> list[dict[str, object]]:
            return [
                {
                    "rank": 1,
                    "els_essay_id": "ANCHOR_A",
                    "bradley_terry_score": 0.5,
                    "bradley_terry_se": 0.1,
                    "comparison_count": 3,
                    "is_anchor": True,
                },
                {
                    "rank": 2,
                    "els_essay_id": "student-1",
                    "bradley_terry_score": 0.1,
                    "bradley_terry_se": 0.2,
                    "comparison_count": 3,
                    "is_anchor": False,
                },
            ]

    class _FakeGradeProjector:
        class GradeProjector:  # noqa: D401 - mimic real projector signature
            async def calculate_projections(
                self, *args: object, **kwargs: object
            ) -> GradeProjectionSummary:
                return GradeProjectionSummary(
                    projections_available=True,
                    primary_grades={"student-1": "C"},
                    confidence_labels={"student-1": "medium"},
                    confidence_scores={"student-1": 0.64},
                )

    publish_mock = AsyncMock()
    update_state_mock = AsyncMock()

    monkeypatch.setattr(bf, "scoring_ranking", _FakeScoring())
    monkeypatch.setattr(bf, "grade_projector", _FakeGradeProjector())
    monkeypatch.setattr(bf, "publish_dual_assessment_events", publish_mock)
    monkeypatch.setattr(bf, "update_batch_state_in_session", update_state_mock)

    finalizer = BatchFinalizer(
        database=repo,
        event_publisher=event_publisher,
        content_client=content_client,
        settings=settings,
    )

    correlation_id = uuid4()
    log_extra = {"correlation_id": str(correlation_id)}

    await finalizer.finalize_scoring(
        batch_id=batch.id,
        correlation_id=correlation_id,
        session=session,
        log_extra=log_extra,
    )

    assert publish_mock.await_count == 1
    assert repo.update_cj_batch_status.await_count == 1

    assert update_state_mock.await_count == 2
    first_call_state = update_state_mock.await_args_list[0].kwargs["state"]
    second_call_state = update_state_mock.await_args_list[1].kwargs["state"]

    assert first_call_state == CoreCJState.SCORING
    assert second_call_state == CoreCJState.COMPLETED

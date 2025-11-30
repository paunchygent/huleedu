"""Unit tests for the scoring finalizer flow."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.status_enums import CJBatchStateEnum as CoreCJState
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import batch_finalizer as bf
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.models_db import CJBatchUpload
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)


@pytest.mark.asyncio
async def test_finalize_scoring_transitions_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoring finalization should move the CJ state machine into SCORING -> COMPLETED."""

    # Setup per-aggregate repository mocks
    session_provider = AsyncMock(spec=SessionProviderProtocol)
    batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
    essay_repo = AsyncMock(spec=CJEssayRepositoryProtocol)

    essay_repo.get_essays_for_cj_batch.return_value = [
        SimpleNamespace(
            els_essay_id="ANCHOR_A",
            assessment_input_text="A",
            current_bt_score=0.0,
            is_anchor=True,
        ),
        SimpleNamespace(
            els_essay_id="student-1",
            assessment_input_text="S1",
            current_bt_score=0.0,
            is_anchor=False,
        ),
    ]
    batch_repo.update_cj_batch_status = AsyncMock()
    batch_repo.update_batch_state = AsyncMock()

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

    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = batch
    session_provider.session.return_value.__aenter__.return_value = session
    session_provider.session.return_value.__aexit__.return_value = None

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

    monkeypatch.setattr(bf, "scoring_ranking", _FakeScoring())
    monkeypatch.setattr(bf, "publish_dual_assessment_events", publish_mock)

    from services.cj_assessment_service.cj_core_logic.grade_projector import (
        GradeProjector,
    )

    grade_projector = AsyncMock(spec=GradeProjector)
    finalizer = BatchFinalizer(
        session_provider=session_provider,
        batch_repository=batch_repo,
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        essay_repository=essay_repo,
        event_publisher=event_publisher,
        content_client=content_client,
        settings=settings,
        grade_projector=grade_projector,
    )

    correlation_id = uuid4()
    log_extra = {"correlation_id": str(correlation_id)}

    await finalizer.finalize_scoring(
        batch_id=batch.id,
        correlation_id=correlation_id,
        log_extra=log_extra,
    )

    publish_mock.assert_awaited_once()

    publish_call = cast(Any, publish_mock.await_args)
    publish_kwargs = publish_call.kwargs

    # Rankings and projections should be passed through, along with a rich publishing DTO
    assert isinstance(publish_kwargs["rankings"], list)
    assert publish_kwargs["grade_projections"] is not None

    publishing_data = publish_kwargs["publishing_data"]
    assert isinstance(publishing_data, bf.DualEventPublishingData)
    assert publishing_data.bos_batch_id == batch.bos_batch_id
    assert publishing_data.cj_batch_id == str(batch.id)
    assert publishing_data.assignment_id == batch.assignment_id
    assert publishing_data.course_code == batch.course_code
    assert publishing_data.user_id == batch.user_id
    assert publishing_data.org_id == batch.org_id

    # Correlation ID used for publishing should match the original BOS correlation threading
    assert publish_kwargs["correlation_id"] == UUID(batch.event_correlation_id)
    assert batch_repo.update_batch_state.await_count == 2
    batch_repo.update_batch_state.assert_any_await(
        session=session,
        batch_id=batch.id,
        state=CoreCJState.SCORING,
    )
    batch_repo.update_batch_state.assert_any_await(
        session=session,
        batch_id=batch.id,
        state=CoreCJState.COMPLETED,
    )
    assert batch_repo.update_cj_batch_status.await_count == 1

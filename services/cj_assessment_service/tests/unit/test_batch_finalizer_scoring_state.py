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
    # Batch-level completion timestamp should be recorded on successful finalization
    assert batch.completed_at is not None


@pytest.mark.asyncio
async def test_finalize_scoring_event_parity_for_forced_recovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced-recovery and callback-driven paths publish identical completion events.

    For the same underlying batch metadata and rankings/projections, the dual-event
    publisher should receive identical payloads regardless of whether finalization
    is invoked from the normal continuation path or from BatchMonitor's forced
    recovery path (COMPLETE_FORCED_RECOVERY).
    """

    # Shared mocks for repositories and dependencies
    session_provider = AsyncMock(spec=SessionProviderProtocol)
    batch_repo = AsyncMock(spec=CJBatchRepositoryProtocol)
    essay_repo = AsyncMock(spec=CJEssayRepositoryProtocol)
    comparison_repo = AsyncMock(spec=CJComparisonRepositoryProtocol)
    event_publisher = AsyncMock(spec=CJEventPublisherProtocol)
    content_client = AsyncMock(spec=ContentClientProtocol)
    settings = Mock()

    # Two separate batch uploads with identical business fields but different ids
    base_correlation_id = str(uuid4())

    batch_normal = CJBatchUpload()
    batch_normal.id = 101
    batch_normal.bos_batch_id = "bos-101"
    batch_normal.event_correlation_id = base_correlation_id
    batch_normal.language = "en"
    batch_normal.course_code = "ENG5"
    batch_normal.expected_essay_count = 2
    batch_normal.status = CJBatchStatusEnum.PERFORMING_COMPARISONS
    batch_normal.created_at = datetime.now(UTC)
    batch_normal.user_id = "user-123"
    batch_normal.org_id = "org-abc"
    batch_normal.assignment_id = "assignment-xyz"

    batch_forced = CJBatchUpload()
    # Same logical batch id and BOS batch id, but represented as a fresh object
    batch_forced.id = batch_normal.id
    batch_forced.bos_batch_id = "bos-101"
    batch_forced.event_correlation_id = base_correlation_id
    batch_forced.language = "en"
    batch_forced.course_code = "ENG5"
    batch_forced.expected_essay_count = 2
    batch_forced.status = CJBatchStatusEnum.PERFORMING_COMPARISONS
    batch_forced.created_at = batch_normal.created_at
    batch_forced.user_id = batch_normal.user_id
    batch_forced.org_id = batch_normal.org_id
    batch_forced.assignment_id = batch_normal.assignment_id

    session = AsyncMock(spec=AsyncSession)
    session.get.side_effect = [batch_normal, batch_forced]
    session_provider.session.return_value.__aenter__.return_value = session
    session_provider.session.return_value.__aexit__.return_value = None

    # Essays returned for scoring (same for both invocations)
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
        comparison_repository=comparison_repo,
        essay_repository=essay_repo,
        event_publisher=event_publisher,
        content_client=content_client,
        settings=settings,
        grade_projector=grade_projector,
    )

    # First: callback-driven path (default COMPLETE_STABLE semantics)
    correlation_id_normal = uuid4()
    await finalizer.finalize_scoring(
        batch_id=batch_normal.id,
        correlation_id=correlation_id_normal,
        log_extra={"correlation_id": str(correlation_id_normal)},
    )

    # Second: forced recovery path via BatchMonitor delegation
    correlation_id_forced = uuid4()
    await finalizer.finalize_scoring(
        batch_id=batch_forced.id,
        correlation_id=correlation_id_forced,
        log_extra={"correlation_id": str(correlation_id_forced)},
        completion_status=CJBatchStatusEnum.COMPLETE_FORCED_RECOVERY,
        source="batch_monitor_forced_recovery",
    )

    # We expect two publish calls with identical payloads for rankings, projections,
    # publishing_data, correlation_id, and processing_started_at.
    assert publish_mock.await_count == 2
    first_call, second_call = publish_mock.await_args_list

    first_kwargs = first_call.kwargs
    second_kwargs = second_call.kwargs

    assert first_kwargs["rankings"] == second_kwargs["rankings"]
    assert first_kwargs["grade_projections"] == second_kwargs["grade_projections"]

    first_publishing = first_kwargs["publishing_data"]
    second_publishing = second_kwargs["publishing_data"]
    assert isinstance(first_publishing, bf.DualEventPublishingData)
    assert isinstance(second_publishing, bf.DualEventPublishingData)

    # Publishing DTO fields must match between the two paths
    assert first_publishing.bos_batch_id == second_publishing.bos_batch_id
    assert first_publishing.cj_batch_id == second_publishing.cj_batch_id
    assert first_publishing.assignment_id == second_publishing.assignment_id
    assert first_publishing.course_code == second_publishing.course_code
    assert first_publishing.user_id == second_publishing.user_id
    assert first_publishing.org_id == second_publishing.org_id
    assert first_publishing.created_at == second_publishing.created_at
    assert first_publishing.llm_model_used == second_publishing.llm_model_used
    assert first_publishing.llm_provider_used == second_publishing.llm_provider_used

    # Correlation id and processing_started_at should also align
    assert first_kwargs["correlation_id"] == second_kwargs["correlation_id"]
    assert first_kwargs["processing_started_at"] == second_kwargs["processing_started_at"]

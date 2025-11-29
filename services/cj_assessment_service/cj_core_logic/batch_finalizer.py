"""Batch finalization logic for CJ Assessment Service.

Provides a single, cohesive module for completing batches in two modes:
- scoring: standard path after comparisons and callbacks
- single_essay: fast path for <2 student essays (no comparisons)

This keeps callback handling and workflow orchestration small and focused
while centralizing completion responsibilities (DB state, rankings,
grade projections, and dual event publishing via outbox).
"""

from __future__ import annotations

import types
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import CJAssessmentFailedV1
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from common_core.status_enums import CJBatchStateEnum as CoreCJState
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.grade_projector import (
        GradeProjector as GradeProjectorType,
    )

logger = create_service_logger("cj_assessment_service.batch_finalizer")


# Lazy imports to avoid scipy/coverage conflicts at module import time
scoring_ranking: types.ModuleType | None = None


class BatchFinalizer:
    """Finalize CJ assessment batches and publish completion events."""

    def __init__(
        self,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        essay_repository: CJEssayRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        content_client: ContentClientProtocol,
        settings: Settings,
        grade_projector: GradeProjectorType,
    ) -> None:
        self._session_provider = session_provider
        self._batch_repo = batch_repository
        self._comparison_repo = comparison_repository
        self._essay_repo = essay_repository
        self._publisher = event_publisher
        self._content = content_client
        self._settings = settings
        self._grade_projector = grade_projector

    async def finalize_scoring(
        self,
        batch_id: int,
        correlation_id: UUID,
        log_extra: dict[str, Any],
    ) -> None:
        """Finalize standard scoring path and publish events."""
        global scoring_ranking
        if scoring_ranking is None:
            from services.cj_assessment_service.cj_core_logic import scoring_ranking as _sr

            scoring_ranking = _sr

        async with self._session_provider.session() as session:
            try:
                # Get batch upload for BOS batch ID and correlation threading
                from services.cj_assessment_service.models_db import CJBatchUpload

                batch_upload = await session.get(CJBatchUpload, batch_id)
                if not batch_upload:
                    logger.error(
                        "Batch upload not found for scoring finalization",
                        extra={**log_extra, "batch_id": batch_id},
                    )
                    return

                # Idempotency guard: if terminal, skip
                status_str = str(batch_upload.status)
                if status_str.startswith("COMPLETE") or status_str.startswith("ERROR"):
                    logger.info(
                        "Batch already terminal, skipping finalization",
                        extra={**log_extra, "batch_id": batch_id, "status": status_str},
                    )
                    return

                # Transition the CJ state machine into SCORING once finalization starts
                await self._batch_repo.update_batch_state(
                    session=session,
                    batch_id=batch_id,
                    state=CoreCJState.SCORING,
                )
                await session.commit()

                # Get essays for scoring
                essays = await self._essay_repo.get_essays_for_cj_batch(
                    session=session, cj_batch_id=batch_id
                )
                from services.cj_assessment_service.models_api import EssayForComparison

                essays_for_api = [
                    EssayForComparison(
                        id=essay.els_essay_id,
                        text_content=essay.assessment_input_text,
                        current_bt_score=essay.current_bt_score,
                        is_anchor=essay.is_anchor,
                    )
                    for essay in essays
                ]

                # Compute Bradley-Terry scores (comparison data is already in DB)
                assert scoring_ranking is not None
                await scoring_ranking.record_comparisons_and_update_scores(
                    all_essays=essays_for_api,
                    comparison_results=[],
                    session_provider=self._session_provider,
                    comparison_repository=self._comparison_repo,
                    essay_repository=self._essay_repo,
                    cj_batch_id=batch_id,
                    correlation_id=correlation_id,
                )

                # Mark batch as complete (stable)
                await self._batch_repo.update_cj_batch_status(
                    session=session,
                    cj_batch_id=batch_id,
                    status=CJBatchStatusEnum.COMPLETE_STABLE,
                )

                # Rankings and grade projections
                rankings = await scoring_ranking.get_essay_rankings(
                    self._session_provider, self._essay_repo, batch_id, correlation_id
                )
                grade_projections = await self._grade_projector.calculate_projections(
                    rankings=rankings,
                    cj_batch_id=batch_id,
                    assignment_id=(
                        batch_upload.assignment_id
                        if hasattr(batch_upload, "assignment_id")
                        else None
                    ),
                    course_code=(
                        batch_upload.course_code if hasattr(batch_upload, "course_code") else ""
                    ),
                    content_client=self._content,
                    correlation_id=correlation_id,
                )

                # Use original correlation_id from batch for publishing
                original_correlation_id = UUID(batch_upload.event_correlation_id)

                # Identity threading must be present
                if not batch_upload.user_id:
                    raise ValueError(
                        f"user_id is None for batch {batch_upload.id} - identity threading failed"
                    )

                publishing_data = DualEventPublishingData(
                    bos_batch_id=batch_upload.bos_batch_id,
                    cj_batch_id=str(batch_upload.id),
                    assignment_id=batch_upload.assignment_id,
                    course_code=batch_upload.course_code,
                    user_id=batch_upload.user_id,
                    org_id=batch_upload.org_id,
                    created_at=batch_upload.created_at,
                )

                await publish_dual_assessment_events(
                    rankings=rankings,
                    grade_projections=grade_projections,
                    publishing_data=publishing_data,
                    event_publisher=self._publisher,
                    settings=self._settings,
                    correlation_id=original_correlation_id,
                    processing_started_at=batch_upload.created_at,
                )

                # Mark the workflow as complete in the fine-grained CJ state machine
                await self._batch_repo.update_batch_state(
                    session=session,
                    batch_id=batch_id,
                    state=CoreCJState.COMPLETED,
                )
                await session.commit()

                logger.info(
                    "Completed scoring finalization for batch",
                    extra={**log_extra, "batch_id": batch_id, "essay_count": len(essays)},
                )

            except Exception as e:
                logger.error(
                    f"Failed scoring finalization: {e}",
                    extra={**log_extra, "batch_id": batch_id, "error_type": type(e).__name__},
                    exc_info=True,
                )
                try:
                    await self._batch_repo.update_cj_batch_status(
                        session=session,
                        cj_batch_id=batch_id,
                        status=CJBatchStatusEnum.ERROR_PROCESSING,
                    )
                except Exception:
                    # Best-effort; avoid masking original error
                    pass

    async def finalize_failure(
        self,
        batch_id: int,
        correlation_id: UUID,
        log_extra: dict[str, Any],
        *,
        failure_reason: str,
        failure_details: dict[str, Any] | None = None,
    ) -> None:
        """Finalize a batch in FAILED state for high failure-rate scenarios.

        This path is used by PR-2 semantics when all attempts are exhausted but
        the success rate is too low (including zero successful comparisons).
        It marks the batch as ERROR_* in CJBatchUpload, sets the fine-grained
        CJBatchState to FAILED, and publishes a CJAssessmentFailedV1 event.
        """
        async with self._session_provider.session() as session:
            from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload

            batch_upload = await session.get(CJBatchUpload, batch_id)
            if not batch_upload:
                logger.error(
                    "Batch upload not found for failure finalization",
                    extra={**log_extra, "batch_id": batch_id},
                )
                return

            status_str = str(batch_upload.status)
            if status_str.startswith("COMPLETE") or status_str.startswith("ERROR"):
                logger.info(
                    "Batch already terminal, skipping failure finalization",
                    extra={**log_extra, "batch_id": batch_id, "status": status_str},
                )
                return

            batch_state = await session.get(CJBatchState, batch_id)
            if not batch_state:
                logger.error(
                    "Batch state not found for failure finalization",
                    extra={**log_extra, "batch_id": batch_id},
                )
                return

            # Update upload status and fine-grained state
            await self._batch_repo.update_cj_batch_status(
                session=session,
                cj_batch_id=batch_id,
                status=CJBatchStatusEnum.ERROR_PROCESSING,
            )

            batch_state.state = CoreCJState.FAILED
            now = datetime.now(UTC)
            batch_state.last_activity_at = now
            if batch_state.processing_metadata is None:
                batch_state.processing_metadata = {}
            batch_state.processing_metadata.setdefault("failed_reason", {})
            batch_state.processing_metadata["failed_reason"] = {
                "reason": failure_reason,
                "timestamp": now.isoformat(),
                "details": failure_details or {},
            }

            await session.commit()

            # Build and publish thin failure event to ELS via outbox
            failure_event_data = CJAssessmentFailedV1(
                event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                entity_id=batch_upload.bos_batch_id,
                entity_type="batch",
                parent_id=None,
                status=BatchStatus.FAILED_CRITICALLY,
                system_metadata=SystemProcessingMetadata(
                    entity_id=batch_upload.bos_batch_id,
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.FAILED,
                    started_at=batch_upload.created_at,
                    completed_at=datetime.now(UTC),
                    event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                    error_info={
                        "reason": failure_reason,
                        "details": failure_details or {},
                    },
                ),
                cj_assessment_job_id=str(batch_id),
            )

            failure_envelope = EventEnvelope[CJAssessmentFailedV1](
                event_type=self._settings.CJ_ASSESSMENT_FAILED_TOPIC,
                event_timestamp=datetime.now(UTC),
                source_service=self._settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=failure_event_data,
                metadata={},
            )

            if failure_envelope.metadata is not None:
                inject_trace_context(failure_envelope.metadata)

            await self._publisher.publish_assessment_failed(
                failure_data=failure_envelope,
                correlation_id=correlation_id,
            )

    async def finalize_single_essay(
        self,
        batch_id: int,
        correlation_id: UUID,
        log_extra: dict[str, Any],
    ) -> None:
        """Finalize single-essay fast path and publish events."""
        global scoring_ranking
        if scoring_ranking is None:
            from services.cj_assessment_service.cj_core_logic import scoring_ranking as _sr

            scoring_ranking = _sr

        from services.cj_assessment_service.models_db import CJBatchUpload

        async with self._session_provider.session() as session:
            try:
                batch_upload = await session.get(CJBatchUpload, batch_id)
                if not batch_upload:
                    logger.error(
                        "Batch upload not found for single-essay finalization",
                        extra={**log_extra, "batch_id": batch_id},
                    )
                    return

                # Idempotency guard: if terminal, skip
                status_str = str(batch_upload.status)
                if status_str.startswith("COMPLETE") or status_str.startswith("ERROR"):
                    logger.info(
                        "Batch already terminal, skipping finalization",
                        extra={**log_extra, "batch_id": batch_id, "status": status_str},
                    )
                    return

                # Identify student essays
                essays = await self._essay_repo.get_essays_for_cj_batch(
                    session=session, cj_batch_id=batch_id
                )
                student_ids = [e.els_essay_id for e in essays if not getattr(e, "is_anchor", False)]

                # Mark explicit completion status + real-time state
                await self._batch_repo.update_cj_batch_status(
                    session=session,
                    cj_batch_id=batch_id,
                    status=CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS,
                )
                await self._batch_repo.update_batch_state(
                    session=session,
                    batch_id=batch_id,
                    state=CoreCJState.COMPLETED,
                )
                await session.commit()

                # Minimal scoring for single student to map ELS status to success
                if len(student_ids) == 1:
                    await self._essay_repo.update_essay_scores_in_batch(
                        session=session,
                        cj_batch_id=batch_id,
                        scores={student_ids[0]: 0.0},
                    )

                # Rankings and grade projections
                rankings = await scoring_ranking.get_essay_rankings(
                    self._session_provider, self._essay_repo, batch_id, correlation_id
                )
                grade_projections = await self._grade_projector.calculate_projections(
                    rankings=rankings,
                    cj_batch_id=batch_id,
                    assignment_id=(
                        batch_upload.assignment_id
                        if hasattr(batch_upload, "assignment_id")
                        else None
                    ),
                    course_code=(
                        batch_upload.course_code if hasattr(batch_upload, "course_code") else ""
                    ),
                    content_client=self._content,
                    correlation_id=correlation_id,
                )

                original_correlation_id = UUID(batch_upload.event_correlation_id)
                if not batch_upload.user_id:
                    raise ValueError(
                        f"user_id is None for batch {batch_upload.id} - identity threading failed"
                    )

                publishing_data = DualEventPublishingData(
                    bos_batch_id=batch_upload.bos_batch_id,
                    cj_batch_id=str(batch_upload.id),
                    assignment_id=batch_upload.assignment_id,
                    course_code=batch_upload.course_code,
                    user_id=batch_upload.user_id,
                    org_id=batch_upload.org_id,
                    created_at=batch_upload.created_at,
                )

                await publish_dual_assessment_events(
                    rankings=rankings,
                    grade_projections=grade_projections,
                    publishing_data=publishing_data,
                    event_publisher=self._publisher,
                    settings=self._settings,
                    correlation_id=original_correlation_id,
                    processing_started_at=batch_upload.created_at,
                )

                logger.info(
                    "Published completion for single-essay batch",
                    extra={
                        **log_extra,
                        "batch_id": batch_id,
                        "student_essay_count": len(student_ids),
                    },
                )

            except Exception as e:
                logger.error(
                    f"Failed single-essay finalization: {e}",
                    extra={**log_extra, "batch_id": batch_id, "error_type": type(e).__name__},
                    exc_info=True,
                )

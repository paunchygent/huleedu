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
from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
)

if TYPE_CHECKING:
    pass

logger = create_service_logger("cj_assessment_service.batch_finalizer")


# Lazy imports to avoid scipy/coverage conflicts at module import time
scoring_ranking: types.ModuleType | None = None
grade_projector: types.ModuleType | None = None


class BatchFinalizer:
    """Finalize CJ assessment batches and publish completion events."""

    def __init__(
        self,
        database: CJRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        content_client: ContentClientProtocol,
        settings: Settings,
    ) -> None:
        self._db = database
        self._publisher = event_publisher
        self._content = content_client
        self._settings = settings

    async def finalize_scoring(
        self,
        batch_id: int,
        correlation_id: UUID,
        session: Any,  # AsyncSession, left as Any for testability
        log_extra: dict[str, Any],
    ) -> None:
        """Finalize standard scoring path and publish events."""
        global scoring_ranking, grade_projector
        if scoring_ranking is None:
            from services.cj_assessment_service.cj_core_logic import scoring_ranking as _sr

            scoring_ranking = _sr
        if grade_projector is None:
            from services.cj_assessment_service.cj_core_logic import grade_projector as _gp

            grade_projector = _gp

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

            # Get essays for scoring
            essays = await self._db.get_essays_for_cj_batch(session=session, cj_batch_id=batch_id)
            from services.cj_assessment_service.models_api import EssayForComparison

            essays_for_api = [
                EssayForComparison(
                    id=essay.els_essay_id,
                    text_content=essay.assessment_input_text,
                    current_bt_score=essay.current_bt_score,
                )
                for essay in essays
            ]

            # Compute Bradley-Terry scores (comparison data is already in DB)
            assert scoring_ranking is not None
            await scoring_ranking.record_comparisons_and_update_scores(
                all_essays=essays_for_api,
                comparison_results=[],
                db_session=session,
                cj_batch_id=batch_id,
                correlation_id=correlation_id,
            )

            # Mark batch as complete (stable)
            await self._db.update_cj_batch_status(
                session=session,
                cj_batch_id=batch_id,
                status=CJBatchStatusEnum.COMPLETE_STABLE,
            )

            # Rankings and grade projections
            rankings = await scoring_ranking.get_essay_rankings(session, batch_id, correlation_id)
            assert grade_projector is not None
            grade_proj = grade_projector.GradeProjector()
            grade_projections = await grade_proj.calculate_projections(
                session=session,
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
                await self._db.update_cj_batch_status(
                    session=session,
                    cj_batch_id=batch_id,
                    status=CJBatchStatusEnum.ERROR_PROCESSING,
                )
            except Exception:
                # Best-effort; avoid masking original error
                pass

    async def finalize_single_essay(
        self,
        batch_id: int,
        correlation_id: UUID,
        session: Any,  # AsyncSession, left as Any for testability
        log_extra: dict[str, Any],
    ) -> None:
        """Finalize single-essay fast path and publish events."""
        global scoring_ranking, grade_projector
        if scoring_ranking is None:
            from services.cj_assessment_service.cj_core_logic import scoring_ranking as _sr

            scoring_ranking = _sr
        if grade_projector is None:
            from services.cj_assessment_service.cj_core_logic import grade_projector as _gp

            grade_projector = _gp

        from common_core.status_enums import CJBatchStateEnum as CoreCJState

        from services.cj_assessment_service.cj_core_logic.batch_submission import (
            update_batch_state_in_session,
        )
        from services.cj_assessment_service.models_db import CJBatchUpload

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
            essays = await self._db.get_essays_for_cj_batch(session=session, cj_batch_id=batch_id)
            student_ids = [e.els_essay_id for e in essays if not getattr(e, "is_anchor", False)]

            # Mark explicit completion status + real-time state
            await self._db.update_cj_batch_status(
                session=session,
                cj_batch_id=batch_id,
                status=CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS,
            )
            await update_batch_state_in_session(
                session=session,
                cj_batch_id=batch_id,
                state=CoreCJState.COMPLETED,
                correlation_id=correlation_id,
            )

            # Minimal scoring for single student to map ELS status to success
            if len(student_ids) == 1:
                await self._db.update_essay_scores_in_batch(
                    session=session,
                    cj_batch_id=batch_id,
                    scores={student_ids[0]: 0.0},
                )

            # Rankings and grade projections
            rankings = await scoring_ranking.get_essay_rankings(session, batch_id, correlation_id)
            assert grade_projector is not None
            grade_proj = grade_projector.GradeProjector()
            grade_projections = await grade_proj.calculate_projections(
                session=session,
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
                extra={**log_extra, "batch_id": batch_id, "student_essay_count": len(student_ids)},
            )

        except Exception as e:
            logger.error(
                f"Failed single-essay finalization: {e}",
                extra={**log_extra, "batch_id": batch_id, "error_type": type(e).__name__},
                exc_info=True,
            )

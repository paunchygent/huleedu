"""Batch monitoring for stuck batch detection and recovery.

This module implements monitoring of CJ assessment batches to detect
stuck batches and trigger appropriate recovery actions.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.event_enums import ProcessingEvent
from common_core.events.assessment_result_events import AssessmentResultV1
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.envelope import EventEnvelope

# EntityReference removed - using primitive parameters
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from services.cj_assessment_service.cj_core_logic import scoring_ranking
from services.cj_assessment_service.cj_core_logic.grade_projector import (
    GradeProjector,
    calculate_grade_projections,
)
from services.cj_assessment_service.cj_core_logic.grade_utils import _grade_to_normalized
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.protocols import (
        CJEventPublisherProtocol,
        CJRepositoryProtocol,
        ContentClientProtocol,
    )

logger = create_service_logger(__name__)


class BatchMonitor:
    """Monitors CJ assessment batches for stuck/timeout conditions."""

    def __init__(
        self,
        repository: CJRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        content_client: ContentClientProtocol,
        settings: Settings,
    ) -> None:
        """Initialize the batch monitor.

        Args:
            repository: Database access interface
            event_publisher: Event publishing interface
            content_client: Content client for fetching anchor essays
            settings: Service configuration
        """
        self._repository = repository
        self._event_publisher = event_publisher
        self._content_client = content_client
        self._settings = settings

        # Configuration
        self.timeout_hours = settings.BATCH_TIMEOUT_HOURS
        self.monitor_interval_minutes = settings.BATCH_MONITOR_INTERVAL_MINUTES

        # Concurrency control
        self._semaphore = asyncio.Semaphore(3)  # Limit concurrent batch checks
        self._running = True

        # Get metrics from shared module
        business_metrics = get_business_metrics()
        self._stuck_batches_gauge = business_metrics.get("cj_stuck_batches_detected")
        self._stuck_batches_recovered = business_metrics.get("cj_stuck_batches_recovered_total")
        self._stuck_batches_failed = business_metrics.get("cj_stuck_batches_failed_total")

    async def check_stuck_batches(self) -> None:
        """Main monitoring function to detect and handle stuck batches.

        Finds batches with last_activity_at older than timeout threshold
        in GENERATING_PAIRS or WAITING_CALLBACKS states.
        """
        # Initial delay to let the service fully start up
        await asyncio.sleep(30)

        while self._running:
            try:
                # Calculate stuck threshold
                stuck_threshold = datetime.now(UTC) - timedelta(hours=self.timeout_hours)

                # Define monitored states
                monitored_states = [
                    CJBatchStateEnum.GENERATING_PAIRS,
                    CJBatchStateEnum.WAITING_CALLBACKS,
                ]

                async with self._repository.session() as session:
                    # Find potentially stuck batches
                    stmt = (
                        select(CJBatchState)
                        .where(
                            and_(
                                CJBatchState.state.in_(monitored_states),
                                CJBatchState.last_activity_at < stuck_threshold,
                            )
                        )
                        .options(
                            selectinload(CJBatchState.batch_upload)  # Eager load relationship
                        )
                    )

                    result = await session.execute(stmt)
                    stuck_batch_states = result.scalars().all()

                    if stuck_batch_states:
                        stuck_count = len(stuck_batch_states)
                        logger.warning(
                            "Found stuck batches",
                            extra={
                                "stuck_batch_count": stuck_count,
                                "stuck_threshold": stuck_threshold.isoformat(),
                                "monitored_states": [s.value for s in monitored_states],
                            },
                        )

                        # Update gauge metric
                        if self._stuck_batches_gauge:
                            self._stuck_batches_gauge.set(stuck_count)

                        # Process each stuck batch with semaphore limiting
                        tasks = [
                            self._process_stuck_batch(batch_state)
                            for batch_state in stuck_batch_states
                        ]
                        await asyncio.gather(*tasks, return_exceptions=True)
                    else:
                        # No stuck batches found, reset gauge to 0
                        if self._stuck_batches_gauge:
                            self._stuck_batches_gauge.set(0)

            except Exception as e:
                logger.error(
                    "Batch monitoring check failed",
                    extra={"error": str(e), "error_type": type(e).__name__},
                )
                # Continue monitoring after error
                await asyncio.sleep(60)  # Brief pause before retry

            # Sleep for the configured interval before next check
            if self._running:
                await asyncio.sleep(self.monitor_interval_minutes * 60)

    async def _process_stuck_batch(self, batch_state: CJBatchState) -> None:
        """Process a single stuck batch with semaphore control.

        Args:
            batch_state: The stuck batch state to process
        """
        async with self._semaphore:
            await self._handle_stuck_batch(batch_state)

    async def _handle_stuck_batch(self, batch_state: CJBatchState) -> None:
        """Decide recovery strategy for a stuck batch.

        Strategy:
        - If >= 80% complete: force to SCORING state
        - If < 80%: mark as FAILED

        Args:
            batch_state: The stuck batch state to handle
        """
        try:
            # Calculate progress percentage
            if batch_state.total_comparisons > 0:
                progress_pct = (
                    batch_state.completed_comparisons / batch_state.total_comparisons
                ) * 100
            else:
                progress_pct = 0

            batch_id = batch_state.batch_id
            current_state = batch_state.state

            logger.info(
                "Handling stuck batch",
                extra={
                    "batch_id": batch_id,
                    "current_state": current_state.value,
                    "progress_pct": progress_pct,
                    "completed_comparisons": batch_state.completed_comparisons,
                    "total_comparisons": batch_state.total_comparisons,
                    "last_activity_at": batch_state.last_activity_at.isoformat(),
                },
            )

            async with self._repository.session() as session:
                if progress_pct >= 80:
                    # Force to scoring if mostly complete
                    logger.info(
                        "Forcing stuck batch to SCORING state",
                        extra={
                            "batch_id": batch_id,
                            "progress_pct": progress_pct,
                            "reason": "batch_mostly_complete",
                        },
                    )

                    # Update state to SCORING
                    stmt = (
                        select(CJBatchState)
                        .where(CJBatchState.batch_id == batch_id)
                        .with_for_update()
                    )
                    result = await session.execute(stmt)
                    batch_state_db = result.scalar_one()

                    batch_state_db.state = CJBatchStateEnum.SCORING
                    batch_state_db.last_activity_at = datetime.now(UTC)

                    # Update processing metadata
                    if batch_state_db.processing_metadata is None:
                        batch_state_db.processing_metadata = {}
                    batch_state_db.processing_metadata["forced_to_scoring"] = {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "progress_pct": progress_pct,
                        "reason": "stuck_timeout",
                    }

                    await session.commit()

                    # Record recovery metric
                    if self._stuck_batches_recovered:
                        self._stuck_batches_recovered.inc()

                    # Trigger scoring process for forced batch
                    await self._trigger_scoring(
                        batch_id=batch_id,
                        session=session,
                        correlation_id=UUID(batch_state.batch_upload.event_correlation_id),
                    )

                else:
                    # Mark as failed if not enough progress
                    logger.warning(
                        "Marking stuck batch as FAILED",
                        extra={
                            "batch_id": batch_id,
                            "progress_pct": progress_pct,
                            "reason": "insufficient_progress",
                        },
                    )

                    # Update state to FAILED
                    stmt = (
                        select(CJBatchState)
                        .where(CJBatchState.batch_id == batch_id)
                        .with_for_update()
                    )
                    result = await session.execute(stmt)
                    batch_state_db = result.scalar_one()

                    batch_state_db.state = CJBatchStateEnum.FAILED
                    batch_state_db.last_activity_at = datetime.now(UTC)

                    # Update processing metadata
                    if batch_state_db.processing_metadata is None:
                        batch_state_db.processing_metadata = {}
                    batch_state_db.processing_metadata["failed_reason"] = {
                        "timestamp": datetime.now(UTC).isoformat(),
                        "progress_pct": progress_pct,
                        "reason": "stuck_timeout_insufficient_progress",
                    }

                    await session.commit()

                    # Get batch upload for failure event
                    batch_upload = await session.get(CJBatchUpload, batch_id)
                    if batch_upload:
                        # Create the failure event data with primitive parameters
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
                                    "reason": "stuck_timeout_insufficient_progress",
                                    "progress_pct": progress_pct,
                                    "batch_state": batch_state_db.state.value,
                                },
                            ),
                            cj_assessment_job_id=str(batch_id),
                        )

                        # Wrap in EventEnvelope
                        failure_envelope = EventEnvelope[CJAssessmentFailedV1](
                            event_type="cj_assessment.failed.v1",
                            event_timestamp=datetime.now(UTC),
                            source_service="cj_assessment_service",
                            correlation_id=UUID(batch_state.batch_upload.event_correlation_id),
                            data=failure_event_data,
                        )

                        # Publish batch failure event
                        await self._event_publisher.publish_assessment_failed(
                            failure_data=failure_envelope,
                            correlation_id=UUID(batch_state.batch_upload.event_correlation_id),
                        )

                # Increment metrics
                if self._stuck_batches_failed:
                    self._stuck_batches_failed.inc()

        except Exception as e:
            logger.error(
                "Failed to handle stuck batch",
                extra={
                    "batch_id": batch_state.batch_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )

    async def stop(self) -> None:
        """Graceful shutdown signal."""
        logger.info("Stopping batch monitor")
        self._running = False

    async def _trigger_scoring(
        self,
        batch_id: int,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> None:
        """Trigger Bradley-Terry scoring for a stuck batch forced to SCORING state.

        Args:
            batch_id: The CJ batch ID
            session: Active database session
            correlation_id: Correlation ID for event tracing
        """
        try:
            logger.info(
                "Triggering Bradley-Terry scoring for forced batch",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                },
            )

            # Get batch upload for BOS batch ID
            batch_upload = await session.get(CJBatchUpload, batch_id)
            if not batch_upload:
                logger.error(
                    "Batch upload not found for batch ID",
                    extra={
                        "batch_id": batch_id,
                        "correlation_id": correlation_id,
                    },
                )
                return

            # Get all essays for this batch
            essays = await self._repository.get_essays_for_cj_batch(
                session=session,
                cj_batch_id=batch_id,
            )

            if not essays:
                logger.error(
                    "No essays found for batch, cannot calculate scores",
                    extra={
                        "batch_id": batch_id,
                        "correlation_id": correlation_id,
                    },
                )
                return

            # Convert to API model format for scoring function
            essays_for_api = [
                EssayForComparison(
                    id=essay.els_essay_id,
                    text_content=essay.content,
                    current_bt_score=essay.current_bt_score,
                )
                for essay in essays
            ]

            # Get all existing comparisons (empty list if none)
            comparisons: list[Any] = []

            # Calculate final Bradley-Terry scores
            await scoring_ranking.record_comparisons_and_update_scores(
                all_essays=essays_for_api,
                comparison_results=comparisons,
                db_session=session,
                cj_batch_id=batch_id,
                correlation_id=correlation_id,
            )

            # Update batch status to completed
            await self._repository.update_cj_batch_status(
                session=session,
                cj_batch_id=batch_id,
                status=CJBatchStateEnum.COMPLETED,
            )

            # Get final rankings
            rankings = await scoring_ranking.get_essay_rankings(session, batch_id, correlation_id)

            # Calculate grade projections using async GradeProjector
            grade_projector = GradeProjector()
            grade_projections = await grade_projector.calculate_projections(
                session=session,
                rankings=rankings,
                cj_batch_id=batch_id,
                assignment_id=batch_upload.assignment_id if hasattr(batch_upload, 'assignment_id') else None,
                course_code=batch_upload.course_code if hasattr(batch_upload, 'course_code') else '',
                content_client=self._content_client,
                correlation_id=correlation_id,
            )
            
            # Log if no projections are available (no anchor essays)
            if not grade_projections.projections_available:
                logger.info(
                    "No grade projections available - no anchor essays present",
                    extra={
                        "batch_id": batch_id,
                        "correlation_id": correlation_id,
                    },
                )

            # Dual event publishing: thin to ELS, rich to RAS
            # Separate student essays from anchors
            student_rankings = [r for r in rankings if not r["els_essay_id"].startswith("ANCHOR_")]
            anchor_rankings = [r for r in rankings if r["els_essay_id"].startswith("ANCHOR_")]
            
            # 1. THIN EVENT TO ELS (filtered rankings without anchors)
            event_data = CJAssessmentCompletedV1(
                event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                entity_id=batch_upload.bos_batch_id,
                entity_type="batch",
                parent_id=None,
                status=BatchStatus.COMPLETED_SUCCESSFULLY if student_rankings else BatchStatus.FAILED_CRITICALLY,
                system_metadata=SystemProcessingMetadata(
                    entity_id=batch_upload.bos_batch_id,
                    entity_type="batch",
                    parent_id=None,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.COMPLETED,
                    started_at=batch_upload.created_at,
                    completed_at=datetime.now(UTC),
                    event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                ),
                cj_assessment_job_id=str(batch_id),
                rankings=student_rankings,  # Filtered rankings (no anchors)
                grade_projections_summary=grade_projections,
            )

            # Wrap in EventEnvelope
            completion_envelope = EventEnvelope[CJAssessmentCompletedV1](
                event_type="cj_assessment.completed.v1",
                event_timestamp=datetime.now(UTC),
                source_service="cj_assessment_service",
                correlation_id=correlation_id,
                data=event_data,
            )

            # Publish thin event to ELS
            await self._event_publisher.publish_assessment_completed(
                completion_data=completion_envelope,
                correlation_id=correlation_id,
            )
            
            # 2. RICH EVENT TO RAS (Full assessment results INCLUDING anchors for score bands)
            essay_results = []
            for ranking in rankings:  # Include ALL rankings (students + anchors)
                essay_id = ranking["els_essay_id"]
                is_anchor = essay_id.startswith("ANCHOR_")
                grade = grade_projections.primary_grades.get(essay_id, "U")
                
                essay_results.append({
                    "essay_id": essay_id,
                    "normalized_score": _grade_to_normalized(grade),
                    "letter_grade": grade,
                    "confidence_score": grade_projections.confidence_scores.get(essay_id, 0.0),
                    "confidence_label": grade_projections.confidence_labels.get(essay_id, "LOW"),
                    "bt_score": ranking.get("score", 0.0),
                    "rank": ranking.get("rank", 999),
                    "is_anchor": is_anchor,
                    # Display name for anchors to help with score band visualization
                    "display_name": f"ANCHOR GRADE {grade}" if is_anchor else None,
                })
            
            ras_event = AssessmentResultV1(
                event_name=ProcessingEvent.ASSESSMENT_RESULT_PUBLISHED,
                entity_id=batch_upload.bos_batch_id,
                entity_type="batch",
                batch_id=batch_upload.bos_batch_id,
                cj_assessment_job_id=str(batch_id),
                assessment_method="cj_assessment",
                model_used=self._settings.DEFAULT_LLM_MODEL,
                model_provider=self._settings.DEFAULT_LLM_PROVIDER.value,
                model_version=getattr(self._settings, "DEFAULT_LLM_MODEL_VERSION", None),
                essay_results=essay_results,
                assessment_metadata={
                    "anchor_essays_used": len(anchor_rankings),
                    "calibration_method": "anchor" if anchor_rankings else "default",
                    "processing_duration_seconds": (datetime.now(UTC) - batch_upload.created_at).total_seconds(),
                    "llm_temperature": self._settings.DEFAULT_LLM_TEMPERATURE,
                    "assignment_id": batch_upload.assignment_id if hasattr(batch_upload, 'assignment_id') else None,
                    "course_code": batch_upload.course_code if hasattr(batch_upload, 'course_code') else '',
                },
                assessed_at=datetime.now(UTC),
            )
            
            ras_envelope = EventEnvelope[AssessmentResultV1](
                event_type=self._settings.ASSESSMENT_RESULT_TOPIC,
                event_timestamp=datetime.now(UTC),
                source_service="cj_assessment_service",
                correlation_id=correlation_id,
                data=ras_event,
            )
            
            # Publish rich event to RAS
            await self._event_publisher.publish_assessment_result(
                result_data=ras_envelope,
                correlation_id=correlation_id,
            )

            logger.info(
                "Successfully triggered scoring and published completion for forced batch",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "essay_count": len(essays),
                    "status": "COMPLETED",
                },
            )

        except Exception as e:
            logger.error(
                "Failed to trigger scoring for stuck batch",
                extra={
                    "batch_id": batch_id,
                    "correlation_id": correlation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )

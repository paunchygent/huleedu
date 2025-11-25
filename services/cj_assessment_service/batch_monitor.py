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
from common_core.events.cj_assessment_events import (
    CJAssessmentFailedV1,
)
from common_core.events.envelope import EventEnvelope

# EntityReference removed - using primitive parameters
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic import scoring_ranking
from services.cj_assessment_service.cj_core_logic.batch_finalizer import BatchFinalizer
from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.enums_db import CJBatchStatusEnum
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload

if TYPE_CHECKING:
    from services.cj_assessment_service.cj_core_logic.grade_projector import (
        GradeProjector as GradeProjectorType,
    )
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.protocols import (
        CJBatchRepositoryProtocol,
        CJComparisonRepositoryProtocol,
        CJEssayRepositoryProtocol,
        CJEventPublisherProtocol,
        ContentClientProtocol,
        SessionProviderProtocol,
    )

logger = create_service_logger(__name__)


class BatchMonitor:
    """Monitors CJ assessment batches for stuck/timeout conditions."""

    def __init__(
        self,
        session_provider: SessionProviderProtocol,
        batch_repository: CJBatchRepositoryProtocol,
        essay_repository: CJEssayRepositoryProtocol,
        comparison_repository: CJComparisonRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        content_client: ContentClientProtocol,
        settings: Settings,
        grade_projector: GradeProjectorType,
    ) -> None:
        """Initialize the batch monitor.

        Args:
            session_provider: Session provider for database access
            batch_repository: Batch repository for batch operations
            essay_repository: Essay repository for essay operations
            comparison_repository: Comparison repository for comparison operations
            event_publisher: Event publishing interface
            content_client: Content client for fetching anchor essays
            settings: Service configuration
            grade_projector: Grade projector for calculating projections
        """
        self._session_provider = session_provider
        self._batch_repository = batch_repository
        self._essay_repository = essay_repository
        self._comparison_repository = comparison_repository
        self._event_publisher = event_publisher
        self._content_client = content_client
        self._settings = settings
        self._grade_projector = grade_projector

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

                async with self._session_provider.session() as session:
                    # Find potentially stuck batches using batch repository
                    stuck_batch_states = await self._batch_repository.get_stuck_batches(
                        session=session,
                        states=monitored_states,
                        stuck_threshold=stuck_threshold,
                    )

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
                        # No stuck batches found, reset gauge to 0 and emit heartbeat
                        logger.info(
                            "BatchMonitor heartbeat: no stuck batches detected",
                            extra={
                                "stuck_threshold": stuck_threshold.isoformat(),
                                "monitored_states": [s.value for s in monitored_states],
                            },
                        )
                        if self._stuck_batches_gauge:
                            self._stuck_batches_gauge.set(0)

                    # Fast-path completion sweeper: finalize batches with all callbacks received
                    ready_batches = await self._batch_repository.get_batches_ready_for_completion(
                        session=session
                    )

                    for ready_state in ready_batches:
                        try:
                            correlation_id = UUID(ready_state.batch_upload.event_correlation_id)
                            log_extra = {
                                "batch_id": ready_state.batch_id,
                                "correlation_id": str(correlation_id),
                                "completed": ready_state.completed_comparisons,
                                "total": ready_state.total_comparisons,
                                "state": ready_state.state.value,
                                "reason": "monitor_completion_sweep",
                            }
                            logger.info(
                                "Finalizing batch with all callbacks received",
                                extra=log_extra,
                            )
                            finalizer = BatchFinalizer(
                                session_provider=self._session_provider,
                                batch_repository=self._batch_repository,
                                essay_repository=self._essay_repository,
                                comparison_repository=self._comparison_repository,
                                event_publisher=self._event_publisher,
                                content_client=self._content_client,
                                settings=self._settings,
                                grade_projector=self._grade_projector,
                            )
                            await finalizer.finalize_scoring(
                                batch_id=ready_state.batch_id,
                                correlation_id=correlation_id,
                                log_extra=log_extra,
                            )
                        except Exception as e:  # pragma: no cover
                            logger.error(
                                "Failed to finalize batch in completion sweep",
                                extra={
                                    "batch_id": ready_state.batch_id,
                                    "error": str(e),
                                    "error_type": type(e).__name__,
                                },
                                exc_info=True,
                            )

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
            denominator = batch_state.completion_denominator()
            callbacks_recorded = batch_state.completed_comparisons + batch_state.failed_comparisons
            progress_pct = (callbacks_recorded / denominator) * 100 if denominator else 0

            batch_id = batch_state.batch_id
            current_state = batch_state.state

            # Early exit: batch completed via insufficient essays fast-path
            try:
                if batch_state.batch_upload and (
                    batch_state.batch_upload.status
                    == CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS
                ):
                    logger.info(
                        "Skipping stuck handling: batch completed with insufficient essays",
                        extra={
                            "batch_id": batch_id,
                            "current_state": current_state.value,
                            "status": CJBatchStatusEnum.COMPLETE_INSUFFICIENT_ESSAYS.value,
                        },
                    )
                    return
            except Exception:
                # If relationship not loaded for any reason, continue with normal flow
                pass

            logger.info(
                "Handling stuck batch",
                extra={
                    "batch_id": batch_id,
                    "current_state": current_state.value,
                    "progress_pct": progress_pct,
                    "completed_comparisons": batch_state.completed_comparisons,
                    "total_budget": batch_state.total_budget,
                    "total_comparisons": batch_state.total_comparisons,
                    "last_activity_at": batch_state.last_activity_at.isoformat(),
                },
            )

            async with self._session_provider.session() as session:
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

                    # Update state to SCORING with FOR UPDATE lock
                    batch_state_db = await self._batch_repository.get_batch_state_for_update(
                        session=session,
                        batch_id=batch_id,
                        for_update=True,
                    )
                    if not batch_state_db:
                        logger.error(
                            "Batch state not found for stuck batch",
                            extra={"batch_id": batch_id},
                        )
                        return

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

                    # Update state to FAILED with FOR UPDATE lock
                    batch_state_db = await self._batch_repository.get_batch_state_for_update(
                        session=session,
                        batch_id=batch_id,
                        for_update=True,
                    )
                    if not batch_state_db:
                        logger.error(
                            "Batch state not found for stuck batch",
                            extra={"batch_id": batch_id},
                        )
                        return

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
        correlation_id: UUID,
    ) -> None:
        """Trigger Bradley-Terry scoring for a stuck batch forced to SCORING state.

        Args:
            batch_id: The CJ batch ID
            correlation_id: Correlation ID for event tracing
        """
        async with self._session_provider.session() as session:
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
                essays = await self._essay_repository.get_essays_for_cj_batch(
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
                        text_content=essay.assessment_input_text,
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
                    session_provider=self._session_provider,
                    comparison_repository=self._comparison_repository,
                    essay_repository=self._essay_repository,
                    cj_batch_id=batch_id,
                    correlation_id=correlation_id,
                )

                # Update batch status to completed
                await self._batch_repository.update_cj_batch_status(
                    session=session,
                    cj_batch_id=batch_id,
                    status=CJBatchStateEnum.COMPLETED,
                )

                # Get final rankings
                rankings = await scoring_ranking.get_essay_rankings(
                    self._session_provider, self._essay_repository, batch_id, correlation_id
                )

                # Calculate grade projections using injected GradeProjector
                grade_projections = await self._grade_projector.calculate_projections(
                    rankings=rankings,
                    cj_batch_id=batch_id,
                    assignment_id=batch_upload.assignment_id
                    if hasattr(batch_upload, "assignment_id")
                    else None,
                    course_code=batch_upload.course_code
                    if hasattr(batch_upload, "course_code")
                    else "",
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

                # Extract data from batch_upload for publishing
                # user_id MUST be present for resource consumption tracking
                if not batch_upload.user_id:
                    raise ValueError(
                        f"user_id is None for batch {batch_upload.id} - identity threading failed. "
                        f"This is a critical error that should never happen in production."
                    )

                publishing_data = DualEventPublishingData(
                    bos_batch_id=batch_upload.bos_batch_id,
                    cj_batch_id=str(batch_upload.id),
                    assignment_id=batch_upload.assignment_id,
                    course_code=batch_upload.course_code,
                    user_id=batch_upload.user_id,  # Will raise if None due to check above
                    org_id=batch_upload.org_id,
                    created_at=batch_upload.created_at,
                )

                # Use centralized dual event publishing function
                await publish_dual_assessment_events(
                    rankings=rankings,
                    grade_projections=grade_projections,
                    publishing_data=publishing_data,  # Pass DTO
                    event_publisher=self._event_publisher,
                    settings=self._settings,
                    correlation_id=correlation_id,
                    processing_started_at=batch_upload.created_at,
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

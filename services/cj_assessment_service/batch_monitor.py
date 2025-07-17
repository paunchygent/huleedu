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
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import BatchStatus, CJBatchStateEnum, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from services.cj_assessment_service.cj_core_logic import scoring_ranking
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.models_db import CJBatchState, CJBatchUpload

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.protocols import (
        CJEventPublisherProtocol,
        CJRepositoryProtocol,
    )

logger = create_service_logger(__name__)


class BatchMonitor:
    """Monitors CJ assessment batches for stuck/timeout conditions."""

    def __init__(
        self,
        repository: CJRepositoryProtocol,
        event_publisher: CJEventPublisherProtocol,
        settings: Settings,
    ) -> None:
        """Initialize the batch monitor.

        Args:
            repository: Database access interface
            event_publisher: Event publishing interface
            settings: Service configuration
        """
        self._repository = repository
        self._event_publisher = event_publisher
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
                        # Create the failure event data
                        failure_event_data = CJAssessmentFailedV1(
                            event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                            entity_ref=EntityReference(
                                entity_id=batch_upload.bos_batch_id,
                                entity_type="batch",
                            ),
                            status=BatchStatus.FAILED_CRITICALLY,
                            system_metadata=SystemProcessingMetadata(
                                entity=EntityReference(
                                    entity_id=batch_upload.bos_batch_id,
                                    entity_type="batch",
                                ),
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

            # Create the event data
            event_data = CJAssessmentCompletedV1(
                event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
                entity_ref=EntityReference(
                    entity_id=batch_upload.bos_batch_id,
                    entity_type="batch",
                ),
                status=BatchStatus.COMPLETED_SUCCESSFULLY,
                system_metadata=SystemProcessingMetadata(
                    entity=EntityReference(
                        entity_id=batch_upload.bos_batch_id,
                        entity_type="batch",
                    ),
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.COMPLETED,
                    started_at=batch_upload.created_at,
                    completed_at=datetime.now(UTC),
                    event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
                ),
                cj_assessment_job_id=str(batch_id),
                rankings=rankings,
            )

            # Wrap in EventEnvelope
            completion_envelope = EventEnvelope[CJAssessmentCompletedV1](
                event_type="cj_assessment.completed.v1",
                event_timestamp=datetime.now(UTC),
                source_service="cj_assessment_service",
                correlation_id=correlation_id,
                data=event_data,
            )

            # Publish completion event
            await self._event_publisher.publish_assessment_completed(
                completion_data=completion_envelope,
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

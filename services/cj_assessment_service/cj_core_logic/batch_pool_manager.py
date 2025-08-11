"""Failed comparison pool management for CJ Assessment Service.

This module handles failed comparison retry logic and statistics.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    FailedComparisonEntry,
    FailedComparisonPool,
)
from services.cj_assessment_service.protocols import CJRepositoryProtocol

from .batch_submission import (
    get_batch_state,
    update_batch_processing_metadata,
)

logger = create_service_logger("cj_assessment_service.batch_pool_manager")


class BatchPoolManager:
    """Manages failed comparison pools and retry logic."""

    def __init__(
        self,
        database: CJRepositoryProtocol,
        settings: Settings,
    ) -> None:
        """Initialize batch pool manager.

        Args:
            database: Database access protocol implementation
            settings: Application settings
        """
        self.database = database
        self.settings = settings

    async def add_to_failed_pool(
        self,
        cj_batch_id: int,
        comparison_task: ComparisonTask,
        failure_reason: str,
        correlation_id: UUID,
    ) -> None:
        """Add a failed comparison to the retry pool using atomic JSONB operations.

        Args:
            cj_batch_id: CJ batch ID for tracking
            comparison_task: Original comparison task that failed
            failure_reason: Reason for failure
            correlation_id: Request correlation ID for tracing

        Raises:
            HuleEduError: On database operation failure
        """
        logger.info(
            f"Adding failed comparison to pool for batch {cj_batch_id}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "failure_reason": failure_reason,
                "essay_a_id": comparison_task.essay_a.id,
                "essay_b_id": comparison_task.essay_b.id,
            },
        )

        try:
            from .batch_submission import append_to_failed_pool_atomic, get_batch_state

            async with self.database.session() as session:
                # First check if batch exists
                batch_state = await get_batch_state(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )

                if not batch_state:
                    from huleedu_service_libs.error_handling import raise_resource_not_found

                    raise_resource_not_found(
                        service="cj_assessment_service",
                        operation="add_to_failed_pool",
                        message=f"Batch state not found for batch {cj_batch_id}",
                        correlation_id=correlation_id,
                        resource_type="batch_state",
                        resource_id=str(cj_batch_id),
                    )

                # Create new failed comparison entry
                failed_entry = FailedComparisonEntry(
                    essay_a_id=comparison_task.essay_a.id,
                    essay_b_id=comparison_task.essay_b.id,
                    comparison_task=comparison_task,
                    failure_reason=failure_reason,
                    failed_at=datetime.now(UTC),
                    retry_count=0,
                    original_batch_id=str(cj_batch_id),
                    correlation_id=correlation_id,
                )

                # Convert to JSON-serializable dict
                failed_entry_json = failed_entry.model_dump(mode="json")

                # Use atomic JSONB append - no locking needed!
                await append_to_failed_pool_atomic(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    failed_entry_json=failed_entry_json,
                    correlation_id=correlation_id,
                )

                # Record metrics
                business_metrics = get_business_metrics()
                failed_comparisons_metric = business_metrics.get("cj_failed_comparisons_total")

                if failed_comparisons_metric:
                    failed_comparisons_metric.labels(failure_reason=failure_reason).inc()

                logger.info(
                    "Successfully added comparison to failed pool using atomic operation",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                    },
                )

        except Exception as e:
            logger.error(
                f"Failed to add comparison to failed pool: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise_processing_error(
                service="cj_assessment_service",
                operation="add_to_failed_pool",
                message=f"Failed to add comparison to failed pool: {str(e)}",
                correlation_id=correlation_id,
                database_operation="add_to_failed_pool",
                entity_id=str(cj_batch_id),
            )

    async def check_retry_batch_needed(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        force_retry_all: bool = False,
    ) -> bool:
        """Check if enough failures accumulated to warrant retry batch.

        Args:
            cj_batch_id: CJ batch ID to check
            correlation_id: Request correlation ID for tracing
            force_retry_all: If True, retry any eligible failures regardless of threshold

        Returns:
            True if retry batch should be created, False otherwise

        Raises:
            HuleEduError: On database operation failure
        """
        if not self.settings.ENABLE_FAILED_COMPARISON_RETRY:
            return False

        try:
            async with self.database.session() as session:
                batch_state = await get_batch_state(
                    session=session, cj_batch_id=cj_batch_id, correlation_id=correlation_id
                )

                if not batch_state or not batch_state.processing_metadata:
                    return False

                failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)

                # Check if we have enough failures for retry
                eligible_failures = [
                    entry
                    for entry in failed_pool.failed_comparison_pool
                    if entry.retry_count < self.settings.MAX_RETRY_ATTEMPTS
                ]

                if force_retry_all:
                    # At end of batch: process ANY eligible failures for fairness
                    retry_needed = len(eligible_failures) > 0
                    logger.info(
                        f"End-of-batch retry check for batch {cj_batch_id}: "
                        f"{len(eligible_failures)} eligible failures remaining, "
                        f"retry needed for fairness: {retry_needed}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "eligible_failures": len(eligible_failures),
                            "force_retry_all": force_retry_all,
                            "retry_needed": retry_needed,
                        },
                    )
                else:
                    # During active processing: use threshold for efficiency
                    retry_needed = (
                        len(eligible_failures) >= self.settings.FAILED_COMPARISON_RETRY_THRESHOLD
                    )
                    logger.info(
                        f"Threshold-based retry check for batch {cj_batch_id}: "
                        f"{len(eligible_failures)} eligible failures, "
                        f"threshold: {self.settings.FAILED_COMPARISON_RETRY_THRESHOLD}, "
                        f"retry needed: {retry_needed}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "eligible_failures": len(eligible_failures),
                            "threshold": self.settings.FAILED_COMPARISON_RETRY_THRESHOLD,
                            "force_retry_all": force_retry_all,
                            "retry_needed": retry_needed,
                        },
                    )

                return retry_needed

        except Exception as e:
            logger.error(
                f"Failed to check retry batch need: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise_processing_error(
                service="cj_assessment_service",
                operation="check_retry_batch_needed",
                message=f"Failed to check retry batch need: {str(e)}",
                correlation_id=correlation_id,
                database_operation="check_retry_batch_needed",
                entity_id=str(cj_batch_id),
            )

    async def form_retry_batch(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        force_retry_all: bool = False,
    ) -> list[ComparisonTask] | None:
        """Form retry batch from failed pool and update statistics.

        Args:
            cj_batch_id: CJ batch ID
            correlation_id: Request correlation ID for tracing
            force_retry_all: If True, process any eligible failures regardless of threshold

        Returns:
            List of comparison tasks for retry, or None if not enough failures

        Raises:
            HuleEduError: On database operation failure
        """
        try:
            async with self.database.session() as session:
                batch_state = await get_batch_state(
                    session=session, cj_batch_id=cj_batch_id, correlation_id=correlation_id
                )

                if not batch_state or not batch_state.processing_metadata:
                    return None

                failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)

                # Get eligible failures for retry
                eligible_failures = [
                    entry
                    for entry in failed_pool.failed_comparison_pool
                    if entry.retry_count < self.settings.MAX_RETRY_ATTEMPTS
                ]

                if (
                    not force_retry_all
                    and len(eligible_failures) < self.settings.FAILED_COMPARISON_RETRY_THRESHOLD
                ):
                    return None

                # If force_retry_all=True, process any eligible failures regardless of threshold
                if force_retry_all and len(eligible_failures) == 0:
                    return None

                # Select batch for retry (up to retry batch size)
                retry_batch_size = min(self.settings.RETRY_BATCH_SIZE, len(eligible_failures))
                retry_entries = eligible_failures[:retry_batch_size]

                # Create comparison tasks
                retry_tasks = [entry.comparison_task for entry in retry_entries]

                # Update retry counts for selected entries
                for entry in retry_entries:
                    entry.retry_count += 1

                # Remove entries that have reached max retry attempts
                remaining_pool = []
                permanently_failed_count = 0

                for entry in failed_pool.failed_comparison_pool:
                    if entry in retry_entries:
                        if entry.retry_count < self.settings.MAX_RETRY_ATTEMPTS:
                            remaining_pool.append(entry)
                        else:
                            permanently_failed_count += 1
                    else:
                        remaining_pool.append(entry)

                # Update pool statistics
                failed_pool.failed_comparison_pool = remaining_pool
                failed_pool.pool_statistics.retry_attempts += 1
                failed_pool.pool_statistics.permanently_failed += permanently_failed_count
                failed_pool.pool_statistics.last_retry_batch = f"retry_batch_{correlation_id}"

                # Record metrics for permanently failed comparisons
                if permanently_failed_count > 0:
                    business_metrics = get_business_metrics()
                    permanently_failed_metric = business_metrics.get(
                        "cj_permanently_failed_comparisons_total"
                    )
                    pool_size_metric = business_metrics.get("cj_failed_pool_size")

                    if permanently_failed_metric:
                        permanently_failed_metric.inc(permanently_failed_count)

                    if pool_size_metric:
                        pool_size_metric.labels(batch_id=str(cj_batch_id)).set(len(remaining_pool))

                # Update batch state
                await update_batch_processing_metadata(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    metadata=failed_pool.model_dump(mode="json"),
                    correlation_id=correlation_id,
                )

                if force_retry_all:
                    logger.info(
                        f"End-of-batch processing: Formed retry batch with {len(retry_tasks)} "
                        f"remaining failed comparisons to ensure fair Bradley-Terry scoring. "
                        f"Pool now has {len(remaining_pool)} entries, "
                        f"{permanently_failed_count} permanently failed",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "retry_batch_size": len(retry_tasks),
                            "remaining_pool_size": len(remaining_pool),
                            "permanently_failed": permanently_failed_count,
                            "force_retry_all": force_retry_all,
                        },
                    )
                else:
                    logger.info(
                        f"Threshold-based retry: Formed retry batch with {len(retry_tasks)} tasks. "
                        f"Pool now has {len(remaining_pool)} entries, "
                        f"{permanently_failed_count} permanently failed",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "retry_batch_size": len(retry_tasks),
                            "remaining_pool_size": len(remaining_pool),
                            "permanently_failed": permanently_failed_count,
                            "force_retry_all": force_retry_all,
                        },
                    )

                return retry_tasks

        except Exception as e:
            logger.error(
                f"Failed to form retry batch: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise_processing_error(
                service="cj_assessment_service",
                operation="form_retry_batch",
                message=f"Failed to form retry batch: {str(e)}",
                correlation_id=correlation_id,
                database_operation="form_retry_batch",
                entity_id=str(cj_batch_id),
            )

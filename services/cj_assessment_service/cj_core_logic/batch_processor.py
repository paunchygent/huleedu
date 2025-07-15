"""Batch submission processor for CJ Assessment Service.

This module handles batch LLM submission logic with configurable batch sizes,
state management integration, and comprehensive error handling.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.exceptions import (
    AssessmentProcessingError,
    DatabaseOperationError,
    LLMProviderError,
)
from services.cj_assessment_service.models_api import (
    ComparisonTask,
    FailedComparisonEntry,
    FailedComparisonPool,
    FailedComparisonPoolStatistics,
)
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)
from services.cj_assessment_service.metrics import get_business_metrics

logger = create_service_logger("cj_assessment_service.batch_processor")


class BatchConfigOverrides(BaseModel):
    """Configuration overrides for batch processing parameters."""

    batch_size: int | None = Field(None, ge=10, le=200, description="Batch size override")
    max_concurrent_batches: int | None = Field(
        None, ge=1, le=5, description="Maximum concurrent batches"
    )
    partial_completion_threshold: float | None = Field(
        None, ge=0.5, le=1.0, description="Partial completion threshold"
    )


class BatchSubmissionResult(BaseModel):
    """Result of batch submission operation."""

    batch_id: int = Field(description="CJ batch ID")
    total_submitted: int = Field(description="Number of comparisons submitted")
    submitted_at: datetime = Field(description="Submission timestamp")
    all_submitted: bool = Field(description="Whether all comparisons were submitted")
    correlation_id: UUID = Field(description="Request correlation ID")


class BatchProcessor:
    """Handles batch submission logic for CJ Assessment Service."""

    def __init__(
        self,
        database: CJRepositoryProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
    ) -> None:
        """Initialize batch processor.

        Args:
            database: Database access protocol implementation
            llm_interaction: LLM interaction protocol implementation
            settings: Application settings
        """
        self.database = database
        self.llm_interaction = llm_interaction
        self.settings = settings

    async def submit_comparison_batch(
        self,
        cj_batch_id: int,
        comparison_tasks: list[ComparisonTask],
        correlation_id: UUID,
        config_overrides: BatchConfigOverrides | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> BatchSubmissionResult:
        """Submit comparison batch with configurable batch size.

        Args:
            cj_batch_id: CJ batch ID for tracking
            comparison_tasks: List of comparison tasks to submit
            correlation_id: Request correlation ID for tracing
            config_overrides: Optional batch configuration overrides
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            BatchSubmissionResult with submission details

        Raises:
            AssessmentProcessingError: On batch submission failure
            DatabaseOperationError: On database operation failure
            LLMProviderError: On LLM provider communication failure
        """
        if not comparison_tasks:
            raise AssessmentProcessingError(
                message="No comparison tasks provided for batch submission",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="batch_submission",
            )

        # Get effective batch size
        effective_batch_size = self._get_effective_batch_size(config_overrides)

        logger.info(
            f"Starting batch submission for CJ batch {cj_batch_id} "
            f"with {len(comparison_tasks)} tasks, batch size: {effective_batch_size}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "total_tasks": len(comparison_tasks),
                "batch_size": effective_batch_size,
            },
        )

        # Process batches
        total_submitted = 0
        submission_timestamp = datetime.now()

        try:
            # Update batch state to WAITING_CALLBACKS before submission
            await self._update_batch_state(
                cj_batch_id=cj_batch_id,
                state=CJBatchStateEnum.WAITING_CALLBACKS,
                correlation_id=correlation_id,
            )

            # Submit in batches
            for i in range(0, len(comparison_tasks), effective_batch_size):
                batch_tasks = comparison_tasks[i : i + effective_batch_size]

                await self._submit_batch_chunk(
                    batch_tasks=batch_tasks,
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                    model_override=model_override,
                    temperature_override=temperature_override,
                    max_tokens_override=max_tokens_override,
                )

                total_submitted += len(batch_tasks)

                # Update submitted count in database
                await self._update_submitted_count(
                    cj_batch_id=cj_batch_id,
                    submitted_count=total_submitted,
                    correlation_id=correlation_id,
                )

                logger.info(
                    f"Submitted batch chunk {i // effective_batch_size + 1} "
                    f"with {len(batch_tasks)} tasks. Total submitted: {total_submitted}",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "chunk_size": len(batch_tasks),
                        "total_submitted": total_submitted,
                    },
                )

            all_submitted = total_submitted == len(comparison_tasks)

            logger.info(
                f"Batch submission completed for CJ batch {cj_batch_id}. "
                f"Submitted: {total_submitted}/{len(comparison_tasks)}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "total_submitted": total_submitted,
                    "total_tasks": len(comparison_tasks),
                    "all_submitted": all_submitted,
                },
            )

            return BatchSubmissionResult(
                batch_id=cj_batch_id,
                total_submitted=total_submitted,
                submitted_at=submission_timestamp,
                all_submitted=all_submitted,
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(
                f"Batch submission failed for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            # Update batch state to FAILED on error
            try:
                await self._update_batch_state(
                    cj_batch_id=cj_batch_id,
                    state=CJBatchStateEnum.FAILED,
                    correlation_id=correlation_id,
                )
            except Exception as state_error:
                logger.error(
                    f"Failed to update batch state to FAILED: {state_error}",
                    extra={"correlation_id": str(correlation_id), "cj_batch_id": cj_batch_id},
                )

            # Re-raise all exceptions as AssessmentProcessingError for consistency
            raise AssessmentProcessingError(
                message=f"Batch submission failed: {str(e)}",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="batch_submission",
            )

    async def check_batch_completion(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        config_overrides: BatchConfigOverrides | None = None,
    ) -> bool:
        """Check if batch is complete or has reached threshold.

        Args:
            cj_batch_id: CJ batch ID to check
            correlation_id: Request correlation ID for tracing
            config_overrides: Optional batch configuration overrides

        Returns:
            True if batch is complete or threshold reached, False otherwise

        Raises:
            DatabaseOperationError: On database operation failure
        """
        try:
            async with self.database.session() as session:
                # Get batch state from database
                batch_state = await self._get_batch_state(
                    session=session, cj_batch_id=cj_batch_id, correlation_id=correlation_id
                )

                if not batch_state:
                    raise DatabaseOperationError(
                        message="Batch state not found",
                        correlation_id=correlation_id,
                        operation="check_batch_completion",
                        entity_id=str(cj_batch_id),
                    )

                # Check if batch is in a terminal state
                if batch_state.state in [
                    CJBatchStateEnum.COMPLETED,
                    CJBatchStateEnum.FAILED,
                    CJBatchStateEnum.CANCELLED,
                ]:
                    return True

                # Check completion threshold
                if batch_state.total_comparisons > 0:
                    completion_rate = (
                        batch_state.completed_comparisons / batch_state.total_comparisons
                    )

                    # Get effective threshold
                    threshold = self._get_effective_threshold(config_overrides, batch_state)

                    logger.info(
                        f"Batch {cj_batch_id} completion check: "
                        f"{batch_state.completed_comparisons}/{batch_state.total_comparisons} "
                        f"({completion_rate:.2%}) vs threshold {threshold:.2%}",
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "completion_rate": completion_rate,
                            "threshold": threshold,
                        },
                    )

                    return bool(completion_rate >= threshold)

                return False

        except Exception as e:
            logger.error(
                f"Failed to check batch completion for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            if isinstance(e, DatabaseOperationError):
                raise
            else:
                raise DatabaseOperationError(
                    message=f"Failed to check batch completion: {str(e)}",
                    correlation_id=correlation_id,
                    operation="check_batch_completion",
                    entity_id=str(cj_batch_id),
                )

    async def handle_batch_submission(
        self,
        cj_batch_id: int,
        comparison_tasks: list[ComparisonTask],
        correlation_id: UUID,
        request_data: dict[str, Any],
    ) -> BatchSubmissionResult:
        """Handle batch submission with state tracking.

        Args:
            cj_batch_id: CJ batch ID for tracking
            comparison_tasks: List of comparison tasks to submit
            correlation_id: Request correlation ID for tracing
            request_data: Original request data containing overrides

        Returns:
            BatchSubmissionResult with submission details

        Raises:
            AssessmentProcessingError: On batch submission failure
        """
        # Extract configuration overrides from request data
        config_overrides = None
        if "batch_config_overrides" in request_data:
            config_overrides = BatchConfigOverrides(**request_data["batch_config_overrides"])

        # Extract LLM overrides from request data
        llm_config_overrides = request_data.get("llm_config_overrides")
        model_override = None
        temperature_override = None
        max_tokens_override = None

        if llm_config_overrides:
            model_override = llm_config_overrides.model_override
            temperature_override = llm_config_overrides.temperature_override
            max_tokens_override = llm_config_overrides.max_tokens_override

        return await self.submit_comparison_batch(
            cj_batch_id=cj_batch_id,
            comparison_tasks=comparison_tasks,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
            model_override=model_override,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
        )

    def _get_effective_batch_size(self, config_overrides: BatchConfigOverrides | None) -> int:
        """Get effective batch size from settings and overrides.

        Args:
            config_overrides: Optional batch configuration overrides

        Returns:
            Effective batch size to use
        """
        if config_overrides and config_overrides.batch_size is not None:
            return config_overrides.batch_size

        # Use settings default or fallback
        return getattr(self.settings, "DEFAULT_BATCH_SIZE", 50)

    def _get_effective_threshold(
        self, config_overrides: BatchConfigOverrides | None, batch_state: Any
    ) -> float:
        """Get effective completion threshold from settings and overrides.

        Args:
            config_overrides: Optional batch configuration overrides
            batch_state: Current batch state with threshold configuration

        Returns:
            Effective completion threshold to use
        """
        if config_overrides and config_overrides.partial_completion_threshold is not None:
            return config_overrides.partial_completion_threshold

        # Use batch state threshold or default
        if hasattr(batch_state, "completion_threshold_pct"):
            return float(batch_state.completion_threshold_pct / 100.0)

        return 0.95  # Default 95% threshold

    async def _submit_batch_chunk(
        self,
        batch_tasks: list[ComparisonTask],
        cj_batch_id: int,
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> None:
        """Submit a chunk of comparison tasks.

        Args:
            batch_tasks: List of comparison tasks to submit
            cj_batch_id: CJ batch ID for tracking
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Raises:
            LLMProviderError: On LLM provider communication failure
        """
        try:
            # Use existing LLM interaction protocol for batch submission
            # This will handle async processing (returns None for queued requests)
            results = await self.llm_interaction.perform_comparisons(
                tasks=batch_tasks,
                correlation_id=correlation_id,
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            )

            # Log submission results
            successful_submissions = sum(1 for r in results if r.llm_assessment is not None)
            logger.info(
                f"Batch chunk submitted: {successful_submissions}/{len(batch_tasks)} successful",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "successful_submissions": successful_submissions,
                    "total_tasks": len(batch_tasks),
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to submit batch chunk for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "chunk_size": len(batch_tasks),
                    "error": str(e),
                },
                exc_info=True,
            )

            raise LLMProviderError(
                message=f"Failed to submit batch chunk: {str(e)}",
                correlation_id=correlation_id,
                is_retryable=True,
            )

    async def _update_batch_state(
        self,
        cj_batch_id: int,
        state: CJBatchStateEnum,
        correlation_id: UUID,
    ) -> None:
        """Update batch state in database.

        Args:
            cj_batch_id: CJ batch ID
            state: New batch state
            correlation_id: Request correlation ID for tracing

        Raises:
            DatabaseOperationError: On database operation failure
        """
        try:
            async with self.database.session() as session:
                await self._update_batch_state_in_session(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    state=state,
                    correlation_id=correlation_id,
                )

        except Exception as e:
            logger.error(
                f"Failed to update batch state for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "target_state": state.value,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise DatabaseOperationError(
                message=f"Failed to update batch state to {state.value}: {str(e)}",
                correlation_id=correlation_id,
                operation="update_batch_state",
                entity_id=str(cj_batch_id),
            )

    async def _update_submitted_count(
        self,
        cj_batch_id: int,
        submitted_count: int,
        correlation_id: UUID,
    ) -> None:
        """Update submitted comparisons count in database.

        Args:
            cj_batch_id: CJ batch ID
            submitted_count: New submitted count
            correlation_id: Request correlation ID for tracing

        Raises:
            DatabaseOperationError: On database operation failure
        """
        try:
            async with self.database.session() as session:
                await self._update_submitted_count_in_session(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    submitted_count=submitted_count,
                    correlation_id=correlation_id,
                )

        except Exception as e:
            logger.error(
                f"Failed to update submitted count for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "submitted_count": submitted_count,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise DatabaseOperationError(
                message=f"Failed to update submitted count: {str(e)}",
                correlation_id=correlation_id,
                operation="update_submitted_count",
                entity_id=str(cj_batch_id),
            )

    async def _get_batch_state(
        self, session: AsyncSession, cj_batch_id: int, correlation_id: UUID
    ) -> Any:
        """Get batch state from database.

        Args:
            session: Database session
            cj_batch_id: CJ batch ID
            correlation_id: Request correlation ID for tracing

        Returns:
            Batch state object or None if not found
        """
        # This would need to be implemented based on the repository protocol
        # For now, we'll use a placeholder that demonstrates the pattern
        from sqlalchemy import select

        from services.cj_assessment_service.models_db import CJBatchState

        try:
            result = await session.execute(
                select(CJBatchState).where(CJBatchState.batch_id == cj_batch_id)
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.error(
                f"Failed to get batch state for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            return None

    async def _update_batch_state_in_session(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        state: CJBatchStateEnum,
        correlation_id: UUID,
    ) -> None:
        """Update batch state within a database session.

        Args:
            session: Database session
            cj_batch_id: CJ batch ID
            state: New batch state
            correlation_id: Request correlation ID for tracing
        """
        from sqlalchemy import update

        from services.cj_assessment_service.models_db import CJBatchState

        logger.debug(
            f"Updating batch state to {state.value}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "new_state": state.value,
            },
        )

        await session.execute(
            update(CJBatchState).where(CJBatchState.batch_id == cj_batch_id).values(state=state)
        )
        await session.commit()

    async def _update_submitted_count_in_session(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        submitted_count: int,
        correlation_id: UUID,
    ) -> None:
        """Update submitted count within a database session.

        Args:
            session: Database session
            cj_batch_id: CJ batch ID
            submitted_count: New submitted count
            correlation_id: Request correlation ID for tracing
        """
        from sqlalchemy import update

        from services.cj_assessment_service.models_db import CJBatchState

        logger.debug(
            f"Updating submitted count to {submitted_count}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "submitted_count": submitted_count,
            },
        )

        await session.execute(
            update(CJBatchState)
            .where(CJBatchState.batch_id == cj_batch_id)
            .values(submitted_comparisons=submitted_count)
        )
        await session.commit()

    async def add_to_failed_pool(
        self,
        cj_batch_id: int,
        comparison_task: ComparisonTask,
        failure_reason: str,
        correlation_id: UUID,
    ) -> None:
        """Add a failed comparison to the retry pool.

        Args:
            cj_batch_id: CJ batch ID for tracking
            comparison_task: Original comparison task that failed
            failure_reason: Reason for failure
            correlation_id: Request correlation ID for tracing

        Raises:
            DatabaseOperationError: On database operation failure
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
            async with self.database.session() as session:
                # Get current batch state
                batch_state = await self._get_batch_state(
                    session=session, cj_batch_id=cj_batch_id, correlation_id=correlation_id
                )

                if not batch_state:
                    raise DatabaseOperationError(
                        message="Batch state not found for failed pool addition",
                        correlation_id=correlation_id,
                        operation="add_to_failed_pool",
                        entity_id=str(cj_batch_id),
                    )

                # Get or create failed pool from processing_metadata
                failed_pool_data = batch_state.processing_metadata or {}
                failed_pool = FailedComparisonPool.model_validate(failed_pool_data)

                # Create new failed comparison entry
                failed_entry = FailedComparisonEntry(
                    essay_a_id=comparison_task.essay_a.id,
                    essay_b_id=comparison_task.essay_b.id,
                    comparison_task=comparison_task,
                    failure_reason=failure_reason,
                    failed_at=datetime.now(),
                    retry_count=0,
                    original_batch_id=str(cj_batch_id),
                    correlation_id=correlation_id,
                )

                # Add to pool
                failed_pool.failed_comparison_pool.append(failed_entry)
                failed_pool.pool_statistics.total_failed += 1

                # Record metrics
                business_metrics = get_business_metrics()
                failed_comparisons_metric = business_metrics.get("cj_failed_comparisons_total")
                pool_size_metric = business_metrics.get("cj_failed_pool_size")

                if failed_comparisons_metric:
                    failed_comparisons_metric.labels(failure_reason=failure_reason).inc()

                if pool_size_metric:
                    pool_size_metric.labels(batch_id=str(cj_batch_id)).set(
                        len(failed_pool.failed_comparison_pool)
                    )

                # Update batch state with new pool data
                await self._update_batch_processing_metadata(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    metadata=failed_pool.model_dump(),
                    correlation_id=correlation_id,
                )

                logger.info(
                    f"Added comparison to failed pool. Pool now contains "
                    f"{len(failed_pool.failed_comparison_pool)} entries",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "pool_size": len(failed_pool.failed_comparison_pool),
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

            raise DatabaseOperationError(
                message=f"Failed to add comparison to failed pool: {str(e)}",
                correlation_id=correlation_id,
                operation="add_to_failed_pool",
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

        Returns:
            True if retry batch should be created, False otherwise

        Raises:
            DatabaseOperationError: On database operation failure
        """
        if not self.settings.ENABLE_FAILED_COMPARISON_RETRY:
            return False

        try:
            async with self.database.session() as session:
                batch_state = await self._get_batch_state(
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

            raise DatabaseOperationError(
                message=f"Failed to check retry batch need: {str(e)}",
                correlation_id=correlation_id,
                operation="check_retry_batch_needed",
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

        Returns:
            List of comparison tasks for retry, or None if not enough failures

        Raises:
            DatabaseOperationError: On database operation failure
        """
        try:
            async with self.database.session() as session:
                batch_state = await self._get_batch_state(
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
                await self._update_batch_processing_metadata(
                    session=session,
                    cj_batch_id=cj_batch_id,
                    metadata=failed_pool.model_dump(),
                    correlation_id=correlation_id,
                )

                if force_retry_all:
                    logger.info(
                        f"End-of-batch processing: Formed retry batch with {len(retry_tasks)} remaining failed comparisons "
                        f"to ensure fair Bradley-Terry scoring. Pool now has {len(remaining_pool)} entries, "
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

            raise DatabaseOperationError(
                message=f"Failed to form retry batch: {str(e)}",
                correlation_id=correlation_id,
                operation="form_retry_batch",
                entity_id=str(cj_batch_id),
            )

    async def submit_retry_batch(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        force_retry_all: bool = False,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> BatchSubmissionResult | None:
        """Submit retry batch if threshold reached.

        Args:
            cj_batch_id: CJ batch ID
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            BatchSubmissionResult if retry batch was submitted, None otherwise

        Raises:
            AssessmentProcessingError: On retry batch submission failure
        """
        if not self.settings.ENABLE_FAILED_COMPARISON_RETRY:
            logger.info(
                f"Failed comparison retry disabled for batch {cj_batch_id}",
                extra={"correlation_id": str(correlation_id), "cj_batch_id": cj_batch_id},
            )
            return None

        logger.info(
            f"Checking retry batch submission for batch {cj_batch_id}",
            extra={"correlation_id": str(correlation_id), "cj_batch_id": cj_batch_id},
        )

        try:
            # Form retry batch
            retry_tasks = await self.form_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=force_retry_all,
            )

            if not retry_tasks:
                logger.info(
                    f"No retry batch formed for batch {cj_batch_id}",
                    extra={"correlation_id": str(correlation_id), "cj_batch_id": cj_batch_id},
                )
                return None

            # Submit retry batch
            result = await self.submit_comparison_batch(
                cj_batch_id=cj_batch_id,
                comparison_tasks=retry_tasks,
                correlation_id=correlation_id,
                config_overrides=None,  # Use defaults for retry
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            )

            if force_retry_all:
                logger.info(
                    f"End-of-batch processing: Successfully submitted {result.total_submitted} remaining failed comparisons "
                    f"for batch {cj_batch_id} to ensure fairness",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "retry_tasks_submitted": result.total_submitted,
                        "force_retry_all": force_retry_all,
                    },
                )
            else:
                logger.info(
                    f"Threshold-based retry: Successfully submitted retry batch for batch {cj_batch_id} "
                    f"with {result.total_submitted} tasks",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "retry_tasks_submitted": result.total_submitted,
                        "force_retry_all": force_retry_all,
                    },
                )

            # Record retry batch submission metric
            business_metrics = get_business_metrics()
            retry_batches_metric = business_metrics.get("cj_retry_batches_submitted_total")
            if retry_batches_metric:
                retry_batches_metric.inc()

            return result

        except Exception as e:
            logger.error(
                f"Failed to submit retry batch for batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise AssessmentProcessingError(
                message=f"Failed to submit retry batch: {str(e)}",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="retry_batch_submission",
            )

    async def process_remaining_failed_comparisons(
        self,
        cj_batch_id: int,
        correlation_id: UUID,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
    ) -> BatchSubmissionResult | None:
        """Process all remaining failed comparisons at end of batch.

        This ensures fairness by processing ALL remaining failures,
        regardless of the normal threshold requirement. This method is called
        when batch processing ends (max comparisons reached or stability achieved)
        to ensure all essays receive equal comparison counts for fair Bradley-Terry scoring.

        Args:
            cj_batch_id: CJ batch ID
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            BatchSubmissionResult if remaining failures were processed, None otherwise

        Raises:
            AssessmentProcessingError: On processing failure
        """
        logger.info(
            f"Processing remaining failed comparisons for batch {cj_batch_id} to ensure fairness",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
            },
        )

        try:
            # Force retry of ALL remaining eligible failures for fairness
            return await self.submit_retry_batch(
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=True,  # KEY: Force processing of all remaining failures
                model_override=model_override,
                temperature_override=temperature_override,
                max_tokens_override=max_tokens_override,
            )

        except Exception as e:
            logger.error(
                f"Failed to process remaining failed comparisons for batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise AssessmentProcessingError(
                message=f"Failed to process remaining failed comparisons: {str(e)}",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="end_of_batch_retry_processing",
            )

    async def _update_batch_processing_metadata(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        metadata: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        """Update batch processing metadata in database session.

        Args:
            session: Database session
            cj_batch_id: CJ batch ID
            metadata: Processing metadata to store
            correlation_id: Request correlation ID for tracing

        Raises:
            DatabaseOperationError: On database operation failure
        """
        from sqlalchemy import update

        from services.cj_assessment_service.models_db import CJBatchState

        try:
            await session.execute(
                update(CJBatchState)
                .where(CJBatchState.batch_id == cj_batch_id)
                .values(processing_metadata=metadata)
            )
            await session.commit()

            logger.debug(
                f"Updated processing metadata for batch {cj_batch_id}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to update processing metadata: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

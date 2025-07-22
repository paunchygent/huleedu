"""Batch retry processor for CJ Assessment Service.

This module handles retry batch formation and submission, including end-of-batch
fairness processing and failed comparison pool coordination.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from huleedu_service_libs.error_handling import raise_processing_error
from services.cj_assessment_service.protocols import (
    BatchProcessorProtocol,
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

from .batch_pool_manager import BatchPoolManager
from .batch_submission import BatchSubmissionResult

logger = create_service_logger("cj_assessment_service.batch_retry_processor")


class BatchRetryProcessor:
    """Handles retry batch processing and end-of-batch fairness logic."""

    def __init__(
        self,
        database: CJRepositoryProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
        pool_manager: BatchPoolManager,
        batch_submitter: BatchProcessorProtocol,
    ) -> None:
        """Initialize batch retry processor.

        Args:
            database: Database access protocol implementation
            llm_interaction: LLM interaction protocol implementation
            settings: Application settings
            pool_manager: Pool manager for failed comparison handling
            batch_submitter: Core batch submission handler (protocol)
        """
        self.database = database
        self.llm_interaction = llm_interaction
        self.settings = settings
        self.pool_manager = pool_manager
        self.batch_submitter = batch_submitter

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
            cj_batch_id: CJ batch ID for tracking
            correlation_id: Request correlation ID for tracing
            force_retry_all: Whether to force retry of all remaining failures
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            BatchSubmissionResult if retry batch submitted, None if not needed

        Raises:
            HuleEduError: On retry batch submission failure
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
            retry_tasks = await self.pool_manager.form_retry_batch(
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

            # Submit retry batch using core submitter
            result = cast(
                BatchSubmissionResult,
                await self.batch_submitter.submit_comparison_batch(
                    cj_batch_id=cj_batch_id,
                    comparison_tasks=retry_tasks,
                    correlation_id=correlation_id,
                    config_overrides=None,  # Use defaults for retry
                    model_override=model_override,
                    temperature_override=temperature_override,
                    max_tokens_override=max_tokens_override,
                ),
            )

            if force_retry_all:
                logger.info(
                    f"End-of-batch processing: Successfully submitted {result.total_submitted} "
                    f"remaining failed comparisons for batch {cj_batch_id} to ensure fairness",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "retry_tasks_submitted": result.total_submitted,
                        "force_retry_all": force_retry_all,
                    },
                )
            else:
                logger.info(
                    f"Threshold-based retry: Successfully submitted retry batch for batch "
                    f"{cj_batch_id} with {result.total_submitted} tasks",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "retry_tasks_submitted": result.total_submitted,
                        "force_retry_all": force_retry_all,
                    },
                )

            # Record retry batch submission metric
            from services.cj_assessment_service.metrics import get_business_metrics

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

            raise_processing_error(
                service="cj_assessment_service",
                operation="submit_retry_batch",
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

        Args:
            cj_batch_id: CJ batch ID for tracking
            correlation_id: Request correlation ID for tracing
            model_override: Optional model name override
            temperature_override: Optional temperature override
            max_tokens_override: Optional max tokens override

        Returns:
            BatchSubmissionResult if failures processed, None if nothing to process

        Raises:
            HuleEduError: On end-of-batch processing failure
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

            raise_processing_error(
                service="cj_assessment_service",
                operation="process_remaining_failed_comparisons",
                message=f"Failed to process remaining failed comparisons: {str(e)}",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="end_of_batch_retry_processing",
            )

from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair

logger = create_service_logger("cj_assessment_service.callback_retry_coordinator")


class ComparisonRetryCoordinator:
    """Manage retry pool operations for failed comparisons."""

    async def add_failed_comparison_to_pool(
        self,
        *,
        pool_manager: Any,
        retry_processor: Any,
        comparison_pair: ComparisonPair,
        comparison_result: Any,
        correlation_id: UUID,
    ) -> None:
        try:
            comparison_task = await self.reconstruct_comparison_task(
                comparison_pair=comparison_pair, correlation_id=correlation_id
            )
            if not comparison_task:
                return

            failure_reason = (
                comparison_result.error_detail.error_code.value
                if comparison_result.error_detail
                else "unknown_error"
            )

            await pool_manager.add_to_failed_pool(
                cj_batch_id=comparison_pair.cj_batch_id,
                comparison_task=comparison_task,
                failure_reason=failure_reason,
                correlation_id=correlation_id,
            )

            retry_needed = await pool_manager.check_retry_batch_needed(
                cj_batch_id=comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
                force_retry_all=False,
            )
            if retry_needed:
                logger.info(
                    "Triggering retry batch for batch %s",
                    comparison_pair.cj_batch_id,
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": comparison_pair.cj_batch_id,
                    },
                )
                await retry_processor.submit_retry_batch(
                    cj_batch_id=comparison_pair.cj_batch_id,
                    correlation_id=correlation_id,
                )
        except Exception as e:
            logger.error(
                "Failed to add comparison to failed pool",
                extra={
                    "correlation_id": str(correlation_id),
                    "comparison_pair_id": comparison_pair.id,
                    "error": str(e),
                },
                exc_info=True,
            )
            # Don't re-raise - we don't want to fail the callback processing

    async def handle_successful_retry(
        self,
        *,
        pool_manager: Any,
        comparison_pair: ComparisonPair,
        correlation_id: UUID,
    ) -> None:
        try:
            from services.cj_assessment_service.metrics import get_business_metrics
            from services.cj_assessment_service.models_api import FailedComparisonPool

            from .batch_submission import get_batch_state, merge_batch_processing_metadata

            batch_state = await get_batch_state(
                session_provider=pool_manager.database,
                cj_batch_id=comparison_pair.cj_batch_id,
                correlation_id=correlation_id,
            )
            if not batch_state or not batch_state.processing_metadata:
                return

            failed_pool = FailedComparisonPool.model_validate(batch_state.processing_metadata)
            original_pool_size = len(failed_pool.failed_comparison_pool)
            failed_pool.failed_comparison_pool = [
                entry
                for entry in failed_pool.failed_comparison_pool
                if not (
                    entry.essay_a_id == comparison_pair.essay_a_els_id
                    and entry.essay_b_id == comparison_pair.essay_b_els_id
                )
            ]

            if len(failed_pool.failed_comparison_pool) < original_pool_size:
                failed_pool.pool_statistics.successful_retries += 1
                business_metrics = get_business_metrics()
                successful_retries_metric = business_metrics.get("cj_successful_retries_total")
                pool_size_metric = business_metrics.get("cj_failed_pool_size")

                if successful_retries_metric:
                    successful_retries_metric.inc()
                if pool_size_metric:
                    pool_size_metric.labels(batch_id=str(comparison_pair.cj_batch_id)).set(
                        len(failed_pool.failed_comparison_pool)
                    )

                await merge_batch_processing_metadata(
                    session_provider=pool_manager.database,
                    cj_batch_id=comparison_pair.cj_batch_id,
                    metadata_updates=failed_pool.model_dump(mode="json"),
                    correlation_id=correlation_id,
                )
                logger.info(
                    "Removed successful retry from failed pool for batch %s",
                    comparison_pair.cj_batch_id,
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": comparison_pair.cj_batch_id,
                        "essay_a_id": comparison_pair.essay_a_els_id,
                        "essay_b_id": comparison_pair.essay_b_els_id,
                    },
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to handle successful retry: %s",
                exc,
                extra={
                    "correlation_id": str(correlation_id),
                    "comparison_pair_id": comparison_pair.id,
                    "cj_batch_id": comparison_pair.cj_batch_id,
                    "error": str(exc),
                },
                exc_info=True,
            )

    async def reconstruct_comparison_task(
        self, *, comparison_pair: ComparisonPair, correlation_id: UUID
    ) -> ComparisonTask | None:
        try:
            essay_a = EssayForComparison(
                id=comparison_pair.essay_a_els_id,
                text_content="[Essay content would be fetched from database]",
                current_bt_score=None,
            )
            essay_b = EssayForComparison(
                id=comparison_pair.essay_b_els_id,
                text_content="[Essay content would be fetched from database]",
                current_bt_score=None,
            )
            return ComparisonTask(
                essay_a=essay_a, essay_b=essay_b, prompt=comparison_pair.prompt_text
            )
        except Exception as exc:
            logger.error(
                "Failed to reconstruct comparison task: %s",
                exc,
                extra={
                    "correlation_id": str(correlation_id),
                    "comparison_pair_id": comparison_pair.id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return None

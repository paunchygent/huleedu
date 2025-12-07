from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.protocols import CJBatchRepositoryProtocol

logger = create_service_logger("cj_assessment_service.batch_completion_policy")


class BatchCompletionPolicy:
    """Encapsulate completion heuristics and counter updates."""

    async def check_batch_completion_conditions(
        self,
        *,
        batch_id: int,
        batch_repo: CJBatchRepositoryProtocol,
        session: AsyncSession,
        correlation_id: UUID,
    ) -> bool:
        try:
            batch_state = await batch_repo.get_batch_state(session=session, batch_id=batch_id)
            if not batch_state:
                return False

            try:
                denominator = batch_state.completion_denominator()
            except RuntimeError as e:
                # Missing/invalid total_budget indicates a bug in batch setup.
                # Log the error and return False to prevent cascading failures.
                logger.error(
                    "Cannot check completion conditions: %s",
                    e,
                    extra={
                        "correlation_id": str(correlation_id),
                        "batch_id": batch_id,
                        "total_budget": batch_state.total_budget,
                        "error_type": "missing_total_budget",
                    },
                )
                return False

            if denominator > 0 and batch_state.completed_comparisons >= denominator * 0.8:
                completion_rate = batch_state.completed_comparisons / denominator
                logger.info(
                    (
                        "Batch %s completion detected: %s/%s comparisons "
                        "completed (80%%+ threshold reached)"
                    ),
                    batch_id,
                    batch_state.completed_comparisons,
                    denominator,
                    extra={
                        "correlation_id": str(correlation_id),
                        "batch_id": batch_id,
                        "completion_rate": completion_rate,
                    },
                )
                return True
            return False
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to check batch completion conditions for batch %s: %s",
                batch_id,
                exc,
                extra={
                    "correlation_id": str(correlation_id),
                    "batch_id": batch_id,
                    "error": str(exc),
                },
                exc_info=True,
            )
            return False

    async def update_batch_completion_counters(
        self,
        *,
        batch_repo: CJBatchRepositoryProtocol,
        session: AsyncSession,
        batch_id: int,
        is_error: bool,
        correlation_id: UUID,
    ) -> None:
        try:
            batch_state = await batch_repo.get_batch_state(session=session, batch_id=batch_id)
            if not batch_state:
                logger.error("Batch state not found for batch %s", batch_id)
                return

            if is_error:
                batch_state.failed_comparisons += 1
                logger.info(
                    "Batch %s failed_comparisons: %s", batch_id, batch_state.failed_comparisons
                )
            else:
                batch_state.completed_comparisons += 1
                logger.info(
                    "Batch %s completed_comparisons: %s",
                    batch_id,
                    batch_state.completed_comparisons,
                )

            batch_state.last_activity_at = datetime.now(UTC)

            # Check if partial scoring should be triggered using total_budget
            # (via completion_denominator) instead of legacy total_comparisons
            try:
                denominator = batch_state.completion_denominator()
                if (
                    not batch_state.partial_scoring_triggered
                    and batch_state.completed_comparisons
                    >= denominator * batch_state.completion_threshold_pct / 100
                ):
                    batch_state.partial_scoring_triggered = True
                    logger.info(
                        "Batch %s partial scoring triggered at %s%% completion",
                        batch_id,
                        batch_state.completion_threshold_pct,
                    )
            except RuntimeError:
                # Skip partial scoring trigger if batch has missing/invalid total_budget.
                # The error will be surfaced when other completion checks are attempted.
                pass
        except Exception as exc:  # pragma: no cover - defensive
            logger.error(
                "Failed to update batch completion counters for batch %s: %s",
                batch_id,
                exc,
                exc_info=True,
            )

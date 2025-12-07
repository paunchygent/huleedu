"""Batch completion checker for CJ Assessment Service.

This module provides completion threshold evaluation and terminal state checking
for CJ Assessment batches with configurable completion thresholds.
"""

from __future__ import annotations

from uuid import UUID

from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import HuleEduError, raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    SessionProviderProtocol,
)

from .batch_config import BatchConfigOverrides, get_effective_threshold

logger = create_service_logger("cj_assessment_service.batch_completion_checker")


class BatchCompletionChecker:
    """Handles batch completion evaluation and threshold checking."""

    def __init__(
        self,
        session_provider: SessionProviderProtocol,
        batch_repo: CJBatchRepositoryProtocol,
    ) -> None:
        """Initialize batch completion checker.

        Args:
            session_provider: Session provider for database access
            batch_repo: Batch repository for batch state operations
        """
        self._session_provider = session_provider
        self._batch_repo = batch_repo

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
            HuleEduError: On database operation failure
        """
        try:
            async with self._session_provider.session() as session:
                # Get batch state from database
                batch_state = await self._batch_repo.get_batch_state(
                    session=session, batch_id=cj_batch_id
                )

                if not batch_state:
                    raise_processing_error(
                        service="cj_assessment_service",
                        operation="check_batch_completion",
                        message="Batch state not found",
                        correlation_id=correlation_id,
                        database_operation="get_batch_state",
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
                try:
                    denominator = batch_state.completion_denominator()
                except RuntimeError as e:
                    # Missing/invalid total_budget indicates a bug in batch setup.
                    # Log the error and return False (batch not complete) to prevent
                    # cascading failures while surfacing the issue in observability.
                    logger.error(
                        "Cannot check completion: %s",
                        e,
                        extra={
                            "correlation_id": str(correlation_id),
                            "cj_batch_id": cj_batch_id,
                            "total_budget": batch_state.total_budget,
                            "error_type": "missing_total_budget",
                        },
                    )
                    return False

                if denominator > 0:
                    completion_rate = batch_state.completed_comparisons / denominator

                    # Get effective threshold
                    threshold = get_effective_threshold(config_overrides, batch_state)

                    logger.info(
                        f"Batch {cj_batch_id} completion check: "
                        f"{batch_state.completed_comparisons}/{denominator} "
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

            if isinstance(e, HuleEduError):
                raise
            else:
                raise_processing_error(
                    service="cj_assessment_service",
                    operation="check_batch_completion",
                    message=f"Failed to check batch completion: {str(e)}",
                    correlation_id=correlation_id,
                    database_operation="check_batch_completion",
                    entity_id=str(cj_batch_id),
                )

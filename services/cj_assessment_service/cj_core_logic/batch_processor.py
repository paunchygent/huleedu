"""Core batch submission processor for CJ Assessment Service.

This module provides the core BatchProcessor class focused on batch submission orchestration
with configurable batch sizes, state management integration, and comprehensive error handling.
Completion checking and retry processing are handled by dedicated modules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

from .batch_config import (
    BatchConfigOverrides,
    get_effective_batch_size,
)
from .batch_submission import (
    BatchSubmissionResult,
    submit_batch_chunk,
    update_batch_state_in_session,
    update_submitted_count_in_session,
)

logger = create_service_logger("cj_assessment_service.batch_processor")


class BatchProcessor:
    """Handles core batch submission orchestration for CJ Assessment Service."""

    def __init__(
        self,
        database: CJRepositoryProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
    ) -> None:
        """Initialize core batch processor.

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
            HuleEduError: On batch submission failure, database operation failure,
                         or LLM provider communication failure
        """
        if not comparison_tasks:
            raise_processing_error(
                service="cj_assessment_service",
                operation="submit_comparison_tasks",
                message="No comparison tasks provided for batch submission",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="batch_submission",
            )

        # Get effective batch size
        effective_batch_size = get_effective_batch_size(self.settings, config_overrides)

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

                await submit_batch_chunk(
                    batch_tasks=batch_tasks,
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                    llm_interaction=self.llm_interaction,
                    database=self.database,  # Pass database for tracking records
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

            # Re-raise all exceptions using factory for consistency
            raise_processing_error(
                service="cj_assessment_service",
                operation="submit_comparison_tasks",
                message=f"Batch submission failed: {str(e)}",
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                processing_stage="batch_submission",
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
            HuleEduError: On batch submission failure
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

    # Private helper methods
    async def _update_batch_state(
        self,
        cj_batch_id: int,
        state: CJBatchStateEnum,
        correlation_id: UUID,
    ) -> None:
        """Update batch state in database."""
        try:
            async with self.database.session() as session:
                await update_batch_state_in_session(
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

            raise_processing_error(
                service="cj_assessment_service",
                operation="update_batch_state",
                message=f"Failed to update batch state to {state.value}: {str(e)}",
                correlation_id=correlation_id,
                database_operation="update_batch_state",
                entity_id=str(cj_batch_id),
            )

    async def _update_submitted_count(
        self,
        cj_batch_id: int,
        submitted_count: int,
        correlation_id: UUID,
    ) -> None:
        """Update submitted comparisons count in database."""
        try:
            async with self.database.session() as session:
                await update_submitted_count_in_session(
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

            raise_processing_error(
                service="cj_assessment_service",
                operation="update_submitted_count",
                message=f"Failed to update submitted count: {str(e)}",
                correlation_id=correlation_id,
                database_operation="update_submitted_count",
                entity_id=str(cj_batch_id),
            )

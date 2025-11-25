"""Core batch submission processor for CJ Assessment Service.

This module provides the core BatchProcessor class focused on batch submission orchestration
with configurable batch sizes, state management integration, and comprehensive error handling.
Completion checking and retry processing are handled by dedicated modules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from common_core import LLMProviderType
from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import raise_processing_error
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.models_api import CJAssessmentRequestData, ComparisonTask
from services.cj_assessment_service.models_db import CJBatchState
from services.cj_assessment_service.protocols import (
    CJBatchRepositoryProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)

from .batch_config import (
    BatchConfigOverrides,
    get_effective_batch_size,
)
from .batch_submission import (
    BatchSubmissionResult,
    submit_batch_chunk,
    update_batch_state,
)

logger = create_service_logger("cj_assessment_service.batch_processor")


class BatchProcessor:
    """Handles core batch submission orchestration for CJ Assessment Service."""

    def __init__(
        self,
        session_provider: SessionProviderProtocol,
        llm_interaction: LLMInteractionProtocol,
        settings: Settings,
        batch_repository: CJBatchRepositoryProtocol,
    ) -> None:
        """Initialize core batch processor.

        Args:
            session_provider: Session provider protocol implementation
            llm_interaction: LLM interaction protocol implementation
            settings: Application settings
            batch_repository: Batch repository for state persistence
        """
        self._session_provider = session_provider
        self.llm_interaction = llm_interaction
        self.settings = settings
        self._batch_repository = batch_repository

    async def submit_comparison_batch(
        self,
        cj_batch_id: int,
        comparison_tasks: list[ComparisonTask],
        correlation_id: UUID,
        config_overrides: BatchConfigOverrides | None = None,
        model_override: str | None = None,
        temperature_override: float | None = None,
        max_tokens_override: int | None = None,
        system_prompt_override: str | None = None,
        provider_override: str | LLMProviderType | None = None,
        metadata_context: dict[str, Any] | None = None,
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
            # Update batch state to WAITING_CALLBACKS and set total comparisons
            await self._update_batch_state_with_totals(
                cj_batch_id=cj_batch_id,
                state=CJBatchStateEnum.WAITING_CALLBACKS,
                iteration_comparisons=len(comparison_tasks),
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
                    session_provider=self._session_provider,
                    batch_repository=self._batch_repository,
                    model_override=model_override,
                    temperature_override=temperature_override,
                    max_tokens_override=max_tokens_override,
                    system_prompt_override=system_prompt_override,
                    provider_override=provider_override,
                    metadata_context=metadata_context,
                )

                total_submitted += len(batch_tasks)

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
        request_data: CJAssessmentRequestData,
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
        if request_data.batch_config_overrides is not None:
            config_overrides = BatchConfigOverrides(**request_data.batch_config_overrides)

        # Extract LLM overrides from request data
        llm_config_overrides = request_data.llm_config_overrides
        model_override = None
        temperature_override = None
        max_tokens_override = None
        provider_override = None
        # Use CJ's canonical system prompt as default (can be overridden by event)
        system_prompt_override = self.settings.SYSTEM_PROMPT

        if llm_config_overrides:
            model_override = llm_config_overrides.model_override
            temperature_override = llm_config_overrides.temperature_override
            max_tokens_override = llm_config_overrides.max_tokens_override
            provider_override = llm_config_overrides.provider_override
            # Only override system prompt if explicitly provided (not None)
            if llm_config_overrides.system_prompt_override is not None:
                system_prompt_override = llm_config_overrides.system_prompt_override

        return await self.submit_comparison_batch(
            cj_batch_id=cj_batch_id,
            comparison_tasks=comparison_tasks,
            correlation_id=correlation_id,
            config_overrides=config_overrides,
            model_override=model_override,
            temperature_override=temperature_override,
            max_tokens_override=max_tokens_override,
            system_prompt_override=system_prompt_override,
            provider_override=provider_override,
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
            await update_batch_state(
                session_provider=self._session_provider,
                batch_repository=self._batch_repository,
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

    async def _update_batch_state_with_totals(
        self,
        cj_batch_id: int,
        state: CJBatchStateEnum,
        iteration_comparisons: int,
        correlation_id: UUID,
    ) -> None:
        """Update batch state with cumulative totals and iteration counter."""

        try:
            async with self._session_provider.session() as session:
                batch_state = await self._batch_repository.get_batch_state_for_update(
                    session=session,
                    batch_id=cj_batch_id,
                    for_update=True,
                )

                if batch_state is None:
                    raise ValueError(f"Batch state not found for batch_id={cj_batch_id}")

                is_first_submission = (
                    batch_state.total_budget is None or batch_state.current_iteration == 0
                )

                if is_first_submission:
                    batch_state.total_budget = self._resolve_total_budget(
                        batch_state=batch_state,
                        iteration_comparisons=iteration_comparisons,
                    )
                    batch_state.total_comparisons = iteration_comparisons
                    batch_state.submitted_comparisons = iteration_comparisons
                    batch_state.current_iteration = 1
                else:
                    batch_state.total_comparisons += iteration_comparisons
                    batch_state.submitted_comparisons += iteration_comparisons
                    batch_state.current_iteration += 1

                batch_state.state = state
                await session.commit()

                logger.info(
                    "Updated batch state with cumulative totals",
                    extra={
                        "correlation_id": str(correlation_id),
                        "cj_batch_id": cj_batch_id,
                        "state": state.value,
                        "iteration_comparisons": iteration_comparisons,
                        "total_comparisons": batch_state.total_comparisons,
                        "total_budget": batch_state.total_budget,
                        "current_iteration": batch_state.current_iteration,
                    },
                )

        except Exception as e:
            logger.error(
                f"Failed to update batch state with totals for CJ batch {cj_batch_id}: {e}",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "target_state": state.value,
                    "iteration_comparisons": iteration_comparisons,
                    "error": str(e),
                },
                exc_info=True,
            )

            raise_processing_error(
                service="cj_assessment_service",
                operation="update_batch_state_with_totals",
                message=f"Failed to update batch state with totals: {str(e)}",
                correlation_id=correlation_id,
                database_operation="update_batch_state_with_totals",
                entity_id=str(cj_batch_id),
            )

    @staticmethod
    def _resolve_total_budget(
        batch_state: "CJBatchState",
        iteration_comparisons: int,
    ) -> int:
        """Determine the correct total comparison budget for the batch."""

        metadata = batch_state.processing_metadata or {}
        requested_budget: int | None = None

        if isinstance(metadata, dict):
            budget_block = metadata.get("comparison_budget")
            if isinstance(budget_block, dict):
                requested_budget = budget_block.get("max_pairs_requested")

        if requested_budget and isinstance(requested_budget, int) and requested_budget > 0:
            return requested_budget

        if batch_state.total_budget and batch_state.total_budget > 0:
            return batch_state.total_budget

        if batch_state.total_comparisons and batch_state.total_comparisons > 0:
            return batch_state.total_comparisons

        return iteration_comparisons

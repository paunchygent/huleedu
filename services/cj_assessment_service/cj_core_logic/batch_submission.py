"""Batch submission operations for CJ Assessment Service.

This module handles low-level batch submission operations and database state management.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from common_core.status_enums import CJBatchStateEnum
from services.cj_assessment_service.exceptions import LLMProviderError
from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.protocols import LLMInteractionProtocol

logger = create_service_logger("cj_assessment_service.batch_submission")


class BatchSubmissionResult(BaseModel):
    """Result of batch submission operation."""

    batch_id: int = Field(description="CJ batch ID")
    total_submitted: int = Field(description="Number of comparisons submitted")
    submitted_at: datetime = Field(description="Submission timestamp")
    all_submitted: bool = Field(description="Whether all comparisons were submitted")
    correlation_id: UUID = Field(description="Request correlation ID")


async def submit_batch_chunk(
    batch_tasks: list[ComparisonTask],
    cj_batch_id: int,
    correlation_id: UUID,
    llm_interaction: LLMInteractionProtocol,
    model_override: str | None = None,
    temperature_override: float | None = None,
    max_tokens_override: int | None = None,
) -> None:
    """Submit a chunk of comparison tasks.

    Args:
        batch_tasks: List of comparison tasks to submit
        cj_batch_id: CJ batch ID for tracking
        correlation_id: Request correlation ID for tracing
        llm_interaction: LLM interaction protocol implementation
        model_override: Optional model name override
        temperature_override: Optional temperature override
        max_tokens_override: Optional max tokens override

    Raises:
        LLMProviderError: On LLM provider communication failure
    """
    try:
        # Use existing LLM interaction protocol for batch submission
        # This will handle async processing (returns None for queued requests)
        results = await llm_interaction.perform_comparisons(
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


async def update_batch_state_in_session(
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


async def update_submitted_count_in_session(
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


async def get_batch_state(session: AsyncSession, cj_batch_id: int, correlation_id: UUID) -> Any:
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


async def update_batch_processing_metadata(
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

"""Batch submission operations for CJ Assessment Service.

This module handles low-level batch submission operations and database state management.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from common_core.status_enums import CJBatchStateEnum
from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonTask
from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    LLMInteractionProtocol,
)

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
    database: CJRepositoryProtocol | None = None,
    model_override: str | None = None,
    temperature_override: float | None = None,
    max_tokens_override: int | None = None,
) -> None:
    """Submit a chunk of comparison tasks with tracking.

    Args:
        batch_tasks: List of comparison tasks to submit
        cj_batch_id: CJ batch ID for tracking
        correlation_id: Request correlation ID for tracing
        llm_interaction: LLM interaction protocol implementation
        database: Optional database for creating tracking records
        model_override: Optional model name override
        temperature_override: Optional temperature override
        max_tokens_override: Optional max tokens override

    Raises:
        HuleEduError: On LLM provider communication failure
    """
    try:
        # Create tracking records if database is provided
        if database is not None:
            from .batch_submission_tracking import create_tracking_records

            async with database.session() as session:
                await create_tracking_records(
                    session=session,
                    batch_tasks=batch_tasks,
                    cj_batch_id=cj_batch_id,
                    correlation_id=correlation_id,
                )
                await session.commit()

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

        raise_external_service_error(
            service="cj_assessment_service",
            operation="submit_batch_chunk",
            message=f"Failed to submit batch chunk: {str(e)}",
            correlation_id=correlation_id,
            external_service="LLM Provider Service",
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


async def get_batch_state(
    session: AsyncSession, cj_batch_id: int, correlation_id: UUID, for_update: bool = False
) -> Any:
    """Get batch state from database.

    Args:
        session: Database session
        cj_batch_id: CJ batch ID
        correlation_id: Request correlation ID for tracing
        for_update: If True, lock the row for update (prevents concurrent modifications)

    Returns:
        Batch state object or None if not found
    """
    # This would need to be implemented based on the repository protocol
    # For now, we'll use a placeholder that demonstrates the pattern
    from sqlalchemy import select
    from sqlalchemy.orm import noload

    from services.cj_assessment_service.models_db import CJBatchState

    try:
        if for_update:
            # When locking for update, use a simple query without any relationship loading
            # to avoid "FOR UPDATE cannot be applied to nullable side of outer join" error
            stmt = (
                select(CJBatchState)
                .where(CJBatchState.batch_id == cj_batch_id)
                .options(noload("*"))  # Disable all relationship loading
                .with_for_update()
            )
        else:
            stmt = select(CJBatchState).where(CJBatchState.batch_id == cj_batch_id)
        result = await session.execute(stmt)
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


async def append_to_failed_pool_atomic(
    session: AsyncSession,
    cj_batch_id: int,
    failed_entry_json: dict[str, Any],
    correlation_id: UUID,
) -> None:
    """Atomically append a failed comparison to the pool using JSONB operations.

    This function uses PostgreSQL's atomic JSONB operations to append to the failed pool
    without needing to read-modify-write, eliminating race conditions.

    Args:
        session: Database session
        cj_batch_id: CJ batch ID
        failed_entry_json: Failed entry data as JSON-serializable dict
        correlation_id: Request correlation ID for tracing

    Raises:
        DatabaseOperationError: On database operation failure
    """
    from sqlalchemy import text

    try:
        # Use raw SQL for atomic JSONB operations
        # The -> operator extracts as json, so cast back to jsonb for concatenation
        stmt = text("""
            UPDATE cj_batch_states
            SET processing_metadata =
                CASE
                    WHEN processing_metadata IS NULL THEN
                        CAST(:initial_pool AS jsonb)
                    ELSE
                        jsonb_build_object(
                            'failed_comparison_pool',
                            CASE
                                WHEN processing_metadata->'failed_comparison_pool' IS NULL THEN CAST(:entry AS jsonb)
                                ELSE (processing_metadata->'failed_comparison_pool')::jsonb || CAST(:entry AS jsonb)
                            END,
                            'pool_statistics',
                            jsonb_build_object(
                                'total_failed', COALESCE((processing_metadata->'pool_statistics'->>'total_failed')::int, 0) + 1,
                                'retry_attempts', COALESCE((processing_metadata->'pool_statistics'->>'retry_attempts')::int, 0),
                                'last_retry_batch', processing_metadata->'pool_statistics'->>'last_retry_batch',
                                'successful_retries', COALESCE((processing_metadata->'pool_statistics'->>'successful_retries')::int, 0),
                                'permanently_failed', COALESCE((processing_metadata->'pool_statistics'->>'permanently_failed')::int, 0)
                            )
                        )
                END
            WHERE batch_id = :batch_id
        """)

        # Create initial pool structure if metadata is null
        initial_pool = {
            "failed_comparison_pool": [failed_entry_json],
            "pool_statistics": {
                "total_failed": 1,
                "retry_attempts": 0,
                "last_retry_batch": None,
                "successful_retries": 0,
                "permanently_failed": 0,
            },
        }

        await session.execute(
            stmt,
            {
                "batch_id": cj_batch_id,
                "entry": json.dumps([failed_entry_json]),
                "initial_pool": json.dumps(initial_pool),
            },
        )
        await session.commit()

        logger.debug(
            f"Atomically appended to failed pool for batch {cj_batch_id}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
            },
        )

    except Exception as e:
        logger.error(
            f"Failed to atomically append to failed pool: {e}",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "error": str(e),
            },
            exc_info=True,
        )
        raise

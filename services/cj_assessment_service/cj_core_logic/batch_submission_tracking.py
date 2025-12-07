"""Tracking record creation for batch submission.

This module handles creation of ComparisonPair tracking records when
comparisons are submitted to the LLM Provider Service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.pair_generation import PairGenerationMode
from services.cj_assessment_service.models_db import ComparisonPair

if TYPE_CHECKING:
    from services.cj_assessment_service.models_api import ComparisonTask

logger = create_service_logger("cj_assessment_service.batch_submission_tracking")


async def create_tracking_records(
    session: AsyncSession,
    batch_tasks: list[ComparisonTask],
    cj_batch_id: int,
    correlation_id: UUID,
    pair_generation_mode: PairGenerationMode | None = None,
) -> dict[tuple[str, str], UUID]:
    """Create ComparisonPair tracking records for submitted tasks.

    This creates the tracking records that will later be updated by callbacks
    from the LLM Provider Service.

    Args:
        session: Database session
        batch_tasks: List of comparison tasks being submitted
        cj_batch_id: CJ batch ID
        correlation_id: Parent correlation ID for the batch
        pair_generation_mode: Generation mode (COVERAGE or RESAMPLING).
            If None, defaults to "coverage" for backwards compatibility.

    Returns:
        Dictionary mapping (essay_a_id, essay_b_id) to request_correlation_id
    """
    tracking_map = {}

    for task in batch_tasks:
        # Generate unique correlation ID for this comparison request
        request_correlation_id = uuid4()

        # Create tracking record (no winner yet - will be updated by callback)
        comparison_pair = ComparisonPair(
            cj_batch_id=cj_batch_id,
            essay_a_els_id=task.essay_a.id,
            essay_b_els_id=task.essay_b.id,
            prompt_text=task.prompt,
            request_correlation_id=request_correlation_id,
            submitted_at=datetime.now(UTC),
            # No winner, confidence, or completion time yet
            winner=None,
            confidence=None,
            justification=None,
            completed_at=None,
            # Pair generation mode for per-mode positional fairness observability
            pair_generation_mode=(
                pair_generation_mode.value if pair_generation_mode else "coverage"
            ),
        )
        session.add(comparison_pair)

        # Track the correlation ID for this comparison
        tracking_map[(task.essay_a.id, task.essay_b.id)] = request_correlation_id

    # Flush to ensure records are created
    await session.flush()

    logger.info(
        f"Created {len(batch_tasks)} tracking records for CJ batch {cj_batch_id}",
        extra={
            "correlation_id": str(correlation_id),
            "cj_batch_id": cj_batch_id,
            "tracking_count": len(batch_tasks),
        },
    )

    return tracking_map

"""Positional fairness test helpers for CJ comparison pairs.

These helpers live in the test tree only and provide small, DB-backed
utilities for analysing A/B positional usage over ComparisonPair rows.
"""

from __future__ import annotations

from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair


async def get_positional_counts_for_batch(
    session: AsyncSession,
    cj_batch_id: int,
) -> dict[str, dict[str, int]]:
    """Return per-essay A/B positional counts for a CJ batch.

    The result maps each essay's ELS ID to a dict of the form:
        {essay_id: {"A": count_as_A, "B": count_as_B}}
    where counts are derived from ComparisonPair rows for the given batch.
    """

    # Count appearances in essay_a position.
    stmt_a = (
        select(CJ_ComparisonPair.essay_a_els_id, func.count())
        .where(CJ_ComparisonPair.cj_batch_id == cj_batch_id)
        .group_by(CJ_ComparisonPair.essay_a_els_id)
    )
    result_a = await session.execute(stmt_a)
    counts_a: Dict[str, int] = {row[0]: int(row[1]) for row in result_a.all()}

    # Count appearances in essay_b position.
    stmt_b = (
        select(CJ_ComparisonPair.essay_b_els_id, func.count())
        .where(CJ_ComparisonPair.cj_batch_id == cj_batch_id)
        .group_by(CJ_ComparisonPair.essay_b_els_id)
    )
    result_b = await session.execute(stmt_b)
    counts_b: Dict[str, int] = {row[0]: int(row[1]) for row in result_b.all()}

    # Normalise into per-essay A/B counts.
    positional_counts: dict[str, dict[str, int]] = {}
    for essay_id in set(counts_a.keys()) | set(counts_b.keys()):
        positional_counts[essay_id] = {
            "A": counts_a.get(essay_id, 0),
            "B": counts_b.get(essay_id, 0),
        }

    return positional_counts

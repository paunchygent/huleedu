"""Positional fairness test helpers for CJ comparison pairs.

These helpers live in the test tree only and provide small, DB-backed
utilities for analysing A/B positional usage over ComparisonPair rows.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    PerPairOrientationCounts,
)
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair


async def get_positional_counts_for_batch(
    session: AsyncSession,
    cj_batch_id: int,
    mode: str | None = None,
) -> dict[str, dict[str, int]]:
    """Return per-essay A/B positional counts for a CJ batch.

    Args:
        session: Database session
        cj_batch_id: CJ batch ID to query
        mode: Optional filter by pair_generation_mode ("coverage", "resampling", or None for all)

    Returns:
        Dict mapping essay_id to {"A": count_as_A, "B": count_as_B}
    """

    # Count appearances in essay_a position.
    stmt_a = select(CJ_ComparisonPair.essay_a_els_id, func.count()).where(
        CJ_ComparisonPair.cj_batch_id == cj_batch_id
    )
    if mode:
        stmt_a = stmt_a.where(CJ_ComparisonPair.pair_generation_mode == mode)
    stmt_a = stmt_a.group_by(CJ_ComparisonPair.essay_a_els_id)
    result_a = await session.execute(stmt_a)
    counts_a: Dict[str, int] = {row[0]: int(row[1]) for row in result_a.all()}

    # Count appearances in essay_b position.
    stmt_b = select(CJ_ComparisonPair.essay_b_els_id, func.count()).where(
        CJ_ComparisonPair.cj_batch_id == cj_batch_id
    )
    if mode:
        stmt_b = stmt_b.where(CJ_ComparisonPair.pair_generation_mode == mode)
    stmt_b = stmt_b.group_by(CJ_ComparisonPair.essay_b_els_id)
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


async def get_pair_orientation_counts_for_batch(
    session: AsyncSession,
    cj_batch_id: int,
    mode: str | None = None,
) -> PerPairOrientationCounts:
    """Return per-pair AB/BA orientation counts for a CJ batch.

    Args:
        session: Database session
        cj_batch_id: CJ batch ID to query
        mode: Optional filter by pair_generation_mode ("coverage", "resampling", or None for all)

    Returns:
        Dict mapping canonical pair keys to orientation counts:
        {(min_essay_id, max_essay_id): (AB_count, BA_count)}

    where:
        - AB_count = times the pair was seen with min_id in A position
        - BA_count = times the pair was seen with min_id in B position

    This matches the key format used by FairComplementOrientationStrategy.
    """
    stmt = select(
        CJ_ComparisonPair.essay_a_els_id,
        CJ_ComparisonPair.essay_b_els_id,
    ).where(CJ_ComparisonPair.cj_batch_id == cj_batch_id)

    if mode:
        stmt = stmt.where(CJ_ComparisonPair.pair_generation_mode == mode)

    result = await session.execute(stmt)
    rows = result.all()

    pair_counts: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])

    for essay_a_id, essay_b_id in rows:
        # Canonical key: (min_id, max_id)
        key = (min(essay_a_id, essay_b_id), max(essay_a_id, essay_b_id))

        # AB = min_id in A position, BA = min_id in B position
        if essay_a_id < essay_b_id:
            pair_counts[key][0] += 1  # AB orientation
        else:
            pair_counts[key][1] += 1  # BA orientation

    # Convert to immutable tuples
    return {k: (v[0], v[1]) for k, v in pair_counts.items()}


async def get_positional_fairness_report(
    session: AsyncSession,
    cj_batch_id: int,
    mode: str | None = None,
) -> dict:
    """Return comprehensive positional fairness data for a CJ batch.

    Args:
        session: Database session
        cj_batch_id: CJ batch ID to query
        mode: Optional filter by pair_generation_mode ("coverage", "resampling", or None for all)

    Returns:
        {
            "per_essay": {essay_id: {"A": int, "B": int}},
            "per_pair": {(min_id, max_id): (AB_count, BA_count)},
            "essay_count": int,
            "pair_count": int,
            "total_comparisons": int,
            "mode": str | None,
        }
    """
    per_essay = await get_positional_counts_for_batch(session, cj_batch_id, mode)
    per_pair = await get_pair_orientation_counts_for_batch(session, cj_batch_id, mode)

    total_comparisons = sum(ab + ba for ab, ba in per_pair.values())

    return {
        "per_essay": per_essay,
        "per_pair": per_pair,
        "essay_count": len(per_essay),
        "pair_count": len(per_pair),
        "total_comparisons": total_comparisons,
        "mode": mode,
    }

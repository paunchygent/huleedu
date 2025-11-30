"""Scoring and ranking logic for comparative judgment.

Adapted from the prototype's ranking_handler.py to work with the service architecture,
using string-based essay IDs and protocol-based database access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
from uuid import UUID

import choix
import numpy as np
from common_core import EssayComparisonWinner
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_cj_insufficient_comparisons,
    raise_cj_score_convergence_failed,
)
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.bt_inference import (
    BT_STANDARD_ERROR_MAX,
    compute_bt_standard_errors,
)
from services.cj_assessment_service.models_api import ComparisonResult, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair
from services.cj_assessment_service.models_db import ProcessedEssay as CJ_ProcessedEssay
from services.cj_assessment_service.protocols import (
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment_service.scoring_ranking")


@dataclass(frozen=True)
class BTScoringResult:
    """Pure domain result for a Bradley–Terry scoring run."""

    scores: dict[str, float]
    ses: dict[str, float]
    per_essay_counts: dict[str, int]
    se_summary: dict[str, float | int]


def compute_bt_scores_and_se(
    all_essays: list[EssayForComparison],
    comparisons: Sequence[CJ_ComparisonPair],
    *,
    cj_batch_id: int | None = None,
    correlation_id: UUID | None = None,
) -> BTScoringResult:
    """Compute BT scores, standard errors, and SE diagnostics for a batch.

    This helper is intentionally pure with respect to persistence concerns:
    it operates only on in-memory essay and comparison data and returns
    a BTScoringResult. It raises CJ-specific domain errors for:

    - insufficient usable comparisons
    - numerical failures in BT inference
    """
    unique_els_essay_ids = sorted({essay.id for essay in all_essays})
    n_items = len(unique_els_essay_ids)

    if n_items == 0:
        if cj_batch_id is not None and correlation_id is not None:
            raise_cj_insufficient_comparisons(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    "No essays available to compute Bradley-Terry scores for "
                    f"CJ Batch {cj_batch_id}."
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                comparison_count=0,
                required_count=1,
            )
        raise ValueError("No essays provided for BT scoring.")

    # First-level guard: no comparisons at all
    if len(comparisons) < 1:
        if cj_batch_id is not None and correlation_id is not None:
            raise_cj_insufficient_comparisons(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    "Not enough valid comparisons (0) in DB to compute scores for "
                    f"CJ Batch {cj_batch_id}. At least 1 comparison is required."
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                comparison_count=0,
                required_count=1,
            )
        raise ValueError("No comparisons provided for BT scoring.")

    els_id_to_idx_map = {els_id: i for i, els_id in enumerate(unique_els_essay_ids)}

    # Extract anchor indices for BT reference selection
    anchor_indices = [els_id_to_idx_map[essay.id] for essay in all_essays if essay.is_anchor]

    choix_comparison_data: list[tuple[int, int]] = []
    per_essay_counts: dict[str, int] = {els_id: 0 for els_id in unique_els_essay_ids}

    for comp in comparisons:
        # Only treat "essay_a"/"essay_b" as usable winners; errors are excluded.
        if comp.winner not in {"essay_a", "essay_b"}:
            continue

        winner_id_str = comp.essay_a_els_id if comp.winner == "essay_a" else comp.essay_b_els_id
        loser_id_str = comp.essay_b_els_id if comp.winner == "essay_a" else comp.essay_a_els_id

        if winner_id_str in els_id_to_idx_map and loser_id_str in els_id_to_idx_map:
            choix_comparison_data.append(
                (els_id_to_idx_map[winner_id_str], els_id_to_idx_map[loser_id_str]),
            )
            per_essay_counts[winner_id_str] += 1
            per_essay_counts[loser_id_str] += 1

    # Second-level guard: comparisons exist, but none mapped into the BT graph
    if not choix_comparison_data:
        if cj_batch_id is not None and correlation_id is not None:
            raise_cj_insufficient_comparisons(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    "No valid comparison data mapped for `choix` while computing "
                    f"BT scores for CJ Batch {cj_batch_id}."
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                comparison_count=0,
                required_count=1,
            )
        raise ValueError("No usable comparison data for BT scoring.")

    try:
        alpha = 0.01
        params = choix.ilsr_pairwise(n_items, choix_comparison_data, alpha=alpha)
        params -= np.mean(params)

        se_vec = compute_bt_standard_errors(
            n_items, choix_comparison_data, params, anchor_indices=anchor_indices
        )
    except Exception as exc:  # pragma: no cover - wrapped into domain error
        if cj_batch_id is not None and correlation_id is not None:
            raise_cj_score_convergence_failed(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    f"Error computing Bradley-Terry scores for CJ Batch {cj_batch_id}: {str(exc)}"
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                convergence_error=str(exc),
                comparison_count=len(choix_comparison_data),
            )
        raise

    updated_bt_scores: dict[str, float] = {
        unique_els_essay_ids[i]: float(params[i]) for i in range(n_items)
    }
    updated_bt_ses: dict[str, float] = {
        unique_els_essay_ids[i]: float(se_vec[i]) for i in range(n_items)
    }

    se_array = np.asarray(se_vec, dtype=float)
    comparison_count = len(choix_comparison_data)
    min_se = float(np.min(se_array)) if se_array.size > 0 else 0.0
    mean_se = float(np.mean(se_array)) if se_array.size > 0 else 0.0
    max_se = float(np.max(se_array)) if se_array.size > 0 else 0.0
    items_at_cap = int(np.sum(se_array >= BT_STANDARD_ERROR_MAX)) if se_array.size else 0

    comparison_counts = np.array(list(per_essay_counts.values()), dtype=int)
    isolated_items = int(np.sum(comparison_counts == 0)) if comparison_counts.size else 0
    mean_comparisons_per_item = float(np.mean(comparison_counts)) if comparison_counts.size else 0.0
    min_comparisons_per_item = int(np.min(comparison_counts)) if comparison_counts.size else 0
    max_comparisons_per_item = int(np.max(comparison_counts)) if comparison_counts.size else 0

    se_summary: dict[str, float | int] = {
        "mean_se": mean_se,
        "max_se": max_se,
        "min_se": min_se,
        "item_count": n_items,
        "comparison_count": comparison_count,
        "items_at_cap": items_at_cap,
        "isolated_items": isolated_items,
        "mean_comparisons_per_item": mean_comparisons_per_item,
        "min_comparisons_per_item": min_comparisons_per_item,
        "max_comparisons_per_item": max_comparisons_per_item,
    }

    return BTScoringResult(
        scores=updated_bt_scores,
        ses=updated_bt_ses,
        per_essay_counts=per_essay_counts,
        se_summary=se_summary,
    )


async def record_comparisons_and_update_scores(
    all_essays: list[EssayForComparison],  # essay.id is string els_essay_id
    comparison_results: Sequence[ComparisonResult | None],  # Can be None for async processing
    session_provider: SessionProviderProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    cj_batch_id: int,
    correlation_id: UUID,
    # settings: Settings # Pass settings if alpha for choix is configurable
    *,
    scoring_result_container: list[BTScoringResult] | None = None,
) -> dict[str, float]:  # Returns dict of els_essay_id -> score
    """Record comparison results and update Bradley-Terry scores using choix.

    Args:
        all_essays: List of all essays in the comparison batch (with string IDs)
        comparison_results: Results from LLM comparisons
        session_provider: Database session provider
        comparison_repository: Repository for comparison operations
        essay_repository: Repository for essay operations
        cj_batch_id: Internal CJ batch ID
        correlation_id: Request correlation ID for tracing

    Returns:
        Dictionary mapping essay IDs (strings) to updated BT scores
    """
    logger.info(
        f"Recording {len(comparison_results)} comparison results for CJ Batch ID: {cj_batch_id}",
        extra={
            "cj_batch_id": str(cj_batch_id),
            "correlation_id": correlation_id,
            "result_count": len(comparison_results),
        },
    )

    async with session_provider.session() as session:
        # 1. Store new comparison results
        successful_comparisons_this_round = 0
        for result in comparison_results:
            # Skip None results (async processing)
            if result is None:
                continue
            if result.llm_assessment:
                winner_db_val = None
                if result.llm_assessment.winner == EssayComparisonWinner.ESSAY_A:
                    winner_db_val = "essay_a"
                elif result.llm_assessment.winner == EssayComparisonWinner.ESSAY_B:
                    winner_db_val = "essay_b"

                # Extract error details if available
                error_code = None
                error_correlation_id = None
                error_timestamp = None
                error_service = None
                error_details = None
                if result.error_detail:
                    error_code = result.error_detail.error_code.value  # Convert enum to string
                    error_correlation_id = result.error_detail.correlation_id
                    error_timestamp = result.error_detail.timestamp
                    error_service = result.error_detail.service
                    error_details = result.error_detail.details

                new_pair = CJ_ComparisonPair(
                    cj_batch_id=cj_batch_id,
                    essay_a_els_id=result.task.essay_a.id,  # This is els_essay_id (string)
                    essay_b_els_id=result.task.essay_b.id,  # This is els_essay_id (string)
                    winner=winner_db_val,
                    prompt_text=result.task.prompt,
                    confidence=result.llm_assessment.confidence,
                    justification=result.llm_assessment.justification,
                    raw_llm_response=result.raw_llm_response_content,
                    error_code=error_code,
                    error_correlation_id=error_correlation_id,
                    error_timestamp=error_timestamp,
                    error_service=error_service,
                    error_details=error_details,
                )
                session.add(new_pair)

                # Only count successful comparisons (not errors)
                if result.llm_assessment.winner in {
                    EssayComparisonWinner.ESSAY_A,
                    EssayComparisonWinner.ESSAY_B,
                }:
                    successful_comparisons_this_round += 1

        if successful_comparisons_this_round > 0:
            await session.flush()  # Flush to save new pairs before querying all
        logger.info(
            f"Stored {successful_comparisons_this_round} new comparison pairs for "
            f"CJ Batch ID: {cj_batch_id}",
            extra={
                "cj_batch_id": str(cj_batch_id),
                "correlation_id": correlation_id,
                "successful_pairs": successful_comparisons_this_round,
            },
        )

        # 2. Fetch ALL valid comparisons for this cj_batch_id to compute scores
        stmt_all_comps = select(CJ_ComparisonPair).where(
            CJ_ComparisonPair.cj_batch_id == cj_batch_id,
            CJ_ComparisonPair.winner.isnot(None),  # Ensure there's a winner
            CJ_ComparisonPair.winner != "error",
        )
        all_db_comparisons_result = await session.execute(stmt_all_comps)
        all_valid_db_comparisons = all_db_comparisons_result.scalars().all()

        try:
            bt_result = compute_bt_scores_and_se(
                all_essays=all_essays,
                comparisons=all_valid_db_comparisons,
                cj_batch_id=cj_batch_id,
                correlation_id=correlation_id,
            )
        except HuleEduError:
            # Domain errors from BT scoring propagate unchanged.
            raise
        except Exception as exc:
            # Wrap unexpected failures in a convergence error for consistent semantics.
            raise_cj_score_convergence_failed(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    "Error computing/updating Bradley-Terry scores for "
                    f"CJ Batch {cj_batch_id}: {str(exc)}"
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                convergence_error=str(exc),
                comparison_count=len(all_valid_db_comparisons),
            )

        if scoring_result_container is not None:
            scoring_result_container.append(bt_result)

        logger.info(
            f"Successfully computed BT scores and SEs for {len(bt_result.scores)} essays in "
            f"CJ Batch {cj_batch_id}.",
            extra={
                "cj_batch_id": str(cj_batch_id),
                "correlation_id": str(correlation_id),
                "mean_se": bt_result.se_summary["mean_se"],
                "max_se": bt_result.se_summary["max_se"],
                "min_se": bt_result.se_summary["min_se"],
                "item_count": bt_result.se_summary["item_count"],
                "comparison_count": bt_result.se_summary["comparison_count"],
                "items_at_cap": bt_result.se_summary["items_at_cap"],
                "isolated_items": bt_result.se_summary["isolated_items"],
                "mean_comparisons_per_item": bt_result.se_summary["mean_comparisons_per_item"],
                "min_comparisons_per_item": bt_result.se_summary["min_comparisons_per_item"],
                "max_comparisons_per_item": bt_result.se_summary["max_comparisons_per_item"],
            },
        )

        # 3. Persist BT results in the database with a single transaction.
        # Update scores, SEs, and comparison counts in the database
        try:
            await _update_essay_scores_in_database(
                session,
                cj_batch_id,
                bt_result.scores,
                bt_result.ses,
                bt_result.per_essay_counts,
            )

            # Commit all changes (comparisons + scores)
            await session.commit()

            return bt_result.scores

        except Exception as e:
            raise_cj_score_convergence_failed(
                service="cj_assessment_service",
                operation="record_comparisons_and_update_scores",
                message=(
                    f"Error computing/updating Bradley-Terry scores for CJ Batch {cj_batch_id}: "
                    f"{str(e)}"
                ),
                correlation_id=correlation_id,
                batch_id=str(cj_batch_id),
                convergence_error=str(e),
                comparison_count=len(all_valid_db_comparisons),
            )


def check_score_stability(
    current_bt_scores: dict[str, float],
    previous_bt_scores: dict[str, float],
    stability_threshold: float = 0.05,
) -> float:
    """Check score stability by computing maximum change between iterations.

    Args:
        current_bt_scores: Current BT scores (essay_id -> score)
        previous_bt_scores: Previous BT scores (essay_id -> score)
        stability_threshold: Threshold for considering scores stable

    Returns:
        Maximum score change across all essays
    """
    if not previous_bt_scores:
        return float("inf")  # No previous scores, not stable

    max_change = 0.0
    for essay_id, current_score in current_bt_scores.items():
        previous_score = previous_bt_scores.get(essay_id, 0.0)
        change = abs(current_score - previous_score)
        max_change = max(max_change, change)

    return max_change


async def get_essay_rankings(
    session_provider: SessionProviderProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    cj_batch_id: int,  # This is the internal CJ_BatchUpload.id
    correlation_id: UUID,
) -> list[dict[str, Any]]:
    """Get final essay rankings for the CJ batch, ordered by score.

    Args:
        session_provider: Database session provider
        essay_repository: Repository for essay operations
        cj_batch_id: Internal CJ batch ID
        correlation_id: Request correlation ID for tracing

    Returns:
        List of essay ranking dictionaries sorted by score (highest first)
    """
    logger.info(
        f"Generating final rankings for CJ Batch ID: {cj_batch_id}",
        extra={
            "cj_batch_id": str(cj_batch_id),
            "correlation_id": correlation_id,
        },
    )

    async with session_provider.session() as session:
        stmt = (
            select(CJ_ProcessedEssay)
            .where(CJ_ProcessedEssay.cj_batch_id == cj_batch_id)
            .order_by(CJ_ProcessedEssay.current_bt_score.desc().nulls_last())
        )
        result = await session.execute(stmt)
        essays_with_scores = result.scalars().all()

        rankings = []
        for rank, db_row in enumerate(essays_with_scores, 1):
            rankings.append(
                {
                    "rank": rank,
                    "els_essay_id": db_row.els_essay_id,
                    "bradley_terry_score": db_row.current_bt_score,
                    "bradley_terry_se": db_row.current_bt_se,
                    "comparison_count": db_row.comparison_count,
                    "is_anchor": bool(db_row.is_anchor),
                    # Provide metadata needed for downstream anchor-grade resolution
                    "text_storage_id": db_row.text_storage_id,
                    "processing_metadata": db_row.processing_metadata,
                },
            )

        logger.info(
            f"Generated rankings for {len(rankings)} essays in CJ Batch {cj_batch_id}.",
            extra={
                "cj_batch_id": str(cj_batch_id),
                "correlation_id": correlation_id,
            },
        )
        return rankings


async def _update_essay_scores_in_database(
    db_session: AsyncSession,
    cj_batch_id: int,  # This is the internal CJ_BatchUpload.id
    scores: dict[str, float],  # Keyed by els_essay_id (string)
    ses: dict[str, float],  # Standard errors keyed by els_essay_id
    counts: dict[str, int],  # Comparison counts keyed by els_essay_id
) -> None:
    """Update essay Bradley-Terry scores, SEs, and counts in the database.

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID
        scores: Dictionary mapping essay IDs to BT scores
        ses: Dictionary mapping essay IDs to standard errors
        counts: Dictionary mapping essay IDs to comparison counts
    """
    if not scores:
        logger.debug(
            f"No scores provided to update for CJ Batch ID: {cj_batch_id}",
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        return

    logger.debug(
        f"Updating BT scores and SEs for {len(scores)} essays in CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    for els_id, score_val in scores.items():
        se_val = ses.get(els_id, 0.0)
        count_val = counts.get(els_id, 0)

        stmt = (
            update(CJ_ProcessedEssay)
            .where(
                CJ_ProcessedEssay.els_essay_id == els_id,
                CJ_ProcessedEssay.cj_batch_id == cj_batch_id,
            )
            .values(
                current_bt_score=score_val,
                current_bt_se=se_val,
                comparison_count=count_val,
            )
        )
        await db_session.execute(stmt)

    logger.info(
        f"Updated scores, SEs, and counts for {len(scores)} essays in CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

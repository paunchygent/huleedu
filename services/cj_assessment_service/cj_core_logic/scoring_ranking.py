"""Scoring and ranking logic for comparative judgment.

Adapted from the prototype's ranking_handler.py to work with the service architecture,
using string-based essay IDs and protocol-based database access.
"""

from __future__ import annotations

from typing import Any, Dict

import choix
import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonResult, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair
from services.cj_assessment_service.models_db import ProcessedEssay as CJ_ProcessedEssay

logger = create_service_logger("cj_assessment_service.scoring_ranking")


async def record_comparisons_and_update_scores(
    all_essays: list[EssayForComparison],  # essay.id is string els_essay_id
    comparison_results: list[ComparisonResult],
    db_session: AsyncSession,
    cj_batch_id: int,
    # settings: Settings # Pass settings if alpha for choix is configurable
) -> dict[str, float]:  # Returns dict of els_essay_id -> score
    """Record comparison results and update Bradley-Terry scores using choix.

    Args:
        all_essays: List of all essays in the comparison batch (with string IDs)
        comparison_results: Results from LLM comparisons
        db_session: Database session for storing results
        cj_batch_id: Internal CJ batch ID

    Returns:
        Dictionary mapping essay IDs (strings) to updated BT scores
    """
    logger.info(
        f"Recording {len(comparison_results)} comparison results for CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    # 1. Store new comparison results
    successful_comparisons_this_round = 0
    for result in comparison_results:
        if result.llm_assessment and result.llm_assessment.winner != "Error":
            winner_db_val = None
            if result.llm_assessment.winner == "Essay A":
                winner_db_val = "essay_a"
            elif result.llm_assessment.winner == "Essay B":
                winner_db_val = "essay_b"

            new_pair = CJ_ComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id=result.task.essay_a.id,  # This is els_essay_id (string)
                essay_b_els_id=result.task.essay_b.id,  # This is els_essay_id (string)
                winner=winner_db_val,
                prompt_text=result.task.prompt,
                prompt_hash=result.prompt_hash or "",  # Ensure not None
                confidence=result.llm_assessment.confidence,
                justification=result.llm_assessment.justification,
                raw_llm_response=result.raw_llm_response_content,
                error_message=result.error_message,
                from_cache=result.from_cache,
            )
            db_session.add(new_pair)
            successful_comparisons_this_round += 1

    if successful_comparisons_this_round > 0:
        await db_session.flush()  # Flush to save new pairs before querying all
    logger.info(
        f"Stored {successful_comparisons_this_round} new comparison pairs for "
        f"CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    # 2. Fetch ALL valid comparisons for this cj_batch_id to compute scores
    stmt_all_comps = select(CJ_ComparisonPair).where(
        CJ_ComparisonPair.cj_batch_id == cj_batch_id,
        CJ_ComparisonPair.winner.isnot(None),  # Ensure there's a winner
        CJ_ComparisonPair.winner != "Error",
    )
    all_db_comparisons_result = await db_session.execute(stmt_all_comps)
    all_valid_db_comparisons = all_db_comparisons_result.scalars().all()

    if len(all_valid_db_comparisons) < 1:  # Or a higher threshold like 3
        logger.warning(
            f"Not enough valid comparisons ({len(all_valid_db_comparisons)}) in DB for "
            f"CJ Batch {cj_batch_id} to compute scores.",
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        return {
            essay.id: essay.current_bt_score or 0.0 for essay in all_essays
        }  # Return current/default scores

    # 3. Prepare data for choix
    # Create a mapping from ELS Essay ID (string) to an integer index (0 to n-1)
    unique_els_essay_ids = sorted(list(set(essay.id for essay in all_essays)))
    n_items = len(unique_els_essay_ids)
    els_id_to_idx_map = {els_id: i for i, els_id in enumerate(unique_els_essay_ids)}

    choix_comparison_data = []
    for comp in all_valid_db_comparisons:
        winner_id_str = comp.essay_a_els_id if comp.winner == "essay_a" else comp.essay_b_els_id
        loser_id_str = comp.essay_b_els_id if comp.winner == "essay_a" else comp.essay_a_els_id

        if winner_id_str in els_id_to_idx_map and loser_id_str in els_id_to_idx_map:
            choix_comparison_data.append(
                (els_id_to_idx_map[winner_id_str], els_id_to_idx_map[loser_id_str])
            )
        else:
            logger.warning(
                f"Comparison pair ({winner_id_str}, {loser_id_str}) contains IDs not in the "
                f"current batch's essay list. Skipping.",
                extra={"cj_batch_id": str(cj_batch_id)},
            )

    if not choix_comparison_data:
        logger.warning(
            f"No valid comparison data mapped for `choix` for CJ Batch {cj_batch_id}.",
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        return {essay.id: essay.current_bt_score or 0.0 for essay in all_essays}

    # 4. Compute Bradley-Terry scores using `choix`
    try:
        # Alpha for regularization, can be made configurable via settings
        alpha = 0.01
        params = choix.ilsr_pairwise(n_items, choix_comparison_data, alpha=alpha)
        # Normalize: mean-center the scores
        params -= np.mean(params)

        # Map integer-indexed scores back to string ELS Essay IDs
        updated_bt_scores: Dict[str, float] = {
            unique_els_essay_ids[i]: float(params[i]) for i in range(n_items)
        }
        logger.info(
            f"Successfully computed BT scores for {len(updated_bt_scores)} essays in "
            f"CJ Batch {cj_batch_id}.",
            extra={"cj_batch_id": str(cj_batch_id)},
        )

        # 5. Update scores in the database
        await _update_essay_scores_in_database(db_session, cj_batch_id, updated_bt_scores)

        return updated_bt_scores

    except Exception as e:
        logger.error(
            f"Error computing/updating Bradley-Terry scores for CJ Batch {cj_batch_id}: {e}",
            exc_info=True,
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        # Return current scores if calculation fails
        return {essay.id: essay.current_bt_score or 0.0 for essay in all_essays}


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
    db_session: AsyncSession,
    cj_batch_id: int,  # This is the internal CJ_BatchUpload.id
) -> list[dict[str, Any]]:
    """Get final essay rankings for the CJ batch, ordered by score.

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID

    Returns:
        List of essay ranking dictionaries sorted by score (highest first)
    """
    logger.info(
        f"Generating final rankings for CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    stmt = (
        select(
            CJ_ProcessedEssay.els_essay_id,
            CJ_ProcessedEssay.current_bt_score,
            # Add CJ_ProcessedEssay.comparison_count if you implement it
        )
        .where(CJ_ProcessedEssay.cj_batch_id == cj_batch_id)
        .order_by(CJ_ProcessedEssay.current_bt_score.desc().nulls_last())
    )
    result = await db_session.execute(stmt)
    essays_with_scores = await result.all()

    rankings = []
    for rank, db_row in enumerate(essays_with_scores, 1):
        rankings.append(
            {
                "rank": rank,
                "els_essay_id": db_row.els_essay_id,
                "score": db_row.current_bt_score,
                # "comparison_count": db_row.comparison_count, # If you add this field
            }
        )

    logger.info(
        f"Generated rankings for {len(rankings)} essays in CJ Batch {cj_batch_id}.",
        extra={"cj_batch_id": str(cj_batch_id)},
    )
    return rankings


async def _update_essay_scores_in_database(
    db_session: AsyncSession,
    cj_batch_id: int,  # This is the internal CJ_BatchUpload.id
    scores: dict[str, float],  # Keyed by els_essay_id (string)
) -> None:
    """Update essay Bradley-Terry scores in the database for a specific CJ Batch.

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID
        scores: Dictionary mapping essay IDs to scores
    """
    if not scores:
        logger.debug(
            f"No scores provided to update for CJ Batch ID: {cj_batch_id}",
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        return

    logger.debug(
        f"Updating BT scores for {len(scores)} essays in CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    for els_id, score_val in scores.items():
        stmt = (
            update(CJ_ProcessedEssay)
            .where(
                CJ_ProcessedEssay.els_essay_id == els_id,
                CJ_ProcessedEssay.cj_batch_id
                == cj_batch_id,  # Ensure we only update essays in this specific CJ job
            )
            .values(current_bt_score=score_val)
        )
        await db_session.execute(stmt)

    logger.info(
        f"DB statements prepared to update scores for {len(scores)} essays in "
        f"CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

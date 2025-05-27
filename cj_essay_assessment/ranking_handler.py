"""Ranking Handler module for the Comparative Judgment system.

This module records LLM comparison outcomes, computes Bradley-Terry scores
using the choix library, updates essay scores in the database, and checks
for score stability to determine when to stop the ranking process.

Key functions:
- record_comparisons_and_update_scores: Records outcomes to DB and updates BT scores
- check_score_stability: Calculates maximum change between current/previous scores
"""

from typing import Any

import choix
import numpy as np
from loguru import logger
from sqlalchemy import select
from sqlalchemy.sql.expression import or_

from src.cj_essay_assessment.db_handler import DatabaseHandler
from src.cj_essay_assessment.models_api import (ComparisonResult,
                                                EssayForComparison)
from src.cj_essay_assessment.models_db import ComparisonPair, ProcessedEssay


async def record_comparisons_and_update_scores(
    db_handler: DatabaseHandler,
    batch_id: int,
    iteration: int,
    results: list[ComparisonResult],
    all_essays: list[EssayForComparison],
) -> dict[int, float]:
    """Records comparison outcomes to database and updates Bradley-Terry scores.

    Args:
        db_handler: Database handler instance
        batch_id: ID of the current batch being processed
        iteration: Current comparison batch iteration
        results: List of ComparisonResult objects from LLM
        all_essays: Complete list of essays in the batch

    Returns:
        Dict mapping essay IDs to their current Bradley-Terry scores

    """
    # Track the recorded comparisons for this round
    recorded_comparisons_count = 0
    errors_count = 0

    async with db_handler.session() as session:
        # 1. Record new comparison outcomes
        for result in results:
            # Skip if assessment is missing or indicates an error
            if not result.llm_assessment or result.llm_assessment.winner == "Error":
                errors_count += 1
                continue

            # Determine winner essay
            winner = None
            if result.llm_assessment.winner == "Essay A":
                winner = "essay_a"
            elif result.llm_assessment.winner == "Essay B":
                winner = "essay_b"

            # Create new ComparisonPair instance
            comparison_pair = ComparisonPair(
                batch_id=batch_id,
                essay_a_id=result.task.essay_a.id,
                essay_b_id=result.task.essay_b.id,
                winner=winner,
                prompt_text=result.task.prompt,
                prompt_hash=result.prompt_hash,
                confidence=(
                    result.llm_assessment.confidence if result.llm_assessment else None
                ),
                justification=(
                    result.llm_assessment.justification if result.llm_assessment else None
                ),
                raw_llm_response=result.raw_llm_response_content,
                error_message=result.error_message,
                from_cache=result.from_cache,
                processing_metadata={"comparison_batch_iteration": iteration},
            )

            session.add(comparison_pair)
            recorded_comparisons_count += 1

        # Commit the comparisons to generate IDs
        await session.flush()

        logger.info(
            f"Recorded {recorded_comparisons_count} new comparisons for "
            f"batch {batch_id} (iteration {iteration}). Errors: {errors_count}",
        )

        # 2. Fetch all comparison pairs for this batch to compute scores
        # Build a query using SQLAlchemy expressions
        query = select(ComparisonPair).where(
            ComparisonPair.batch_id == batch_id,
            or_(ComparisonPair.winner != None),  # noqa: E711
        )
        query_result = await session.execute(query)
        all_comparisons = query_result.scalars().all()

        logger.info(
            f"Retrieved {len(all_comparisons)} total valid comparisons "
            f"for batch {batch_id}",
        )

        # If we don't have enough data yet, return empty scores
        if len(all_comparisons) < 3:  # Minimum needed for meaningful scoring
            logger.warning(
                f"Not enough comparisons ({len(all_comparisons)}) "
                f"to compute Bradley-Terry scores yet",
            )
            return {}

        # 3. Prepare data for choix
        # Build a map of essay IDs to indices for choix
        essay_ids = [essay.id for essay in all_essays]
        id_to_index = {essay_id: idx for idx, essay_id in enumerate(essay_ids)}

        # Convert comparisons to (winner_idx, loser_idx) pairs for choix
        comparisons_for_choix = []
        for comp in all_comparisons:
            # Skip if winner isn't recorded
            if comp.winner is None:
                continue

            # Get winner and loser essay IDs based on the winner field
            winner_id = comp.essay_a_id if comp.winner == "essay_a" else comp.essay_b_id
            loser_id = comp.essay_b_id if comp.winner == "essay_a" else comp.essay_a_id

            winner_idx = id_to_index.get(winner_id)
            loser_idx = id_to_index.get(loser_id)

            # Make sure both essays still exist in the current set
            if winner_idx is not None and loser_idx is not None:
                comparisons_for_choix.append((winner_idx, loser_idx))

        n_items = len(all_essays)

        if not comparisons_for_choix:
            logger.warning("No valid comparison data for choix computation")
            return {}

        logger.info(
            f"Computing Bradley-Terry scores for {n_items} essays "
            f"using {len(comparisons_for_choix)} comparisons",
        )

        # 4. Call choix to compute parameters (scores)
        try:
            # Use regularization (alpha) to ensure connected graphs and stable estimates
            # Higher alpha = more regularization, scores closer to 0
            choix_params = choix.ilsr_pairwise(n_items, comparisons_for_choix, alpha=0.01)

            # 5. Map scores back to essay IDs and normalize
            # Mean-center the scores (shift so mean is 0)
            choix_params = choix_params - np.mean(choix_params)

            # Map scores back to essay IDs
            current_bt_scores = {
                essay_ids[i]: float(score) for i, score in enumerate(choix_params)
            }

            # 6. Update database with new scores
            for essay_id, score in current_bt_scores.items():
                essay_query = select(ProcessedEssay).where(ProcessedEssay.id == essay_id)
                essay_result = await session.execute(essay_query)
                essay = essay_result.scalar_one_or_none()

                if essay:
                    # Update current_bt_score
                    essay.current_bt_score = score

            # Commit the score updates
            await session.commit()

            logger.info(
                f"Updated Bradley-Terry scores for {len(current_bt_scores)} "
                f"essays in batch {batch_id}",
            )
            return current_bt_scores

        except Exception as e:
            logger.error(f"Error computing Bradley-Terry scores: {e}")
            # Commit the comparison records even if scoring fails
            await session.commit()
            return {}


def check_score_stability(
    current_scores: dict[int, float],
    previous_scores: dict[int, float],
) -> float:
    """Calculates the maximum absolute change between current and previous scores.

    Args:
        current_scores: Dictionary mapping essay IDs to current BT scores
        previous_scores: Dictionary mapping essay IDs to previous BT scores

    Returns:
        Maximum absolute change in any essay's score

    """
    if not current_scores or not previous_scores:
        return float("inf")  # No stability if we don't have both score sets

    # Find all essay IDs in either score set
    all_essay_ids = set(current_scores.keys()) | set(previous_scores.keys())

    if not all_essay_ids:
        return 0.0  # No changes if no essays

    # Calculate max absolute change for any essay
    max_abs_change = max(
        abs(current_scores.get(essay_id, 0.0) - previous_scores.get(essay_id, 0.0))
        for essay_id in all_essay_ids
    )

    return max_abs_change


async def get_essay_rankings(
    db_handler: DatabaseHandler,
    batch_id: int,
) -> list[dict[str, Any]]:
    """Retrieves all essays for a batch with their current BT scores and rankings.

    Args:
        db_handler: Database handler instance
        batch_id: ID of the batch to get rankings for

    Returns:
        List of dictionaries with essay details including rank

    """
    async with db_handler.session() as session:
        # Get all essays for this batch that have BT scores
        # Use SQLAlchemy expression for attribute access to avoid mypy errors
        query = (
            select(ProcessedEssay)
            .where(
                ProcessedEssay.batch_id == batch_id,
                or_(ProcessedEssay.current_bt_score != None),  # noqa: E711
            )
            .order_by(ProcessedEssay.current_bt_score.desc())
        )

        result = await session.execute(query)
        essays = result.scalars().all()

        # Create ranking list with essay details
        rankings = []
        for rank, essay in enumerate(essays, 1):
            rankings.append(
                {
                    "id": essay.id,
                    "original_filename": essay.original_filename,
                    "bt_score": essay.current_bt_score,
                    "rank": rank,
                },
            )

        return rankings

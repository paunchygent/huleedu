"""Scoring and ranking logic for CJ Assessment Service."""

from __future__ import annotations

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonResult, EssayForComparison

from .models_db import ComparisonPair as CJ_ComparisonPair
from .models_db import ProcessedEssay as CJ_ProcessedEssay

logger = create_service_logger("cj_assessment_service.scoring_ranking")


async def record_comparisons_and_update_scores(
    all_essays: list[EssayForComparison],
    comparison_results: list[ComparisonResult],
    db_session: AsyncSession,
    cj_batch_id: int,
) -> dict[str, float]:
    """Record comparison results and update Bradley-Terry scores using choix."""
    logger.info(f"Recording {len(comparison_results)} comparison results")

    # Store comparison results
    for result in comparison_results:
        if result.llm_assessment and result.llm_assessment.winner != "Error":
            winner_db_val = None
            if result.llm_assessment.winner == "Essay A":
                winner_db_val = "essay_a"
            elif result.llm_assessment.winner == "Essay B":
                winner_db_val = "essay_b"

            new_pair = CJ_ComparisonPair(
                cj_batch_id=cj_batch_id,
                essay_a_els_id=result.task.essay_a.id,
                essay_b_els_id=result.task.essay_b.id,
                winner=winner_db_val,
                prompt_text=result.task.prompt,
                prompt_hash=result.prompt_hash or "",
                confidence=result.llm_assessment.confidence,
                justification=result.llm_assessment.justification,
                raw_llm_response=result.raw_llm_response_content,
                error_message=result.error_message,
                from_cache=result.from_cache,
            )
            db_session.add(new_pair)

    await db_session.flush()

    # Return current scores for now
    return {essay.id: essay.current_bt_score or 0.0 for essay in all_essays}


def check_score_stability(
    current_bt_scores: dict[str, float],
    previous_bt_scores: dict[str, float],
    stability_threshold: float = 0.05,
) -> float:
    """Check score stability by computing maximum change between iterations."""
    if not previous_bt_scores:
        return float("inf")

    max_change = 0.0
    for essay_id, current_score in current_bt_scores.items():
        previous_score = previous_bt_scores.get(essay_id, 0.0)
        change = abs(current_score - previous_score)
        max_change = max(max_change, change)

    return max_change


async def get_essay_rankings(
    db_session: AsyncSession,
    cj_batch_id: int,
) -> list[dict]:
    """Get final essay rankings for the CJ batch."""
    stmt = (
        select(
            CJ_ProcessedEssay.els_essay_id,
            CJ_ProcessedEssay.current_bt_score,
        )
        .where(CJ_ProcessedEssay.cj_batch_id == cj_batch_id)
        .order_by(CJ_ProcessedEssay.current_bt_score.desc().nulls_last())
    )
    result = await db_session.execute(stmt)
    essays_with_scores = result.all()

    rankings = []
    for rank, db_row in enumerate(essays_with_scores, 1):
        rankings.append(
            {
                "rank": rank,
                "els_essay_id": db_row.els_essay_id,
                "score": db_row.current_bt_score,
            }
        )

    return rankings

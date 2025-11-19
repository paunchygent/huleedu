"""Pair generation logic for comparative judgment.

Adapted from the prototype's pair_generator.py to work with the service architecture,
using string-based essay IDs and protocol-based database access.
"""

from __future__ import annotations

from random import Random
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair

_LEGACY_PROMPT_PATTERNS = (
    "you are an impartial comparative judgement assessor",
    "comparison_result",
    "respond with json",
    "judge instructions",
)

logger = create_service_logger("cj_assessment_service.pair_generation")


async def generate_comparison_tasks(
    essays_for_comparison: list[EssayForComparison],
    db_session: AsyncSession,
    cj_batch_id: int,
    existing_pairs_threshold: int,
    max_pairwise_comparisons: int | None = None,
    correlation_id: UUID | None = None,
    randomization_seed: int | None = None,
) -> list[ComparisonTask]:
    """Generate comparison tasks for essays, avoiding duplicate comparisons.

    Args:
        essays_for_comparison: List of essays to compare (with string IDs)
        db_session: Database session for checking existing comparisons
        cj_batch_id: Internal CJ batch ID for this comparison batch
        existing_pairs_threshold: Maximum existing pairs before skipping generation

    Returns:
        List of comparison tasks ready for LLM processing
    """
    if len(essays_for_comparison) < 2:
        logger.warning(f"Need at least 2 essays for comparison, got {len(essays_for_comparison)}")
        return []

    logger.info(
        f"Generating comparison tasks for {len(essays_for_comparison)} essays",
        extra={
            "correlation_id": correlation_id,
            "cj_batch_id": cj_batch_id,
            "essay_count": len(essays_for_comparison),
        },
    )

    # Fetch assessment context (instructions and student prompt) from batch metadata
    assessment_context = await _fetch_assessment_context(db_session, cj_batch_id)

    # Get existing comparison pairs to avoid duplicates
    existing_comparison_ids = await _fetch_existing_comparison_ids(db_session, cj_batch_id)

    existing_count = len(existing_comparison_ids)
    logger.debug(f"Found {existing_count} existing comparison pairs")

    # Enforce optional global cap on total comparison pairs for this batch
    if max_pairwise_comparisons is not None and existing_count >= max_pairwise_comparisons:
        logger.warning(
            "Global comparison cap reached; no new pairs will be generated",
            extra={
                "cj_batch_id": cj_batch_id,
                "existing_pairs": existing_count,
                "max_pairwise_comparisons": max_pairwise_comparisons,
                "correlation_id": str(correlation_id) if correlation_id else None,
            },
        )
        return []

    # Respect remaining budget under global cap when deciding how many new pairs
    remaining_budget = (
        max_pairwise_comparisons - existing_count
        if max_pairwise_comparisons is not None
        else existing_pairs_threshold
    )
    effective_threshold = min(existing_pairs_threshold, remaining_budget)

    comparison_tasks = []
    new_pairs_count = 0
    randomizer = _build_pair_randomizer(randomization_seed)

    # Generate all possible pairs
    for i in range(len(essays_for_comparison)):
        for j in range(i + 1, len(essays_for_comparison)):
            essay_a = essays_for_comparison[i]
            essay_b = essays_for_comparison[j]

            # Create normalized pair ID (sorted to handle bidirectional pairs)
            current_pair_ids = tuple(sorted((essay_a.id, essay_b.id)))

            # Skip if this pair already exists
            if current_pair_ids in existing_comparison_ids:
                logger.debug(f"Skipping existing pair: {essay_a.id} vs {essay_b.id}")
                continue

            # Stop if we've generated too many new pairs in this round
            if new_pairs_count >= effective_threshold:
                logger.info(
                    f"Reached new pairs threshold ({effective_threshold}), "
                    f"stopping pair generation",
                )
                break

            if _should_swap_positions(randomizer):
                essay_a, essay_b = essay_b, essay_a

            # Create comparison task with assessment context
            prompt = _build_comparison_prompt(
                essay_a,
                essay_b,
                assessment_instructions=assessment_context.get("assessment_instructions"),
                student_prompt_text=assessment_context.get("student_prompt_text"),
                judge_rubric_text=assessment_context.get("judge_rubric_text"),
            )
            task = ComparisonTask(essay_a=essay_a, essay_b=essay_b, prompt=prompt)

            comparison_tasks.append(task)
            new_pairs_count += 1

        # Break outer loop if threshold reached
        if new_pairs_count >= effective_threshold:
            break

    logger.info(
        f"Generated {len(comparison_tasks)} new comparison tasks",
        extra={
            "correlation_id": correlation_id,
            "cj_batch_id": cj_batch_id,
            "task_count": len(comparison_tasks),
        },
    )
    return comparison_tasks


def _build_pair_randomizer(randomization_seed: int | None) -> Random:
    """Return a random number generator for pair randomization."""

    return Random(randomization_seed)


def _should_swap_positions(randomizer: Random) -> bool:
    """Return True when essay positions should be swapped."""

    return randomizer.random() < 0.5


async def _fetch_existing_comparison_ids(
    db_session: AsyncSession,
    cj_batch_id: int,
) -> set[tuple[str, str]]:
    """Fetch existing comparison pair ELS essay IDs from the database for a given CJ batch.

    Returns a set of sorted tuples of (essay_a_els_id, essay_b_els_id) to ensure
    (id1, id2) is treated the same as (id2, id1).

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID

    Returns:
        Set of normalized (essay_a_els_id, essay_b_els_id) tuples for existing comparisons
    """
    logger.debug(
        f"Fetching existing comparison pairs for CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )

    stmt = select(CJ_ComparisonPair.essay_a_els_id, CJ_ComparisonPair.essay_b_els_id).where(
        CJ_ComparisonPair.cj_batch_id == cj_batch_id,
    )

    result = await db_session.execute(stmt)
    existing_pairs_db = result.all()  # Fetches list of (str, str) tuples

    # Store as sorted tuples to handle (a,b) and (b,a) as the same pair
    normalized_pairs: set[tuple[str, str]] = set()
    for id_a, id_b in existing_pairs_db:
        normalized_pairs.add(tuple(sorted((id_a, id_b))))

    logger.debug(
        f"Found {len(normalized_pairs)} existing normalized comparison pairs for "
        f"CJ Batch ID: {cj_batch_id}",
        extra={"cj_batch_id": str(cj_batch_id)},
    )
    return normalized_pairs


async def _fetch_assessment_context(
    db_session: AsyncSession,
    cj_batch_id: int,
) -> dict[str, str | None]:
    """Fetch assessment context from batch and assignment records.

    Retrieves assessment instructions and student prompt text to include in LLM prompts.

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID

    Returns:
        Dictionary with keys 'assessment_instructions' and 'student_prompt_text'
    """
    from services.cj_assessment_service.models_db import (
        AssessmentInstruction,
        CJBatchUpload,
    )

    # Fetch batch record with processing metadata
    batch_stmt = select(CJBatchUpload).where(CJBatchUpload.id == cj_batch_id)
    batch_result = await db_session.execute(batch_stmt)
    batch = batch_result.scalar_one_or_none()

    if not batch:
        logger.warning(
            f"No batch found for CJ batch ID {cj_batch_id}",
            extra={"cj_batch_id": str(cj_batch_id)},
        )
        return {"assessment_instructions": None, "student_prompt_text": None}

    # Extract context from processing metadata
    metadata = batch.processing_metadata or {}
    student_prompt_text = metadata.get("student_prompt_text")
    judge_rubric_text = metadata.get("judge_rubric_text")
    assignment_id = metadata.get("assignment_id") or batch.assignment_id

    # Fetch assessment instructions if assignment_id is available
    assessment_instructions = None
    if assignment_id:
        instruction_stmt = select(AssessmentInstruction).where(
            AssessmentInstruction.assignment_id == assignment_id
        )
        instruction_result = await db_session.execute(instruction_stmt)
        instruction = instruction_result.scalar_one_or_none()

        if instruction:
            assessment_instructions = instruction.instructions_text
        else:
            logger.warning(
                "No assessment instruction found for assignment",
                extra={"cj_batch_id": str(cj_batch_id), "assignment_id": assignment_id},
            )

    logger.debug(
        f"Fetched assessment context for batch {cj_batch_id}",
        extra={
            "cj_batch_id": str(cj_batch_id),
            "has_instructions": assessment_instructions is not None,
            "has_student_prompt": student_prompt_text is not None,
            "has_judge_rubric": judge_rubric_text is not None,
        },
    )

    # Detect legacy data where student prompt actually contains judge rubric text
    legacy_prompt_reason = _detect_legacy_prompt(student_prompt_text)
    if legacy_prompt_reason:
        logger.warning(
            "Detected legacy student prompt that matches judge rubric heuristics",
            extra={
                "cj_batch_id": str(cj_batch_id),
                "legacy_reason": legacy_prompt_reason,
            },
        )
        if student_prompt_text and not judge_rubric_text:
            judge_rubric_text = student_prompt_text
        student_prompt_text = None

    # Warn if no context is available
    if not assessment_instructions and not student_prompt_text and not judge_rubric_text:
        logger.warning(
            "No assessment context available for prompt building",
            extra={
                "cj_batch_id": str(cj_batch_id),
            },
        )

    return {
        "assessment_instructions": assessment_instructions,
        "student_prompt_text": student_prompt_text,
        "judge_rubric_text": judge_rubric_text,
    }


def _detect_legacy_prompt(student_prompt_text: str | None) -> str | None:
    """Return reason string if prompt looks like mis-labelled judge rubric text."""

    if not student_prompt_text:
        return None

    lowered = student_prompt_text.lower()
    for pattern in _LEGACY_PROMPT_PATTERNS:
        if pattern in lowered:
            return pattern

    return None


def _build_comparison_prompt(
    essay_a: EssayForComparison,
    essay_b: EssayForComparison,
    assessment_instructions: str | None = None,
    student_prompt_text: str | None = None,
    judge_rubric_text: str | None = None,
) -> str:
    """Build the comparison prompt for two essays with assessment context.

    Args:
        essay_a: First essay for comparison
        essay_b: Second essay for comparison
        assessment_instructions: Assessment criteria supplied by teacher/admin
        student_prompt_text: Original student prompt showing what was asked
        judge_rubric_text: Detailed judge rubric to guide evaluation

    Returns:
        Formatted prompt string for LLM comparison with full context
    """
    prompt_parts = []

    # Add student prompt context if available
    if student_prompt_text:
        prompt_parts.append(f"**Student Assignment:**\n{student_prompt_text}")

    # Add assessment instructions/rubric if available
    if assessment_instructions:
        prompt_parts.append(f"**Assessment Criteria:**\n{assessment_instructions}")

    if judge_rubric_text:
        prompt_parts.append(f"**Judge Instructions:**\n{judge_rubric_text}")

    # Add essays for comparison
    prompt_parts.append(f"**Essay A (ID: {essay_a.id}):**\n{essay_a.text_content}")
    prompt_parts.append(f"**Essay B (ID: {essay_b.id}):**\n{essay_b.text_content}")

    # Add response instructions
    prompt_parts.append(
        "Using the Student Assignment, Assessment Criteria, and Judge Instructions above, "
        "determine which essay better fulfills the requirements. Respond with JSON indicating "
        "the `winner` ('Essay A' or 'Essay B'), a brief `justification`, and a `confidence` "
        "rating from 1-5 (5 = very confident). Provide a decisive judgment."
    )

    return "\n\n".join(prompt_parts)

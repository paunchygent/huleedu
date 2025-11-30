"""Pair generation logic for comparative judgment.

Uses DI-injected matching strategies to generate optimal comparison pairs
where each essay appears in exactly one comparison per wave.
"""

from __future__ import annotations

from enum import Enum
from random import Random
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.prompt_templates import PromptTemplateBuilder
from services.cj_assessment_service.models_api import ComparisonTask, EssayForComparison
from services.cj_assessment_service.models_db import ComparisonPair as CJ_ComparisonPair
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    PairMatchingStrategyProtocol,
    SessionProviderProtocol,
)

_LEGACY_PROMPT_PATTERNS = (
    "you are an impartial comparative judgement assessor",
    "comparison_result",
    "respond with json",
    "judge instructions",
)

logger = create_service_logger("cj_assessment_service.pair_generation")


class PairGenerationMode(str, Enum):
    """Pair generation modes for CJ comparisons.

    COVERAGE:
        Generate new comparison pairs to improve graph coverage (Phase-1).

    RESAMPLING:
        Resample existing pairs to improve fairness and stability (Phase-2).
    """

    COVERAGE = "coverage"
    RESAMPLING = "resampling"


async def generate_comparison_tasks(
    essays_for_comparison: list[EssayForComparison],
    session_provider: SessionProviderProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    matching_strategy: PairMatchingStrategyProtocol,
    cj_batch_id: int,
    max_pairwise_comparisons: int | None = None,
    correlation_id: UUID | None = None,
    randomization_seed: int | None = None,
    mode: PairGenerationMode = PairGenerationMode.COVERAGE,
) -> list[ComparisonTask]:
    """Generate comparison tasks using injected matching strategy.

    Each essay appears in exactly one comparison per wave. Uses the
    matching strategy to compute optimal pairs based on information gain.

    Args:
        essays_for_comparison: List of essays to compare (with string IDs)
        session_provider: Session provider for database access
        comparison_repository: Repository for comparison pair operations
        instruction_repository: Repository for assessment instruction operations
        matching_strategy: DI-injected strategy for computing optimal pairs
        cj_batch_id: Internal CJ batch ID for this comparison batch
        max_pairwise_comparisons: Optional global cap on total comparison pairs
        correlation_id: Correlation ID for observability
        randomization_seed: Seed for randomizing essay positions in pairs

    Returns:
        List of comparison tasks ready for LLM processing
    """
    if len(essays_for_comparison) < 2:
        logger.warning(
            f"Need at least 2 essays for comparison, got {len(essays_for_comparison)}",
            extra={"cj_batch_id": cj_batch_id, "mode": mode.name},
        )
        return []

    logger.info(
        f"Generating comparison tasks for {len(essays_for_comparison)} essays",
        extra={
            "correlation_id": correlation_id,
            "cj_batch_id": cj_batch_id,
            "essay_count": len(essays_for_comparison),
            "mode": mode.name,
        },
    )

    async with session_provider.session() as session:
        # Fetch assessment context (instructions and student prompt) from batch metadata
        assessment_context = await _fetch_assessment_context(session, cj_batch_id)

        # Get existing comparison pairs to avoid duplicates
        existing_pairs = await _fetch_existing_comparison_ids(session, cj_batch_id)

        existing_pairs_count = len(existing_pairs)
        logger.debug(
            f"Found {existing_pairs_count} existing comparison pairs",
            extra={"cj_batch_id": cj_batch_id, "mode": mode.name},
        )

        # Fetch comparison counts for each essay (for fairness weighting)
        comparison_counts = await _fetch_comparison_counts(session, cj_batch_id)

        # Derive a conservative view of budget consumption:
        # - existing_pairs_count tracks unique unordered pairs
        # - comparison_counts encodes total comparisons performed
        total_comparisons_performed = sum(comparison_counts.values()) // 2
        budget_consumed = max(existing_pairs_count, total_comparisons_performed)

        # Enforce optional global cap on total comparison pairs for this batch.
        remaining_budget: int | None = None
        if max_pairwise_comparisons is not None:
            remaining_budget = max_pairwise_comparisons - budget_consumed
            if remaining_budget <= 0:
                logger.warning(
                    "Global comparison cap reached; no new pairs will be generated",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "existing_pairs": existing_pairs_count,
                        "total_comparisons_performed": total_comparisons_performed,
                        "max_pairwise_comparisons": max_pairwise_comparisons,
                        "correlation_id": str(correlation_id) if correlation_id else None,
                    },
                )
                return []

        matched_pairs: list[tuple[EssayForComparison, EssayForComparison]]

        if mode is PairGenerationMode.COVERAGE:
            # Phase-1 semantics: generate new pairs to improve coverage.

            # Handle odd essay count via strategy (excludes essay with most comparisons)
            essays_for_matching, excluded_essay = matching_strategy.handle_odd_count(
                essays_for_comparison, comparison_counts
            )

            if excluded_essay:
                logger.info(
                    "Excluded essay from wave due to odd count",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "excluded_essay_id": excluded_essay.id,
                        "correlation_id": str(correlation_id) if correlation_id else None,
                    },
                )

            # Compute optimal pairs via strategy (each essay appears exactly once)
            matched_pairs = matching_strategy.compute_wave_pairs(
                essays=essays_for_matching,
                existing_pairs=existing_pairs,
                comparison_counts=comparison_counts,
                randomization_seed=randomization_seed,
            )

            # Respect global cap using remaining_budget derived above.
            if remaining_budget is not None and len(matched_pairs) > remaining_budget:
                matched_pairs = matched_pairs[:remaining_budget]
                logger.info(
                    "Truncated pairs to respect global cap",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "remaining_budget": remaining_budget,
                        "pairs_truncated_to": len(matched_pairs),
                    },
                )

        elif mode is PairGenerationMode.RESAMPLING:
            # Phase-2 semantics: resample existing pairs, prioritising essays with
            # lower comparison counts to avoid starving under-sampled essays.
            if not existing_pairs:
                logger.info(
                    "No existing pairs available for resampling",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "correlation_id": str(correlation_id) if correlation_id else None,
                    },
                )
                return []

            # Build lookup for essays by ID to reconstruct EssayForComparison objects.
            essays_by_id: dict[str, EssayForComparison] = {
                essay.id: essay for essay in essays_for_comparison
            }

            # Score candidate pairs: lower total comparison count -> higher priority.
            scored_candidates: list[
                tuple[int, str, str, EssayForComparison, EssayForComparison]
            ] = []
            for id_a, id_b in existing_pairs:
                essay_a = essays_by_id.get(id_a)
                essay_b = essays_by_id.get(id_b)
                if not essay_a or not essay_b:
                    # Skip pairs that refer to essays not present in the current wave.
                    continue
                total_count = comparison_counts.get(id_a, 0) + comparison_counts.get(id_b, 0)
                # Sort by (total_count, id_a, id_b) for deterministic ordering.
                scored_candidates.append((total_count, id_a, id_b, essay_a, essay_b))

            if not scored_candidates:
                logger.info(
                    "No candidate resampling pairs after filtering",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "correlation_id": str(correlation_id) if correlation_id else None,
                    },
                )
                return []

            scored_candidates.sort(key=lambda item: (item[0], item[1], item[2]))

            # Determine how many pairs we can schedule in this resampling wave.
            if remaining_budget is None:
                max_pairs_this_wave = len(scored_candidates)
            else:
                max_pairs_this_wave = max(0, min(len(scored_candidates), remaining_budget))

            if max_pairs_this_wave == 0:
                logger.info(
                    "Resampling wave skipped due to exhausted remaining budget",
                    extra={
                        "cj_batch_id": cj_batch_id,
                        "mode": mode.name,
                        "remaining_budget": remaining_budget,
                        "correlation_id": str(correlation_id) if correlation_id else None,
                    },
                )
                return []

            selected = scored_candidates[:max_pairs_this_wave]
            matched_pairs = [(essay_a, essay_b) for _, _, _, essay_a, essay_b in selected]

            logger.info(
                "Selected resampling pairs for small-net Phase-2 wave",
                extra={
                    "cj_batch_id": cj_batch_id,
                    "mode": mode.name,
                    "selected_pairs": len(matched_pairs),
                    "remaining_budget": remaining_budget,
                    "total_comparisons_performed": total_comparisons_performed,
                },
            )

        else:  # pragma: no cover - defensive guard for future enum values
            logger.error(
                "Unsupported PairGenerationMode encountered",
                extra={
                    "cj_batch_id": cj_batch_id,
                    "mode": str(mode),
                    "correlation_id": str(correlation_id) if correlation_id else None,
                },
            )
            return []

        # Build ComparisonTasks from matched pairs
        comparison_tasks: list[ComparisonTask] = []
        randomizer = _build_pair_randomizer(randomization_seed)

        for essay_a, essay_b in matched_pairs:
            # Randomize position to avoid systematic bias
            if _should_swap_positions(randomizer):
                essay_a, essay_b = essay_b, essay_a

            prompt_blocks = PromptTemplateBuilder.assemble_full_prompt(
                assessment_context=assessment_context,
                essay_a=essay_a,
                essay_b=essay_b,
            )
            prompt_text = PromptTemplateBuilder.render_prompt_text(prompt_blocks)

            task = ComparisonTask(
                essay_a=essay_a,
                essay_b=essay_b,
                prompt=prompt_text,
                prompt_blocks=prompt_blocks,
            )
            comparison_tasks.append(task)

        # For observability, keep using compute_wave_size but make the
        # input explicit for RESAMPLING waves where odd-count handling
        # is not applied.
        if mode is PairGenerationMode.COVERAGE:
            wave_size_input_count = len(essays_for_matching)
        else:
            wave_size_input_count = len(essays_for_comparison)

        logger.info(
            f"Generated {len(comparison_tasks)} new comparison tasks via optimal matching",
            extra={
                "correlation_id": correlation_id,
                "cj_batch_id": cj_batch_id,
                "task_count": len(comparison_tasks),
                "wave_size": matching_strategy.compute_wave_size(wave_size_input_count),
                "mode": mode.name,
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


async def _fetch_comparison_counts(
    db_session: AsyncSession,
    cj_batch_id: int,
) -> dict[str, int]:
    """Fetch comparison counts for each essay in the batch.

    Counts how many times each essay appears in either essay_a or essay_b position.

    Args:
        db_session: Database session
        cj_batch_id: Internal CJ batch ID

    Returns:
        Dict mapping essay_id -> comparison count
    """
    # Count appearances in essay_a position
    stmt_a = (
        select(CJ_ComparisonPair.essay_a_els_id, func.count())
        .where(CJ_ComparisonPair.cj_batch_id == cj_batch_id)
        .group_by(CJ_ComparisonPair.essay_a_els_id)
    )
    result_a = await db_session.execute(stmt_a)
    counts_a: dict[str, int] = {row[0]: row[1] for row in result_a.all()}

    # Count appearances in essay_b position
    stmt_b = (
        select(CJ_ComparisonPair.essay_b_els_id, func.count())
        .where(CJ_ComparisonPair.cj_batch_id == cj_batch_id)
        .group_by(CJ_ComparisonPair.essay_b_els_id)
    )
    result_b = await db_session.execute(stmt_b)
    counts_b: dict[str, int] = {row[0]: row[1] for row in result_b.all()}

    # Merge counts
    comparison_counts: dict[str, int] = {}
    all_ids = set(counts_a.keys()) | set(counts_b.keys())
    for essay_id in all_ids:
        comparison_counts[essay_id] = counts_a.get(essay_id, 0) + counts_b.get(essay_id, 0)

    logger.debug(
        f"Fetched comparison counts for {len(comparison_counts)} essays",
        extra={"cj_batch_id": str(cj_batch_id)},
    )
    return comparison_counts


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

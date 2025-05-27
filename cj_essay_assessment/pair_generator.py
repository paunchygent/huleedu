import random
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models_api import ComparisonTask, EssayForComparison
from .models_db import ComparisonPair


async def _fetch_existing_comparison_ids(
    db_session: AsyncSession,
    batch_id: int,
) -> set[tuple[int, int]]:
    """Fetches a set of essay ID pairs (tuples sorted by ID) that have already been compared
    for a given batch. This helps in avoiding re-comparison of the same pair.
    """
    stmt = select(ComparisonPair.essay_a_id, ComparisonPair.essay_b_id).where(
        ComparisonPair.batch_id == batch_id,
    )
    result = await db_session.execute(stmt)
    # Ensure IDs are not None and store them as sorted tuples to make (1,2)
    # and (2,1) equivalent
    existing_pairs: set[tuple[int, int]] = {
        tuple(sorted((e1_id, e2_id)))  # type: ignore
        for e1_id, e2_id in result.fetchall()
        if e1_id is not None and e2_id is not None
    }
    return existing_pairs


async def generate_comparison_tasks(
    essays_for_comparison: list[EssayForComparison],
    db_session: AsyncSession,
    batch_id: int,
    settings: Settings,
) -> list[ComparisonTask]:
    """Generates a list of comparison tasks for a round of pairwise comparisons.

    Args:
        essays_for_comparison: A list of EssayForComparison objects to generate
            pairs from.
        db_session: An active SQLAlchemy AsyncSession.
        batch_id: The ID of the current batch being processed.
        settings: The application settings object.

    Returns:
        A list of ComparisonTask objects, ready for LLM assessment.
        Returns an empty list if fewer than two essays are provided or
        no new pairs can be formed.

    """
    if not essays_for_comparison or len(essays_for_comparison) < 2:
        return []

    # 1. Generate all unique pairs of essays using their IDs for internal tracking.
    # We use EssayForComparison objects directly in combinations to keep data associated.
    all_potential_essay_obj_pairs: list[tuple[EssayForComparison, EssayForComparison]] = (
        list(combinations(essays_for_comparison, 2))
    )

    # 2. Filter out pairs that have already been compared.
    existing_compared_id_pairs = await _fetch_existing_comparison_ids(
        db_session,
        batch_id,
    )

    new_essay_obj_pairs: list[tuple[EssayForComparison, EssayForComparison]] = []
    for essay_a_obj, essay_b_obj in all_potential_essay_obj_pairs:
        # Create a sorted tuple of IDs for checking against the existing set
        current_pair_ids = tuple(sorted((essay_a_obj.id, essay_b_obj.id)))
        if current_pair_ids not in existing_compared_id_pairs:
            new_essay_obj_pairs.append((essay_a_obj, essay_b_obj))

    if not new_essay_obj_pairs:
        return []

    # 3. Shuffle the remaining new pairs.
    random.shuffle(new_essay_obj_pairs)

    # 4. Limit the number of tasks for this iteration.
    pairs_for_this_round = new_essay_obj_pairs[
        : settings.comparisons_per_stability_check_iteration
    ]

    # 5. Construct the assessment prompt for each selected pair
    # and create ComparisonTask objects.
    comparison_tasks: list[ComparisonTask] = []
    for essay_a, essay_b in pairs_for_this_round:
        prompt = settings.assessment_prompt_template.format(
            essay_a_id=essay_a.id,
            essay_a_text=essay_a.text_content,
            essay_b_id=essay_b.id,
            essay_b_text=essay_b.text_content,
        )
        task = ComparisonTask(
            essay_a=essay_a,  # essay_a and essay_b are EssayForComparison instances
            essay_b=essay_b,
            prompt=prompt,
        )
        comparison_tasks.append(task)

    # 6. Return a list of ComparisonTask objects.
    return comparison_tasks

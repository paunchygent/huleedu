"""Tests for CJ pair generation randomization behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)


@pytest.fixture(autouse=True)
def stub_db_helpers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub out DB helpers so tests focus on randomization logic."""

    async def fake_fetch_context(*_: object, **__: object) -> dict[str, str | None]:
        return {
            "assessment_instructions": "Assess clarity",
            "student_prompt_text": "Describe your hometown",
            "judge_rubric_text": None,
        }

    async def fake_fetch_existing(*_: object, **__: object) -> set[tuple[str, str]]:
        return set()

    monkeypatch.setattr(pair_generation, "_fetch_assessment_context", fake_fetch_context)
    monkeypatch.setattr(pair_generation, "_fetch_existing_comparison_ids", fake_fetch_existing)


@pytest.fixture
def sample_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def sample_essays() -> list[EssayForComparison]:
    return [
        EssayForComparison(id="anchor-1", text_content="Anchor essay", current_bt_score=0.0),
        EssayForComparison(id="student-1", text_content="Student one", current_bt_score=0.0),
        EssayForComparison(id="student-2", text_content="Student two", current_bt_score=0.0),
    ]


@pytest.mark.asyncio
async def test_seed_produces_deterministic_pair_order(
    sample_session: AsyncMock, sample_essays: list[EssayForComparison]
) -> None:
    """Generating with the same seed should return identical ordering."""

    tasks_first = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        cj_batch_id=99,
        existing_pairs_threshold=10,
        correlation_id=None,
        randomization_seed=42,
    )

    tasks_second = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        cj_batch_id=99,
        existing_pairs_threshold=10,
        correlation_id=None,
        randomization_seed=42,
    )

    first_order = [(task.essay_a.id, task.essay_b.id) for task in tasks_first]
    second_order = [(task.essay_a.id, task.essay_b.id) for task in tasks_second]

    assert len(tasks_first) == 3  # nC2 pairs for three essays
    assert first_order == second_order


@pytest.mark.asyncio
async def test_randomization_swaps_positions_when_triggered(
    sample_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced swap path should invert the first generated pair."""

    call_counter = {"calls": 0}

    def fake_should_swap(randomizer: object) -> bool:
        call_counter["calls"] += 1
        return call_counter["calls"] == 1  # swap the first pair only

    monkeypatch.setattr(pair_generation, "_should_swap_positions", fake_should_swap)

    tasks = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        cj_batch_id=1,
        existing_pairs_threshold=5,
        correlation_id=None,
        randomization_seed=7,
    )

    assert tasks, "Expected at least one comparison task"
    first_pair = tasks[0]
    # Original ordering is anchor vs student-1; swapping puts student-1 first
    assert first_pair.essay_a.id == "student-1"
    assert first_pair.essay_b.id == "anchor-1"


@pytest.mark.asyncio
async def test_anchor_positions_are_balanced(
    sample_session: AsyncMock, sample_essays: list[EssayForComparison]
) -> None:
    """Across diverse seeds, anchors should occupy essay_a about half the time."""

    anchor_a_total = 0
    anchor_pair_total = 0

    for seed in range(200):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=sample_essays,
            session_provider=AsyncMock(spec=SessionProviderProtocol),
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            cj_batch_id=2,
            existing_pairs_threshold=10,
            randomization_seed=seed,
        )
        for task in tasks:
            participants = (task.essay_a.id, task.essay_b.id)
            if any(p.startswith("anchor-") for p in participants):
                anchor_pair_total += 1
                if task.essay_a.id.startswith("anchor-"):
                    anchor_a_total += 1

    assert anchor_pair_total > 0
    ratio = anchor_a_total / anchor_pair_total
    assert 0.35 <= ratio <= 0.65


@pytest.mark.asyncio
async def test_anchor_position_chi_squared(
    sample_session: AsyncMock, sample_essays: list[EssayForComparison]
) -> None:
    """Formal statistical test for randomization fairness using Chi-Squared test.

    Null Hypothesis (H0): The probability of an anchor being in position A is 0.5.
    We fail to reject H0 if p-value > 0.05.
    """
    from scipy.stats import chisquare

    anchor_a_count = 0
    anchor_b_count = 0

    # Generate enough samples for statistical significance
    # 200 seeds * ~2 anchor pairs per batch = ~400 observations
    for seed in range(200):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=sample_essays,
            session_provider=AsyncMock(spec=SessionProviderProtocol),
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            cj_batch_id=seed,
            existing_pairs_threshold=10,
            randomization_seed=seed,
        )

        for task in tasks:
            is_anchor_a = task.essay_a.id.startswith("anchor-")
            is_anchor_b = task.essay_b.id.startswith("anchor-")

            # Only count pairs where exactly one is an anchor (mixed pair)
            if is_anchor_a != is_anchor_b:
                if is_anchor_a:
                    anchor_a_count += 1
                else:
                    anchor_b_count += 1

    total_observations = anchor_a_count + anchor_b_count
    assert total_observations > 100, "Insufficient sample size for statistical test"

    observed = [anchor_a_count, anchor_b_count]
    expected = [total_observations / 2, total_observations / 2]

    # Perform Chi-Squared test
    chi2_stat, p_value = chisquare(f_obs=observed, f_exp=expected)

    # Check if p-value > 0.05 (significance level)
    # If p < 0.05, we reject H0 and conclude the distribution is biased
    # We want to FAIL to reject H0 (i.e., it IS random)
    assert p_value > 0.05, (
        f"Randomization failed Chi-Squared test: p={p_value:.4f} < 0.05. "
        f"Observed: A={anchor_a_count}, B={anchor_b_count}"
    )

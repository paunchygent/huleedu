"""Tests for CJ pair generation randomization behavior."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic import pair_generation
from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    PairOrientationStrategyProtocol,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    SessionProviderProtocol,
)
from services.cj_assessment_service.tests.helpers.matching_strategies import (
    make_real_matching_strategy_mock,
)


class RandomOrientationStrategy(PairOrientationStrategyProtocol):
    """Test-only orientation strategy that randomizes A/B positions."""

    def choose_coverage_orientation(
        self,
        pair: tuple[EssayForComparison, EssayForComparison],
        per_essay_position_counts: dict[str, tuple[int, int]],
        rng: object,
    ) -> tuple[EssayForComparison, EssayForComparison]:
        essay_a, essay_b = pair
        random = getattr(rng, "random")
        if callable(random) and random() < 0.5:
            return essay_a, essay_b
        return essay_b, essay_a

    def choose_resampling_orientation(
        self,
        pair: tuple[EssayForComparison, EssayForComparison],
        per_pair_orientation_counts: dict[tuple[str, str], tuple[int, int]],
        per_essay_position_counts: dict[str, tuple[int, int]],
        rng: object,
    ) -> tuple[EssayForComparison, EssayForComparison]:
        return self.choose_coverage_orientation(pair, per_essay_position_counts, rng)


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
    monkeypatch.setattr(
        pair_generation,
        "_fetch_comparison_counts",
        AsyncMock(return_value={}),
    )

    async def fake_per_essay_counts(*_: object, **__: object) -> dict[str, tuple[int, int]]:
        return {}

    async def fake_per_pair_counts(
        *_: object, **__: object
    ) -> dict[tuple[str, str], tuple[int, int]]:
        return {}

    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_essay_position_counts",
        fake_per_essay_counts,
    )
    monkeypatch.setattr(
        pair_generation,
        "_fetch_per_pair_orientation_counts",
        fake_per_pair_counts,
    )


@pytest.fixture
def sample_session() -> AsyncMock:
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_matching_strategy() -> MagicMock:
    """Use real optimal graph matching strategy for tests."""
    return make_real_matching_strategy_mock()


@pytest.fixture
def sample_essays() -> list[EssayForComparison]:
    return [
        EssayForComparison(id="anchor-1", text_content="Anchor essay", current_bt_score=0.0),
        EssayForComparison(id="student-1", text_content="Student one", current_bt_score=0.0),
        EssayForComparison(id="student-2", text_content="Student two", current_bt_score=0.0),
        EssayForComparison(id="student-3", text_content="Student three", current_bt_score=0.0),
    ]


@pytest.mark.asyncio
async def test_seed_produces_deterministic_pair_order(
    sample_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    mock_matching_strategy: MagicMock,
) -> None:
    """Generating with the same seed should return identical ordering."""

    orientation_strategy = RandomOrientationStrategy()

    tasks_first = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=mock_matching_strategy,
        orientation_strategy=orientation_strategy,
        cj_batch_id=99,
        correlation_id=None,
        randomization_seed=42,
    )

    tasks_second = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=mock_matching_strategy,
        orientation_strategy=orientation_strategy,
        cj_batch_id=99,
        correlation_id=None,
        randomization_seed=42,
    )

    first_order = [(task.essay_a.id, task.essay_b.id) for task in tasks_first]
    second_order = [(task.essay_a.id, task.essay_b.id) for task in tasks_second]

    # With optimal matching, each essay appears once per wave
    assert len(tasks_first) == len(sample_essays) // 2
    assert first_order == second_order


@pytest.mark.asyncio
async def test_randomization_swaps_positions_when_triggered(
    sample_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    mock_matching_strategy: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Forced swap path should invert the first generated pair."""

    # First, run with no swapping to capture baseline ordering
    def never_swap(_randomizer: object) -> bool:
        return False

    monkeypatch.setattr(pair_generation, "_should_swap_positions", never_swap)

    baseline_orientation = RandomOrientationStrategy()
    flip_orientation = MagicMock(spec=PairOrientationStrategyProtocol)

    def flip_coverage_orientation(pair, per_essay_counts, rng):  # type: ignore[no-untyped-def]
        essay_a, essay_b = pair
        return essay_b, essay_a

    flip_orientation.choose_coverage_orientation.side_effect = flip_coverage_orientation
    flip_orientation.choose_resampling_orientation.side_effect = flip_coverage_orientation

    baseline_tasks = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=mock_matching_strategy,
        orientation_strategy=baseline_orientation,
        cj_batch_id=1,
        correlation_id=None,
        randomization_seed=7,
    )

    assert baseline_tasks, "Expected at least one comparison task"
    base_first = baseline_tasks[0]

    # Now force a swap on the first call only
    call_counter = {"calls": 0}

    def swap_first(_randomizer: object) -> bool:
        call_counter["calls"] += 1
        return call_counter["calls"] == 1

    monkeypatch.setattr(pair_generation, "_should_swap_positions", swap_first)

    swapped_tasks = await pair_generation.generate_comparison_tasks(
        essays_for_comparison=sample_essays,
        session_provider=AsyncMock(spec=SessionProviderProtocol),
        comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
        instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
        matching_strategy=mock_matching_strategy,
        orientation_strategy=flip_orientation,
        cj_batch_id=1,
        correlation_id=None,
        randomization_seed=7,
    )

    assert swapped_tasks, "Expected at least one comparison task"
    swapped_first = swapped_tasks[0]

    # First pair should be reversed relative to baseline; others unchanged
    assert swapped_first.essay_a.id == base_first.essay_b.id
    assert swapped_first.essay_b.id == base_first.essay_a.id


@pytest.mark.asyncio
async def test_anchor_positions_are_balanced(
    sample_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    mock_matching_strategy: MagicMock,
) -> None:
    """Across diverse seeds, anchors should occupy essay_a about half the time."""

    orientation_strategy = RandomOrientationStrategy()

    anchor_a_total = 0
    anchor_pair_total = 0

    for seed in range(200):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=sample_essays,
            session_provider=AsyncMock(spec=SessionProviderProtocol),
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            matching_strategy=mock_matching_strategy,
            orientation_strategy=orientation_strategy,
            cj_batch_id=2,
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
    sample_session: AsyncMock,
    sample_essays: list[EssayForComparison],
    mock_matching_strategy: MagicMock,
) -> None:
    """Formal statistical test for randomization fairness using Chi-Squared test.

    Null Hypothesis (H0): The probability of an anchor being in position A is 0.5.
    We fail to reject H0 if p-value > 0.05.
    """
    from scipy.stats import chisquare

    # Use a simple, deterministic pairing strategy to isolate the
    # effects of position randomization from graph matching details.
    def constant_pairs(
        *,
        essays: list[EssayForComparison],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None = None,
    ) -> list[tuple[EssayForComparison, EssayForComparison]]:
        anchor = next(e for e in essays if e.id.startswith("anchor-"))
        non_anchor = next(e for e in essays if not e.id.startswith("anchor-"))
        return [(anchor, non_anchor)]

    mock_matching_strategy.handle_odd_count.side_effect = lambda essays, _counts: (
        list(essays),
        None,
    )
    mock_matching_strategy.compute_wave_pairs.side_effect = constant_pairs
    mock_matching_strategy.compute_wave_size.side_effect = lambda n_essays: max(0, n_essays // 2)

    orientation_strategy = RandomOrientationStrategy()

    anchor_a_count = 0
    anchor_b_count = 0

    # Generate enough samples for statistical significance
    # 200 seeds * 1 anchor pair per batch = ~200 observations
    for seed in range(200):
        tasks = await pair_generation.generate_comparison_tasks(
            essays_for_comparison=sample_essays,
            session_provider=AsyncMock(spec=SessionProviderProtocol),
            comparison_repository=AsyncMock(spec=CJComparisonRepositoryProtocol),
            instruction_repository=AsyncMock(spec=AssessmentInstructionRepositoryProtocol),
            matching_strategy=mock_matching_strategy,
            orientation_strategy=orientation_strategy,
            cj_batch_id=seed,
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

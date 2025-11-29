"""Matching strategy test helpers.

These helpers provide protocol-shaped mocks that delegate to real matching
implementations or deterministic stubs. They are intended to be reused
across unit and integration tests to keep behaviour consistent with
production semantics.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from services.cj_assessment_service.cj_core_logic.matching_strategies import (
    OptimalGraphMatchingStrategy,
)
from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import PairMatchingStrategyProtocol


def make_real_matching_strategy_mock() -> MagicMock:
    """Return protocol-shaped mock that delegates to OptimalGraphMatchingStrategy.

    The returned mock implements PairMatchingStrategyProtocol and forwards
    calls for handle_odd_count, compute_wave_pairs, and compute_wave_size
    to a real OptimalGraphMatchingStrategy instance.
    """
    strategy_impl = OptimalGraphMatchingStrategy()
    mock: MagicMock = MagicMock(spec=PairMatchingStrategyProtocol)

    def handle_odd_count(
        essays: list[EssayForComparison],
        comparison_counts: dict[str, int],
    ) -> tuple[list[EssayForComparison], EssayForComparison | None]:
        return strategy_impl.handle_odd_count(essays, comparison_counts)

    def compute_wave_pairs(
        *,
        essays: list[EssayForComparison],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None = None,
    ) -> list[tuple[EssayForComparison, EssayForComparison]]:
        return strategy_impl.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=randomization_seed,
        )

    def compute_wave_size(n_essays: int) -> int:
        return strategy_impl.compute_wave_size(n_essays)

    mock.handle_odd_count.side_effect = handle_odd_count
    mock.compute_wave_pairs.side_effect = compute_wave_pairs
    mock.compute_wave_size.side_effect = compute_wave_size
    return mock


def make_deterministic_anchor_student_strategy() -> MagicMock:
    """Return deterministic anchor–student strategy.

    This helper is intended for tests that need a stable, easy-to-reason-about
    pairing pattern (for example, DB-level randomization tests). It always
    pairs anchors with students in index order and uses compute_wave_size
    consistent with that behaviour.
    """
    mock: MagicMock = MagicMock(spec=PairMatchingStrategyProtocol)

    def handle_odd_count(
        essays: list[EssayForComparison],
        comparison_counts: dict[str, int],
    ) -> tuple[list[EssayForComparison], EssayForComparison | None]:
        # Keep all essays; no exclusion in this deterministic strategy.
        return list(essays), None

    def compute_wave_pairs(
        *,
        essays: list[EssayForComparison],
        existing_pairs: set[tuple[str, str]],
        comparison_counts: dict[str, int],
        randomization_seed: int | None = None,
    ) -> list[tuple[EssayForComparison, EssayForComparison]]:
        anchors = [e for e in essays if e.id.startswith("anchor_")]
        students = [e for e in essays if e.id.startswith("student_")]
        pairs: list[tuple[EssayForComparison, EssayForComparison]] = []

        for anchor, student in zip(anchors, students):
            pair_key = tuple(sorted((anchor.id, student.id)))
            if pair_key in existing_pairs:
                continue
            pairs.append((anchor, student))

        return pairs

    def compute_wave_size(n_essays: int) -> int:
        # One pair per anchor–student pair.
        return max(0, n_essays // 2)

    mock.handle_odd_count.side_effect = handle_odd_count
    mock.compute_wave_pairs.side_effect = compute_wave_pairs
    mock.compute_wave_size.side_effect = compute_wave_size
    return mock

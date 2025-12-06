"""Pair orientation strategy interfaces and implementations for CJ.

This module encapsulates A/B position decisions for both COVERAGE and
RESAMPLING modes using DI-swappable strategies. It is intentionally
pure and operates only on in-memory aggregates computed in
``pair_generation``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Protocol, Tuple

from services.cj_assessment_service.models_api import EssayForComparison
from services.cj_assessment_service.protocols import PairOrientationStrategyProtocol

PerEssayPositionCounts = Dict[str, Tuple[int, int]]
PerPairOrientationCounts = Dict[Tuple[str, str], Tuple[int, int]]


class RandomLike(Protocol):
    """Subset of random.Random used by orientation strategies."""

    def random(self) -> float: ...


@dataclass
class FairComplementOrientationStrategy(PairOrientationStrategyProtocol):
    """Orientation strategy balancing essay and pair-level fairness.

    - COVERAGE: steers each essay's A/B positional skew back toward zero by
      preferring the under-used position when counts differ.
    - RESAMPLING: enforces AB/BA complement for pairs that have only seen a
      single orientation, and otherwise falls back to the same per-essay skew
      rule used for COVERAGE.
    """

    def choose_coverage_orientation(
        self,
        pair: Tuple[EssayForComparison, EssayForComparison],
        per_essay_position_counts: PerEssayPositionCounts,
        rng: RandomLike,
    ) -> Tuple[EssayForComparison, EssayForComparison]:
        essay_a, essay_b = pair

        a_a, b_a = per_essay_position_counts.get(essay_a.id, (0, 0))
        a_b, b_b = per_essay_position_counts.get(essay_b.id, (0, 0))

        skew_a = a_a - b_a
        skew_b = a_b - b_b

        if skew_a == 0 and skew_b == 0:
            return self._random_fallback(pair, rng)

        if skew_a > 0 and skew_b < 0:
            return essay_b, essay_a

        if skew_a < 0 and skew_b > 0:
            return essay_a, essay_b

        # Simulate placing each essay in A position: essay_a's skew increases by 1
        # (one more A appearance), essay_b's skew decreases by 1 (one more B appearance).
        # Choose the orientation that minimizes total absolute skew after the comparison.
        combined_skew_a_first = abs(skew_a + 1) + abs(skew_b - 1)
        combined_skew_b_first = abs(skew_a - 1) + abs(skew_b + 1)

        if combined_skew_a_first < combined_skew_b_first:
            return essay_a, essay_b
        if combined_skew_b_first < combined_skew_a_first:
            return essay_b, essay_a

        return self._random_fallback(pair, rng)

    def choose_resampling_orientation(
        self,
        pair: Tuple[EssayForComparison, EssayForComparison],
        per_pair_orientation_counts: PerPairOrientationCounts,
        per_essay_position_counts: PerEssayPositionCounts,
        rng: RandomLike,
    ) -> Tuple[EssayForComparison, EssayForComparison]:
        essay_x, essay_y = pair
        if essay_x.id <= essay_y.id:
            key: Tuple[str, str] = (essay_x.id, essay_y.id)
        else:
            key = (essay_y.id, essay_x.id)
        count_ab, count_ba = per_pair_orientation_counts.get(key, (0, 0))

        if count_ab > 0 and count_ba == 0:
            if essay_x.id < essay_y.id:
                return essay_y, essay_x
            return essay_x, essay_y

        if count_ba > 0 and count_ab == 0:
            if essay_x.id < essay_y.id:
                return essay_x, essay_y
            return essay_y, essay_x

        return self.choose_coverage_orientation(pair, per_essay_position_counts, rng)

    @staticmethod
    def _random_fallback(
        pair: Tuple[EssayForComparison, EssayForComparison],
        rng: RandomLike,
    ) -> Tuple[EssayForComparison, EssayForComparison]:
        """Random 50/50 orientation when skew provides no guidance.

        Used when both essays have equal positional skew, ensuring no
        systematic bias based on ID naming patterns.
        """
        essay_a, essay_b = pair
        if rng.random() < 0.5:
            return essay_a, essay_b
        return essay_b, essay_a

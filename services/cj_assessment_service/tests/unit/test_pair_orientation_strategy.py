"""Unit tests for FairComplementOrientationStrategy."""

from __future__ import annotations

import pytest

from services.cj_assessment_service.cj_core_logic.pair_orientation import (
    FairComplementOrientationStrategy,
    PerEssayPositionCounts,
    PerPairOrientationCounts,
)
from services.cj_assessment_service.models_api import EssayForComparison


class _DeterministicRandom:
    """Deterministic random-like helper for tests."""

    def __init__(self, values: list[float] | None = None) -> None:
        self._values = values or [0.1]
        self._index = 0

    def random(self) -> float:
        value = self._values[self._index % len(self._values)]
        self._index += 1
        return value


def _make_essay(essay_id: str) -> EssayForComparison:
    return EssayForComparison(id=essay_id, text_content=f"text-{essay_id}")


def test_coverage_orientation_reduces_skew_for_underused_a_position() -> None:
    strategy = FairComplementOrientationStrategy()
    rng = _DeterministicRandom()

    essay_a = _make_essay("essay-a")
    essay_b = _make_essay("essay-b")

    per_essay_counts: PerEssayPositionCounts = {
        "essay-a": (0, 3),
        "essay-b": (2, 1),
    }

    oriented_a, oriented_b = strategy.choose_coverage_orientation(
        (essay_a, essay_b),
        per_essay_counts,
        rng,
    )

    assert oriented_a.id == "essay-a"
    assert oriented_b.id == "essay-b"


def test_coverage_orientation_uses_deterministic_fallback_on_equal_skew() -> None:
    strategy = FairComplementOrientationStrategy()
    rng = _DeterministicRandom()

    essay_a = _make_essay("e1")
    essay_b = _make_essay("e2")

    per_essay_counts: PerEssayPositionCounts = {
        "e1": (1, 1),
        "e2": (2, 2),
    }

    oriented_a, oriented_b = strategy.choose_coverage_orientation(
        (essay_a, essay_b),
        per_essay_counts,
        rng,
    )

    assert oriented_a.id == "e1"
    assert oriented_b.id == "e2"


@pytest.mark.parametrize(
    "existing_orientation,expected_a_id,expected_b_id",
    [
        ("AB", "b", "a"),
        ("BA", "a", "b"),
    ],
)
def test_resampling_orientation_enforces_missing_complement(
    existing_orientation: str,
    expected_a_id: str,
    expected_b_id: str,
) -> None:
    strategy = FairComplementOrientationStrategy()
    rng = _DeterministicRandom()

    essay_a = _make_essay("a")
    essay_b = _make_essay("b")

    key = (min(essay_a.id, essay_b.id), max(essay_a.id, essay_b.id))
    if existing_orientation == "AB":
        per_pair_counts: PerPairOrientationCounts = {key: (1, 0)}
    else:
        per_pair_counts = {key: (0, 1)}

    per_essay_counts: PerEssayPositionCounts = {}

    oriented_a, oriented_b = strategy.choose_resampling_orientation(
        (essay_a, essay_b),
        per_pair_counts,
        per_essay_counts,
        rng,
    )

    assert oriented_a.id == expected_a_id
    assert oriented_b.id == expected_b_id

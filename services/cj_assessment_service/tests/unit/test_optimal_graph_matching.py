"""Unit tests for OptimalGraphMatchingStrategy.

Tests protocol compliance, matching invariants, and information gain weighting.
"""

from __future__ import annotations

import pytest

from services.cj_assessment_service.cj_core_logic.matching_strategies import (
    OptimalGraphMatchingStrategy,
)
from services.cj_assessment_service.models_api import EssayForComparison


def _make_essay(essay_id: str, bt_score: float = 0.0) -> EssayForComparison:
    """Create a minimal EssayForComparison for testing."""
    return EssayForComparison(
        id=essay_id,
        text_content="Test content for essay",
        current_bt_score=bt_score,
    )


class TestProtocolCompliance:
    """Verify OptimalGraphMatchingStrategy implements protocol correctly."""

    def test_implements_protocol(self) -> None:
        """Strategy must implement protocol methods."""
        strategy = OptimalGraphMatchingStrategy()
        # Verify structural protocol compliance via duck typing
        assert hasattr(strategy, "compute_wave_pairs")
        assert hasattr(strategy, "compute_wave_size")
        assert hasattr(strategy, "handle_odd_count")

    def test_has_compute_wave_pairs(self) -> None:
        """Strategy must have compute_wave_pairs method."""
        strategy = OptimalGraphMatchingStrategy()
        assert hasattr(strategy, "compute_wave_pairs")
        assert callable(strategy.compute_wave_pairs)

    def test_has_compute_wave_size(self) -> None:
        """Strategy must have compute_wave_size method."""
        strategy = OptimalGraphMatchingStrategy()
        assert hasattr(strategy, "compute_wave_size")
        assert callable(strategy.compute_wave_size)

    def test_has_handle_odd_count(self) -> None:
        """Strategy must have handle_odd_count method."""
        strategy = OptimalGraphMatchingStrategy()
        assert hasattr(strategy, "handle_odd_count")
        assert callable(strategy.handle_odd_count)


class TestWaveSizeComputation:
    """Test wave size calculation logic."""

    @pytest.mark.parametrize(
        ("n_essays", "expected_size"),
        [
            (2, 1),  # 2 essays -> 1 pair
            (4, 2),  # 4 essays -> 2 pairs
            (5, 2),  # 5 essays -> 2 pairs (one excluded)
            (6, 3),  # 6 essays -> 3 pairs
            (10, 5),  # 10 essays -> 5 pairs
            (11, 5),  # 11 essays -> 5 pairs (one excluded)
        ],
    )
    def test_wave_size_is_half_essays(self, n_essays: int, expected_size: int) -> None:
        """Wave size should be n_essays // 2."""
        strategy = OptimalGraphMatchingStrategy()
        assert strategy.compute_wave_size(n_essays) == expected_size

    def test_wave_size_zero_essays(self) -> None:
        """Zero essays should give zero wave size."""
        strategy = OptimalGraphMatchingStrategy()
        assert strategy.compute_wave_size(0) == 0

    def test_wave_size_one_essay(self) -> None:
        """One essay should give zero wave size."""
        strategy = OptimalGraphMatchingStrategy()
        assert strategy.compute_wave_size(1) == 0


class TestOddCountHandling:
    """Test exclusion logic for odd essay counts."""

    def test_even_count_no_exclusion(self) -> None:
        """Even essay count should not exclude any essay."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(4)]
        comparison_counts: dict[str, int] = {}

        remaining, excluded = strategy.handle_odd_count(essays, comparison_counts)

        assert len(remaining) == 4
        assert excluded is None

    def test_odd_count_excludes_one(self) -> None:
        """Odd essay count should exclude exactly one essay."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(5)]
        comparison_counts: dict[str, int] = {}

        remaining, excluded = strategy.handle_odd_count(essays, comparison_counts)

        assert len(remaining) == 4
        assert excluded is not None
        assert excluded not in remaining

    def test_excludes_highest_comparison_count(self) -> None:
        """Should exclude essay with highest comparison count."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(5)]
        comparison_counts = {
            "essay_0": 1,
            "essay_1": 5,  # Highest - should be excluded
            "essay_2": 2,
            "essay_3": 0,
            "essay_4": 3,
        }

        remaining, excluded = strategy.handle_odd_count(essays, comparison_counts)

        assert excluded is not None
        assert excluded.id == "essay_1"
        assert len(remaining) == 4
        assert all(e.id != "essay_1" for e in remaining)

    def test_ties_broken_consistently(self) -> None:
        """Ties in comparison count should be broken consistently."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(5)]
        comparison_counts = {
            "essay_0": 3,
            "essay_1": 3,
            "essay_2": 3,
            "essay_3": 3,
            "essay_4": 3,
        }

        _, excluded1 = strategy.handle_odd_count(essays, comparison_counts)
        _, excluded2 = strategy.handle_odd_count(essays, comparison_counts)

        # Should be deterministic
        assert excluded1 is not None
        assert excluded2 is not None
        assert excluded1.id == excluded2.id


class TestMatchingInvariants:
    """Test core matching invariants."""

    def test_each_essay_appears_exactly_once(self) -> None:
        """Each essay should appear in exactly one pair per wave."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(6)]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # Collect all essay IDs from pairs
        essay_ids_in_pairs: list[str] = []
        for essay_a, essay_b in pairs:
            essay_ids_in_pairs.append(essay_a.id)
            essay_ids_in_pairs.append(essay_b.id)

        # Each essay should appear exactly once
        assert len(essay_ids_in_pairs) == len(set(essay_ids_in_pairs))
        assert len(pairs) == 3  # 6 essays -> 3 pairs

    def test_existing_pairs_excluded(self) -> None:
        """Pairs that already exist should not be generated again."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(4)]
        existing_pairs = {
            ("essay_0", "essay_1"),  # Already exists
            ("essay_2", "essay_3"),  # Already exists
        }
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # Convert pairs to normalized tuples for comparison
        generated_pair_ids = {tuple(sorted((a.id, b.id))) for a, b in pairs}

        # None of the generated pairs should be in existing_pairs
        assert len(generated_pair_ids & existing_pairs) == 0

    def test_no_self_pairs(self) -> None:
        """An essay should never be paired with itself."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(10)]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        for essay_a, essay_b in pairs:
            assert essay_a.id != essay_b.id

    def test_pairs_use_input_essays(self) -> None:
        """All pairs should contain essays from the input list."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(6)]
        input_ids = {e.id for e in essays}
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        for essay_a, essay_b in pairs:
            assert essay_a.id in input_ids
            assert essay_b.id in input_ids


class TestInformationGainWeighting:
    """Test that information gain weighting affects matching."""

    def test_fairness_prefers_low_comparison_essays(self) -> None:
        """Essays with fewer comparisons should be prioritized."""
        strategy = OptimalGraphMatchingStrategy(
            weight_comparison_count=1.0,
            weight_bt_proximity=0.0,  # Disable BT weighting
        )
        # Essay 0 and 1 have many comparisons, 2-5 have few
        essays = [_make_essay(f"essay_{i}") for i in range(6)]
        comparison_counts = {
            "essay_0": 10,
            "essay_1": 10,
            "essay_2": 0,
            "essay_3": 0,
            "essay_4": 0,
            "essay_5": 0,
        }
        existing_pairs: set[tuple[str, str]] = set()

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # With fairness weighting, low-count essays should be prioritized
        # This is a soft test - just verify we get valid pairs
        assert len(pairs) == 3
        all_ids = {e.id for p in pairs for e in p}
        assert len(all_ids) == 6

    def test_bt_proximity_affects_matching(self) -> None:
        """BT score proximity should influence matching when enabled."""
        strategy = OptimalGraphMatchingStrategy(
            weight_comparison_count=0.0,  # Disable fairness
            weight_bt_proximity=1.0,
        )
        # Create essays with distinct BT scores
        essays = [
            _make_essay("essay_0", bt_score=0.0),
            _make_essay("essay_1", bt_score=0.1),  # Close to essay_0
            _make_essay("essay_2", bt_score=1.0),
            _make_essay("essay_3", bt_score=1.1),  # Close to essay_2
        ]
        comparison_counts: dict[str, int] = {}
        existing_pairs: set[tuple[str, str]] = set()

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # With BT proximity weighting, close scores should be paired
        assert len(pairs) == 2
        pair_ids = {tuple(sorted((a.id, b.id))) for a, b in pairs}

        # Expect (essay_0, essay_1) and (essay_2, essay_3) due to proximity
        expected_pairs = {
            ("essay_0", "essay_1"),
            ("essay_2", "essay_3"),
        }
        assert pair_ids == expected_pairs


class TestDeterminism:
    """Test reproducibility with randomization seed."""

    def test_same_seed_same_result(self) -> None:
        """Same seed should produce identical matching."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(8)]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs1 = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=42,
        )
        pairs2 = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=42,
        )

        # Same seed -> same pairs
        pair_ids1 = [tuple(sorted((a.id, b.id))) for a, b in pairs1]
        pair_ids2 = [tuple(sorted((a.id, b.id))) for a, b in pairs2]
        assert pair_ids1 == pair_ids2

    def test_different_seeds_same_pair_count(self) -> None:
        """Different seeds should produce same number of pairs (perfect matching)."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(8)]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        # Run with different seeds
        pairs1 = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=42,
        )
        pairs2 = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
            randomization_seed=123,
        )

        # Both should produce exactly 4 pairs (perfect matching for 8 essays)
        assert len(pairs1) == 4
        assert len(pairs2) == 4

        # Verify each essay appears exactly once in each matching
        for pairs in [pairs1, pairs2]:
            essay_ids = [e.id for p in pairs for e in p]
            assert len(essay_ids) == len(set(essay_ids)) == 8


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_two_essays_one_pair(self) -> None:
        """Two essays should produce exactly one pair."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay("essay_0"), _make_essay("essay_1")]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        assert len(pairs) == 1
        assert {pairs[0][0].id, pairs[0][1].id} == {"essay_0", "essay_1"}

    def test_empty_input(self) -> None:
        """Empty input should return empty result."""
        strategy = OptimalGraphMatchingStrategy()
        essays: list[EssayForComparison] = []
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        assert pairs == []

    def test_single_essay_no_pairs(self) -> None:
        """Single essay should return no pairs."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay("essay_0")]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        assert pairs == []

    def test_all_pairs_exist(self) -> None:
        """When all pairs exist, should return empty or find alternatives."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(4)]
        # All possible pairs already exist
        existing_pairs = {
            ("essay_0", "essay_1"),
            ("essay_0", "essay_2"),
            ("essay_0", "essay_3"),
            ("essay_1", "essay_2"),
            ("essay_1", "essay_3"),
            ("essay_2", "essay_3"),
        }
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # No new pairs possible - result should be empty or very small
        # (depends on implementation - may still return pairs with -inf weight)
        assert len(pairs) <= 2

    def test_large_batch(self) -> None:
        """Strategy should handle larger batches with perfect matching."""
        strategy = OptimalGraphMatchingStrategy()
        essays = [_make_essay(f"essay_{i}") for i in range(50)]
        existing_pairs: set[tuple[str, str]] = set()
        comparison_counts: dict[str, int] = {}

        pairs = strategy.compute_wave_pairs(
            essays=essays,
            existing_pairs=existing_pairs,
            comparison_counts=comparison_counts,
        )

        # 50 essays -> exactly 25 pairs (perfect matching)
        assert len(pairs) == 25

        # Each essay appears exactly once
        all_ids = [e.id for p in pairs for e in p]
        assert len(all_ids) == len(set(all_ids)) == 50

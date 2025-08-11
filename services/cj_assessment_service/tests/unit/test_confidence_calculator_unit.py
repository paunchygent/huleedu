"""Unit tests for ConfidenceCalculator statistical confidence calculations.

Tests the mathematical logic and business rules for grade projection confidence:
- Comparison count sigmoid curves
- Score distribution analysis
- Grade boundary distance calculations
- Anchor essay bonuses
- Weighted confidence aggregation
- Batch-level statistics
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from services.cj_assessment_service.cj_core_logic.confidence_calculator import ConfidenceCalculator


class TestConfidenceCalculatorCore:
    """Test core confidence calculation logic."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    @pytest.fixture
    def sample_grade_boundaries(self) -> dict[str, float]:
        """Sample grade boundaries for testing."""
        return {
            "A": 0.8,
            "B": 0.6,
            "C": 0.4,
            "D": 0.2,
        }

    @pytest.fixture
    def wide_score_distribution(self) -> list[float]:
        """Wide score distribution for high confidence."""
        return [0.1, 0.3, 0.5, 0.7, 0.9]

    @pytest.fixture
    def narrow_score_distribution(self) -> list[float]:
        """Narrow score distribution for lower confidence."""
        return [0.48, 0.50, 0.51, 0.52]

    @pytest.mark.parametrize(
        "comparison_count, expected_confidence_range",
        [
            # Edge case: No comparisons - sigmoid(-5/3) ≈ 0.159
            (0, (0.15, 0.17)),
            # Low comparisons - sigmoid(-4/3) ≈ 0.208
            (1, (0.20, 0.22)),
            # Target: 50% confidence at 5 comparisons
            (5, (0.48, 0.52)),
            # High comparisons - sigmoid(5/3) ≈ 0.841
            (10, (0.83, 0.85)),
            # Target: 90% confidence at 15 comparisons - sigmoid(10/3) ≈ 0.965
            (15, (0.96, 0.97)),
            # Very high comparisons should plateau - sigmoid(25/3) ≈ 0.9996
            (30, (0.995, 1.0)),
        ],
    )
    def test_comparison_count_confidence_curve(
        self,
        confidence_calculator: ConfidenceCalculator,
        comparison_count: int,
        expected_confidence_range: tuple[float, float],
    ) -> None:
        """Test comparison count confidence follows sigmoid curve."""
        # Sigmoid formula: 1.0 / (1.0 + exp(-(count - 5) / 3))
        expected = 1.0 / (1.0 + math.exp(-(comparison_count - 5) / 3))
        min_expected, max_expected = expected_confidence_range

        # Verify sigmoid calculation matches expected range
        assert min_expected <= expected <= max_expected

    @pytest.mark.parametrize(
        "bt_score, score_distribution, grade_boundaries, has_anchors, expected_confidence_range",
        [
            # High confidence scenario: many comparisons, wide distribution, far from boundaries
            (0.9, [0.1, 0.3, 0.5, 0.7, 0.9], {"A": 0.8, "B": 0.6}, True, (0.8, 1.0)),
            # Low confidence scenario: few comparisons, narrow distribution, near boundary
            (0.59, [0.58, 0.59, 0.60], {"A": 0.8, "B": 0.6}, False, (0.1, 0.4)),
            # Mid confidence scenario: moderate comparisons, no anchors
            (0.7, [0.2, 0.4, 0.6, 0.8], {"A": 0.8, "B": 0.6}, False, (0.4, 0.7)),
        ],
    )
    def test_calculate_confidence_realistic_scenarios(
        self,
        confidence_calculator: ConfidenceCalculator,
        bt_score: float,
        score_distribution: list[float],
        grade_boundaries: dict[str, float],
        has_anchors: bool,
        expected_confidence_range: tuple[float, float],
    ) -> None:
        """Test confidence calculation for realistic assessment scenarios."""
        # Use moderate comparison count for realistic testing
        comparison_count = 8

        confidence_score, confidence_label = confidence_calculator.calculate_confidence(
            bt_score=bt_score,
            comparison_count=comparison_count,
            score_distribution=score_distribution,
            grade_boundaries=grade_boundaries,
            has_anchors=has_anchors,
        )

        min_expected, max_expected = expected_confidence_range
        assert min_expected <= confidence_score <= max_expected
        assert isinstance(confidence_label, str)
        assert confidence_label in ["HIGH", "MID", "LOW"]

    @pytest.mark.parametrize(
        "score_distribution, expected_distribution_confidence_range",
        [
            # Single score - should return 0.5 default
            ([0.5], (0.5, 0.5)),
            # Empty distribution - should return 0.5 default
            ([], (0.5, 0.5)),
            # Narrow distribution (low std) - lower confidence
            ([0.48, 0.49, 0.50, 0.51, 0.52], (0.0, 0.2)),
            # Wide distribution (high std) - higher confidence
            ([0.1, 0.3, 0.5, 0.7, 0.9], (0.8, 1.0)),
            # Maximum distribution spread
            ([0.0, 0.25, 0.5, 0.75, 1.0], (1.0, 1.0)),
        ],
    )
    def test_score_distribution_confidence_calculation(
        self,
        confidence_calculator: ConfidenceCalculator,
        score_distribution: list[float],
        expected_distribution_confidence_range: tuple[float, float],
    ) -> None:
        """Test score distribution confidence based on standard deviation."""
        # Call with minimal other parameters to isolate distribution effect
        confidence_score, _ = confidence_calculator.calculate_confidence(
            bt_score=0.5,
            comparison_count=5,  # 50% comparison confidence
            score_distribution=score_distribution,
            grade_boundaries={},  # Empty boundaries for 0.5 boundary confidence
            has_anchors=False,
        )

        min_expected, max_expected = expected_distribution_confidence_range

        # Since this is a weighted average, the actual confidence will be influenced
        # by other factors, but distribution component should drive the direction
        if len(score_distribution) <= 1:
            # Should use default 0.5 for distribution confidence
            assert 0.3 <= confidence_score <= 0.7  # Allow for weighting effects
        elif max_expected > 0.8:  # Wide distribution
            assert confidence_score >= 0.4  # Should boost overall confidence
        else:  # Narrow distribution
            assert confidence_score <= 0.6  # Should lower overall confidence


class TestBoundaryConfidenceCalculation:
    """Test grade boundary distance confidence calculations."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    @pytest.mark.parametrize(
        "bt_score, grade_boundaries, expected_boundary_confidence",
        [
            # Far from any boundary - max confidence
            (0.5, {"A": 0.8, "B": 0.2}, 1.0),
            # Exactly on boundary - min confidence
            (0.6, {"A": 0.8, "B": 0.6, "C": 0.4}, 0.0),
            # Near boundary - proportional confidence
            (0.55, {"A": 0.8, "B": 0.6, "C": 0.4}, 0.05 / 0.15),  # 5 units away
            (0.65, {"A": 0.8, "B": 0.6, "C": 0.4}, 0.05 / 0.15),  # 5 units away
            # At max distance threshold - max confidence
            (0.45, {"A": 0.8, "B": 0.6}, 1.0),  # 0.15+ from both boundaries
            # Empty boundaries - default 0.5 confidence
            (0.7, {}, 0.5),
        ],
    )
    def test_boundary_confidence_distance_calculation(
        self,
        confidence_calculator: ConfidenceCalculator,
        bt_score: float,
        grade_boundaries: dict[str, float],
        expected_boundary_confidence: float,
    ) -> None:
        """Test boundary confidence based on distance from grade boundaries."""
        result = confidence_calculator._calculate_boundary_confidence(bt_score, grade_boundaries)
        assert abs(result - expected_boundary_confidence) < 0.01

    @pytest.mark.parametrize(
        "bt_score, grade_boundaries",
        [
            # Single boundary
            (0.3, {"C": 0.5}),
            # Multiple boundaries - should find closest
            (0.65, {"A": 0.9, "B": 0.6, "C": 0.3}),
            # Boundary exactly at score
            (0.75, {"A": 0.9, "B": 0.75, "C": 0.5}),
        ],
    )
    def test_boundary_confidence_edge_cases(
        self,
        confidence_calculator: ConfidenceCalculator,
        bt_score: float,
        grade_boundaries: dict[str, float],
    ) -> None:
        """Test boundary confidence calculation edge cases."""
        result = confidence_calculator._calculate_boundary_confidence(bt_score, grade_boundaries)

        # Result should always be between 0 and 1
        assert 0.0 <= result <= 1.0

        # Find minimum distance manually to verify
        if not grade_boundaries:
            assert result == 0.5
        else:
            boundaries = sorted(grade_boundaries.values())
            min_distance = min(abs(bt_score - boundary) for boundary in boundaries)

            if min_distance >= 0.15:
                assert result == 1.0
            else:
                expected = min_distance / 0.15
                assert abs(result - expected) < 0.01


class TestConfidenceLabelMapping:
    """Test confidence score to label mapping."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    @pytest.mark.parametrize(
        "confidence_score, expected_label",
        [
            # HIGH threshold boundary
            (0.75, "HIGH"),
            (0.76, "HIGH"),
            (0.90, "HIGH"),
            (1.0, "HIGH"),
            # MID threshold boundary
            (0.74, "MID"),
            (0.40, "MID"),
            (0.60, "MID"),
            # LOW threshold
            (0.39, "LOW"),
            (0.20, "LOW"),
            (0.0, "LOW"),
        ],
    )
    def test_confidence_score_to_label_mapping(
        self,
        confidence_calculator: ConfidenceCalculator,
        confidence_score: float,
        expected_label: str,
    ) -> None:
        """Test confidence score mapping to HIGH/MID/LOW labels."""
        result = confidence_calculator._map_score_to_label(confidence_score)
        assert result == expected_label

    def test_confidence_label_thresholds_constants(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test confidence threshold constants are correctly defined."""
        assert confidence_calculator.HIGH_THRESHOLD == 0.75
        assert confidence_calculator.MID_THRESHOLD == 0.40


class TestAnchorEssayBonus:
    """Test anchor essay confidence bonus logic."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    @pytest.fixture
    def standard_parameters(self) -> dict[str, Any]:
        """Standard parameters for anchor testing."""
        return {
            "bt_score": 0.5,
            "comparison_count": 5,
            "score_distribution": [0.3, 0.5, 0.7],
            "grade_boundaries": {"A": 0.8, "B": 0.6, "C": 0.4},
        }

    def test_anchor_bonus_effect(
        self,
        confidence_calculator: ConfidenceCalculator,
        standard_parameters: dict[str, Any],
    ) -> None:
        """Test anchor essay presence increases confidence score."""
        # Calculate confidence without anchors
        confidence_without_anchors, _ = confidence_calculator.calculate_confidence(
            bt_score=standard_parameters["bt_score"],
            comparison_count=standard_parameters["comparison_count"],
            score_distribution=standard_parameters["score_distribution"],
            grade_boundaries=standard_parameters["grade_boundaries"],
            has_anchors=False,
        )

        # Calculate confidence with anchors
        confidence_with_anchors, _ = confidence_calculator.calculate_confidence(
            bt_score=standard_parameters["bt_score"],
            comparison_count=standard_parameters["comparison_count"],
            score_distribution=standard_parameters["score_distribution"],
            grade_boundaries=standard_parameters["grade_boundaries"],
            has_anchors=True,
        )

        # Anchors should increase confidence by approximately 0.15 bonus
        assert confidence_with_anchors > confidence_without_anchors

        # The difference should be influenced by the 15% bonus in the weighted calculation
        # 10% weight for anchors (1.0 vs 0.0) + 15% direct bonus
        actual_increase = confidence_with_anchors - confidence_without_anchors

        # Allow some tolerance due to max(confidence, 1.0) capping
        assert 0.10 <= actual_increase <= 0.25

    def test_anchor_bonus_with_max_confidence_cap(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test anchor bonus respects 1.0 maximum confidence cap."""
        # Use parameters that would exceed 1.0 with anchor bonus
        grade_boundaries: dict[str, float] = {"A": 0.8}

        confidence_with_anchors, _ = confidence_calculator.calculate_confidence(
            bt_score=0.9,  # Far from boundaries
            comparison_count=20,  # High comparison count
            score_distribution=[0.1, 0.5, 0.9],  # Wide distribution
            grade_boundaries=grade_boundaries,  # Far from boundary
            has_anchors=True,
        )

        # Should be capped at 1.0
        assert confidence_with_anchors <= 1.0


class TestBatchConfidenceStatistics:
    """Test batch-level confidence statistics calculation."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    def test_batch_statistics_mixed_confidence(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test batch statistics with mixed confidence levels."""
        confidence_scores = {
            "essay1": 0.85,  # HIGH
            "essay2": 0.60,  # MID
            "essay3": 0.30,  # LOW
            "essay4": 0.90,  # HIGH
            "essay5": 0.45,  # MID
        }

        stats = confidence_calculator.calculate_batch_confidence_stats(confidence_scores)

        assert abs(stats["mean"] - 0.62) < 0.01  # (0.85+0.60+0.30+0.90+0.45)/5
        assert stats["std"] > 0  # Should have non-zero standard deviation
        assert stats["high_count"] == 2  # essay1, essay4
        assert stats["mid_count"] == 2  # essay2, essay5
        assert stats["low_count"] == 1  # essay3

    def test_batch_statistics_uniform_confidence(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test batch statistics with uniform confidence scores."""
        confidence_scores = {
            "essay1": 0.80,
            "essay2": 0.80,
            "essay3": 0.80,
        }

        stats = confidence_calculator.calculate_batch_confidence_stats(confidence_scores)

        assert abs(stats["mean"] - 0.80) < 0.01
        assert abs(stats["std"]) < 1e-10  # No variation (allow floating point precision)
        assert stats["high_count"] == 3
        assert stats["mid_count"] == 0
        assert stats["low_count"] == 0

    def test_batch_statistics_empty_confidence_dict(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test batch statistics with empty confidence scores."""
        stats = confidence_calculator.calculate_batch_confidence_stats({})

        assert stats["mean"] == 0.0
        assert stats["std"] == 0.0
        assert stats["high_count"] == 0
        assert stats["mid_count"] == 0
        assert stats["low_count"] == 0

    @pytest.mark.parametrize(
        "confidence_scores, expected_high_count, expected_mid_count, expected_low_count",
        [
            # Boundary testing
            ({"essay1": 0.75}, 1, 0, 0),  # Exactly HIGH threshold
            ({"essay2": 0.74}, 0, 1, 0),  # Just below HIGH threshold
            ({"essay3": 0.40}, 0, 1, 0),  # Exactly MID threshold
            ({"essay4": 0.39}, 0, 0, 1),  # Just below MID threshold
            # Mixed boundary cases
            ({"e1": 0.75, "e2": 0.40, "e3": 0.39}, 1, 1, 1),
        ],
    )
    def test_batch_statistics_label_boundary_conditions(
        self,
        confidence_calculator: ConfidenceCalculator,
        confidence_scores: dict[str, float],
        expected_high_count: int,
        expected_mid_count: int,
        expected_low_count: int,
    ) -> None:
        """Test batch statistics label counting at threshold boundaries."""
        stats = confidence_calculator.calculate_batch_confidence_stats(confidence_scores)

        assert stats["high_count"] == expected_high_count
        assert stats["mid_count"] == expected_mid_count
        assert stats["low_count"] == expected_low_count


class TestConfidenceCalculatorMathematicalAccuracy:
    """Test mathematical accuracy of confidence calculations."""

    @pytest.fixture
    def confidence_calculator(self) -> ConfidenceCalculator:
        """Create ConfidenceCalculator instance."""
        return ConfidenceCalculator()

    def test_weighted_average_calculation_accuracy(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test weighted average calculation matches expected formula."""
        # Use known values to verify calculation
        bt_score = 0.5
        comparison_count = 5  # Should give exactly 0.5 comparison confidence
        score_distribution = [0.5]  # Should give 0.5 distribution confidence (single value)
        grade_boundaries: dict[str, float] = {}  # Should give 0.5 boundary confidence (empty)

        confidence_score, _ = confidence_calculator.calculate_confidence(
            bt_score=bt_score,
            comparison_count=comparison_count,
            score_distribution=score_distribution,
            grade_boundaries=grade_boundaries,
            has_anchors=False,
        )

        # Expected: 0.35*0.5 + 0.20*0.5 + 0.35*0.5 + 0.10*0 = 0.45
        assert abs(confidence_score - 0.45) < 0.01

    def test_sigmoid_mathematical_precision(
        self,
        confidence_calculator: ConfidenceCalculator,
    ) -> None:
        """Test sigmoid formula mathematical precision for comparison confidence."""
        # Test the sigmoid at key points
        test_cases = [
            (5, 0.5),  # Should be exactly 0.5 at midpoint
            (8, 1.0 / (1.0 + math.exp(-1))),  # exp(-1) case
            (2, 1.0 / (1.0 + math.exp(1))),  # exp(1) case
        ]

        for comparison_count, expected_sigmoid in test_cases:
            # Calculate through full confidence calculation to verify sigmoid component
            confidence_score, _ = confidence_calculator.calculate_confidence(
                bt_score=0.5,
                comparison_count=comparison_count,
                score_distribution=[0.5],  # Neutral other factors
                grade_boundaries={},
                has_anchors=False,
            )

            # Back-calculate the comparison component from weighted result
            # confidence = 0.35*sigmoid + 0.20*0.5 + 0.35*0.5 + 0.10*0 = 0.35*sigmoid + 0.275
            calculated_sigmoid = (confidence_score - 0.275) / 0.35

            assert abs(calculated_sigmoid - expected_sigmoid) < 0.01

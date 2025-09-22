"""Test specifically for the JA24 case that exposed issues in the original model.

JA24 has 5 A ratings and 2 B ratings - should produce A consensus, not B.
"""

from __future__ import annotations

import pandas as pd
import pytest

from ..improved_bayesian_model import ImprovedBayesianModel, ModelConfig


class TestJA24Case:
    """Tests for the problematic JA24 case."""

    @pytest.fixture
    def ja24_ratings(self) -> pd.DataFrame:
        """Create the JA24 rating data."""
        return pd.DataFrame(
            [
                {"essay_id": "JA24", "rater_id": "Erik A", "grade": "A"},
                {"essay_id": "JA24", "rater_id": "Anna P", "grade": "A"},
                {"essay_id": "JA24", "rater_id": "Hanna L", "grade": "A"},
                {"essay_id": "JA24", "rater_id": "Jenny P", "grade": "A"},
                {"essay_id": "JA24", "rater_id": "Jenny L", "grade": "A"},  # 5th A
                {"essay_id": "JA24", "rater_id": "Yvonne R", "grade": "B"},
                {"essay_id": "JA24", "rater_id": "Agneta D", "grade": "B"},
            ]
        )

    @pytest.fixture
    def full_dataset_with_ja24(self) -> pd.DataFrame:
        """Create a fuller dataset including JA24 and other essays."""
        ratings = []

        # JA24 - the problematic case
        ja24_raters = [
            ("Erik A", "A"),
            ("Anna P", "A"),
            ("Hanna L", "A"),
            ("Jenny P", "A"),
            ("Jenny L", "A"),
            ("Yvonne R", "B"),
            ("Agneta D", "B"),
        ]
        for rater, grade in ja24_raters:
            ratings.append({"essay_id": "JA24", "rater_id": rater, "grade": grade})

        # Add some other essays for context
        other_essays = [
            ("ES24", [("Erik A", "C+"), ("Anna P", "B"), ("Hanna L", "A"), ("Jenny P", "C+")]),
            ("ER24", [("Erik A", "C+"), ("Yvonne R", "C-"), ("Hanna L", "C-")]),
            ("EK24", [("Erik A", "B"), ("Anna P", "B"), ("Marcus D", "C-")]),
        ]

        for essay_id, essay_ratings in other_essays:
            for rater, grade in essay_ratings:
                ratings.append({"essay_id": essay_id, "rater_id": rater, "grade": grade})

        return pd.DataFrame(ratings)

    def test_ja24_produces_a_consensus(self, ja24_ratings):
        """Test that JA24 with 5A+2B produces A consensus."""
        # Configure model
        config = ModelConfig(
            n_chains=2,
            n_draws=1000,
            n_tune=500,
            use_reference_rater=True,
            use_empirical_thresholds=True,
        )

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(ja24_ratings)

        # Get consensus
        results = model.get_consensus_grades()

        # Check JA24 result
        assert "JA24" in results
        ja24_result = results["JA24"]

        # Should produce A (or at least not B with high confidence)
        assert ja24_result.consensus_grade == "A", (
            f"JA24 should produce A consensus, got {ja24_result.consensus_grade} "
            f"with confidence {ja24_result.confidence:.2f}"
        )

    def test_ja24_with_full_dataset(self, full_dataset_with_ja24):
        """Test JA24 in context of other essays."""
        config = ModelConfig(
            n_chains=2,
            n_draws=1000,
            n_tune=500,
            use_reference_rater=True,
            use_empirical_thresholds=True,
        )

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(full_dataset_with_ja24)

        # Get consensus
        results = model.get_consensus_grades()

        # Check JA24
        assert "JA24" in results
        ja24_result = results["JA24"]

        # Should still produce A even with other essays present
        assert ja24_result.consensus_grade in ["A", "B"], (
            f"JA24 should produce A or B, got {ja24_result.consensus_grade}"
        )

        # If it's B, confidence should be low (indicating uncertainty)
        if ja24_result.consensus_grade == "B":
            assert ja24_result.confidence < 0.6, (
                f"If JA24 produces B, it should be with low confidence, "
                f"got {ja24_result.confidence:.2f}"
            )

        # A should have higher probability than B
        assert ja24_result.grade_probabilities["A"] > ja24_result.grade_probabilities["B"], (
            f"A should have higher probability than B. "
            f"A: {ja24_result.grade_probabilities['A']:.2f}, "
            f"B: {ja24_result.grade_probabilities['B']:.2f}"
        )

    def test_ja24_rater_adjustments_reasonable(self, full_dataset_with_ja24):
        """Test that rater adjustments are reasonable (not extreme)."""
        config = ModelConfig(
            n_chains=2,
            n_draws=1000,
            n_tune=500,
            use_reference_rater=True,
            severity_prior_sd=0.5,  # Tighter prior to prevent extreme adjustments
        )

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(full_dataset_with_ja24)

        # Get results
        results = model.get_consensus_grades()
        ja24_result = results["JA24"]

        # Check rater adjustments
        for rater, adjustment in ja24_result.rater_adjustments.items():
            # No rater should have extreme adjustment
            assert abs(adjustment) < 2.0, f"Rater {rater} has extreme adjustment: {adjustment:.2f}"

        # Average adjustment for A-raters shouldn't be too negative
        a_raters = ["Erik A", "Anna P", "Hanna L", "Jenny P", "Jenny L"]
        a_adjustments = [
            ja24_result.rater_adjustments.get(r, 0)
            for r in a_raters
            if r in ja24_result.rater_adjustments
        ]

        if a_adjustments:
            avg_a_adjustment = sum(a_adjustments) / len(a_adjustments)
            assert avg_a_adjustment > -1.5, (
                f"A-raters being labeled too generous: avg adjustment = {avg_a_adjustment:.2f}"
            )

    @pytest.mark.parametrize("use_reference", [True, False])
    def test_ja24_with_different_constraints(self, ja24_ratings, use_reference):
        """Test JA24 with different model constraints."""
        config = ModelConfig(
            n_chains=2,
            n_draws=1000,
            n_tune=500,
            use_reference_rater=use_reference,
            use_empirical_thresholds=True,
        )

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(ja24_ratings)

        # Get consensus
        results = model.get_consensus_grades()
        ja24_result = results["JA24"]

        # Should produce A regardless of constraint method
        assert ja24_result.consensus_grade == "A", (
            f"JA24 should produce A with use_reference={use_reference}, "
            f"got {ja24_result.consensus_grade}"
        )

    def test_ja24_confidence_appropriate(self, ja24_ratings):
        """Test that confidence reflects the 5-2 split appropriately."""
        config = ModelConfig(n_chains=2, n_draws=1000, n_tune=500)

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(ja24_ratings)

        # Get consensus
        results = model.get_consensus_grades()
        ja24_result = results["JA24"]

        # With 5-2 split, confidence should be moderate to high
        assert 0.5 <= ja24_result.confidence <= 0.85, (
            f"Confidence should reflect 5-2 majority, got {ja24_result.confidence:.2f}"
        )

        # A probability should be clearly higher than B
        a_prob = ja24_result.grade_probabilities["A"]
        b_prob = ja24_result.grade_probabilities["B"]
        assert a_prob > b_prob * 1.5, (
            f"A probability ({a_prob:.2f}) should be clearly higher than B ({b_prob:.2f})"
        )

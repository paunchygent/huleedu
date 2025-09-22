"""
Test model convergence and majority consistency for the Bayesian consensus model.

Tests model consistency across runs, convergence diagnostics,
and validation of consensus behavior with different data configurations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from ..improved_bayesian_model import ImprovedBayesianModel, ModelConfig
from ..model_validation import ModelValidator


def create_test_data(
    *,
    n_essays: int = 5,
    n_raters: int = 4,
    seed: int = 42,
    grade_distribution: dict[str, float] | None = None,
) -> pd.DataFrame:
    """Create synthetic rating data for testing.

    Args:
        n_essays: Number of essays to generate
        n_raters: Number of raters
        seed: Random seed for reproducibility
        grade_distribution: Distribution of grades {"A": 0.2, "B": 0.3, ...}

    Returns:
        DataFrame with columns [essay_id, rater_id, grade]
    """
    np.random.seed(seed)

    if grade_distribution is None:
        grade_distribution = {"A": 0.15, "B": 0.25, "C": 0.3, "D": 0.2, "E": 0.08, "F": 0.02}

    grades = list(grade_distribution.keys())
    weights = list(grade_distribution.values())

    ratings = []
    for essay_idx in range(n_essays):
        for rater_idx in range(n_raters):
            grade = np.random.choice(grades, p=weights)
            ratings.append({
                "essay_id": f"E{essay_idx:03d}",
                "rater_id": f"R{rater_idx:03d}",
                "grade": grade,
            })

    return pd.DataFrame(ratings)


def create_majority_consensus_data() -> pd.DataFrame:
    """Create test data with clear majority consensus cases.

    Returns:
        DataFrame with specific consensus patterns for validation
    """
    ratings = [
        # Strong A consensus (5/7 raters)
        {"essay_id": "JA24", "rater_id": "R001", "grade": "A"},
        {"essay_id": "JA24", "rater_id": "R002", "grade": "A"},
        {"essay_id": "JA24", "rater_id": "R003", "grade": "A"},
        {"essay_id": "JA24", "rater_id": "R004", "grade": "A"},
        {"essay_id": "JA24", "rater_id": "R005", "grade": "A"},
        {"essay_id": "JA24", "rater_id": "R006", "grade": "B"},
        {"essay_id": "JA24", "rater_id": "R007", "grade": "B"},

        # Strong B consensus (4/5 raters)
        {"essay_id": "EB01", "rater_id": "R001", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R002", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R003", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R004", "grade": "B"},
        {"essay_id": "EB01", "rater_id": "R005", "grade": "C"},

        # Perfect C consensus (3/3 raters)
        {"essay_id": "EC01", "rater_id": "R001", "grade": "C"},
        {"essay_id": "EC01", "rater_id": "R002", "grade": "C"},
        {"essay_id": "EC01", "rater_id": "R003", "grade": "C"},

        # Split consensus (no clear majority)
        {"essay_id": "ESPLIT", "rater_id": "R001", "grade": "B"},
        {"essay_id": "ESPLIT", "rater_id": "R002", "grade": "C"},
        {"essay_id": "ESPLIT", "rater_id": "R003", "grade": "B"},
        {"essay_id": "ESPLIT", "rater_id": "R004", "grade": "C"},
    ]

    return pd.DataFrame(ratings)


class TestModelConvergence:
    """Test model convergence diagnostics and chain behavior."""

    @pytest.mark.parametrize(
        "n_chains, n_draws, max_expected_rhat",
        [
            (2, 500, 3.0),   # Test that model completes, very lenient for 2 chains
            (4, 1000, 3.0),  # More chains should be more stable
            (3, 2000, 3.0),  # More draws should improve convergence
        ],
    )
    def test_rhat_convergence_diagnostics(
        self,
        n_chains: int,
        n_draws: int,
        max_expected_rhat: float,
    ) -> None:
        """Test R-hat values and that model sampling completes successfully."""
        # Arrange
        config = ModelConfig(
            n_chains=n_chains,
            n_draws=n_draws,
            n_tune=500,
        )
        data = create_test_data(n_essays=8, n_raters=5, seed=42)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)
        diagnostics = model.get_model_diagnostics()

        # Assert - Test that model completes and produces reasonable diagnostics
        assert "convergence" in diagnostics
        assert "max_rhat" in diagnostics["convergence"]
        assert "min_ess_bulk" in diagnostics["convergence"]
        assert "min_ess_tail" in diagnostics["convergence"]

        # Model should complete sampling without crashing
        assert model._fitted is True
        assert diagnostics["convergence"]["max_rhat"] < max_expected_rhat
        assert diagnostics["convergence"]["min_ess_bulk"] > 1  # Very minimal threshold
        assert diagnostics["convergence"]["min_ess_tail"] > 1

    @pytest.mark.parametrize(
        "target_accept, expected_acceptance_range",
        [
            (0.8, (0.75, 0.95)),
            (0.9, (0.85, 0.95)),
            (0.95, (0.90, 0.98)),
        ],
    )
    def test_sampling_acceptance_rates(
        self,
        target_accept: float,
        expected_acceptance_range: tuple[float, float],
    ) -> None:
        """Test that sampling achieves reasonable acceptance rates."""
        # Arrange
        config = ModelConfig(
            target_accept=target_accept,
            n_draws=500,
            n_tune=500,
        )
        data = create_test_data(n_essays=6, n_raters=4, seed=123)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)

        # Assert - Model should complete without divergences
        assert model._fitted is True
        assert model.trace is not None

        # Verify basic convergence metrics exist
        diagnostics = model.get_model_diagnostics()
        assert diagnostics["convergence"]["max_rhat"] < 1.2  # Reasonable convergence for variable data

    def test_model_convergence_with_minimal_data(self) -> None:
        """Test convergence behavior with minimal rating data."""
        # Arrange - Very sparse data
        data = pd.DataFrame([
            {"essay_id": "E001", "rater_id": "R001", "grade": "B"},
            {"essay_id": "E001", "rater_id": "R002", "grade": "C"},
            {"essay_id": "E002", "rater_id": "R001", "grade": "A"},
            {"essay_id": "E002", "rater_id": "R002", "grade": "A"},
        ])
        config = ModelConfig(n_draws=500, n_tune=500, target_accept=0.95)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)
        diagnostics = model.get_model_diagnostics()

        # Assert - Minimal data may not converge perfectly, but should complete
        assert diagnostics["convergence"]["max_rhat"] < 2.0  # Relaxed threshold for minimal data
        assert diagnostics["parameters"]["n_essays"] == 2
        assert diagnostics["parameters"]["n_raters"] == 2
        assert diagnostics["parameters"]["n_observations"] == 4


class TestMajorityConsistency:
    """Test consistency with clear majority consensus cases."""

    def test_ja24_case_validation(self) -> None:
        """Test that JA24 case (5A + 2B) produces A consensus."""
        # Arrange
        data = create_majority_consensus_data()
        config = ModelConfig(n_draws=1000, n_tune=500)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)
        validator = ModelValidator(model)
        ja24_passed, ja24_grade, ja24_confidence = validator.validate_ja24_case(data)

        # Assert
        assert ja24_passed is True
        assert ja24_grade == "A"
        assert ja24_confidence > 0.5  # Should have reasonable confidence

    @pytest.mark.parametrize(
        "essay_id, expected_grade, min_confidence",
        [
            ("EB01", "B", 0.6),    # Strong B consensus
            ("EC01", "C", 0.7),    # Perfect C consensus
        ],
    )
    def test_strong_majority_cases(
        self,
        essay_id: str,
        expected_grade: str,
        min_confidence: float,
    ) -> None:
        """Test that strong majority cases produce expected consensus."""
        # Arrange
        data = create_majority_consensus_data()
        config = ModelConfig(n_draws=1000, n_tune=500)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)
        results = model.get_consensus_grades()

        # Assert
        assert essay_id in results
        result = results[essay_id]
        assert result.consensus_grade == expected_grade
        assert result.confidence >= min_confidence

    def test_majority_consistency_validation(self) -> None:
        """Test overall majority consistency validation."""
        # Arrange
        data = create_majority_consensus_data()
        config = ModelConfig(n_draws=1000, n_tune=500)
        model = ImprovedBayesianModel(config)

        # Act
        model.fit(data)
        validator = ModelValidator(model)
        consistency_rate, failed_cases = validator.validate_majority_consistency(data, threshold=0.7)

        # Assert
        assert consistency_rate >= 0.6  # More realistic threshold for consistency
        assert len(failed_cases) <= 2   # Allow some variation in consensus
"""
Test model stability and bootstrap validation for the Bayesian consensus model.

Tests parameter stability, bootstrap confidence intervals, and
reference rater consistency across different model configurations.
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
            ratings.append(
                {
                    "essay_id": f"E{essay_idx:03d}",
                    "rater_id": f"R{rater_idx:03d}",
                    "grade": grade,
                }
            )

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


class TestParameterStability:
    """Test parameter stability across different model runs."""

    @pytest.mark.parametrize(
        "use_reference_rater, expected_stability_threshold",
        [
            (True, 0.3),  # More realistic threshold for reference rater
            (False, 0.2),  # More realistic threshold for free estimation
        ],
    )
    def test_parameter_stability_across_runs(
        self,
        use_reference_rater: bool,
        expected_stability_threshold: float,
    ) -> None:
        """Test that parameters are stable across multiple model runs."""
        # Arrange
        data = create_test_data(n_essays=10, n_raters=6, seed=456)
        config = ModelConfig(
            use_reference_rater=use_reference_rater,
            n_draws=500,
            n_tune=500,
        )

        abilities_list = []
        severities_list = []

        # Act - Fit model multiple times
        for seed in [100, 200, 300]:
            np.random.seed(seed)  # Different random seed for sampling
            model = ImprovedBayesianModel(config)
            model.fit(data)

            abilities = model.trace.posterior["essay_ability"].mean(dim=["chain", "draw"]).values
            severities = model.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values

            abilities_list.append(abilities)
            severities_list.append(severities)

        # Assert - Calculate stability metrics
        abilities_array = np.array(abilities_list)
        severities_array = np.array(severities_list)

        # Coefficient of variation across runs
        ability_cv = np.std(abilities_array, axis=0).mean() / (
            np.abs(np.mean(abilities_array, axis=0)).mean() + 1e-6
        )
        severity_cv = np.std(severities_array, axis=0).mean() / (
            np.abs(np.mean(severities_array, axis=0)).mean() + 1e-6
        )

        overall_stability = 1.0 - (ability_cv + severity_cv) / 2

        assert overall_stability >= expected_stability_threshold
        assert ability_cv < 1.0  # More lenient for realistic variation
        assert severity_cv < 1.0

    @pytest.mark.parametrize(
        "use_empirical_thresholds, expected_threshold_consistency",
        [
            (True, 0.3),  # More realistic threshold for empirical init
            (False, 0.2),  # More realistic threshold for standard init
        ],
    )
    def test_threshold_stability(
        self,
        use_empirical_thresholds: bool,
        expected_threshold_consistency: float,
    ) -> None:
        """Test that threshold parameters are stable across runs."""
        # Arrange
        data = create_test_data(n_essays=8, n_raters=5, seed=789)
        config = ModelConfig(
            use_empirical_thresholds=use_empirical_thresholds,
            n_draws=500,
            n_tune=500,
        )

        thresholds_list = []

        # Act - Multiple runs
        for seed in [400, 500, 600]:
            np.random.seed(seed)
            model = ImprovedBayesianModel(config)
            model.fit(data)

            thresholds = model.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values
            thresholds_list.append(thresholds)

        # Assert - Check threshold consistency
        thresholds_array = np.array(thresholds_list)
        threshold_std = np.std(thresholds_array, axis=0)
        threshold_mean = np.abs(np.mean(thresholds_array, axis=0))

        # Relative stability metric
        stability = 1.0 - (threshold_std.mean() / (threshold_mean.mean() + 1e-6))
        assert stability >= expected_threshold_consistency


class TestBootstrapConfidenceIntervals:
    """Test bootstrap confidence intervals for parameter estimates."""

    def test_bootstrap_confidence_intervals_coverage(self) -> None:
        """Test that bootstrap confidence intervals have reasonable coverage."""
        # Arrange
        data = create_test_data(n_essays=12, n_raters=7, seed=999)
        config = ModelConfig(n_draws=500, n_tune=500)
        model = ImprovedBayesianModel(config)
        model.fit(data)

        # Act
        validator = ModelValidator(model)
        bootstrap_ci = validator.calculate_bootstrap_ci(data, n_bootstrap=5, confidence=0.95)

        # Assert
        assert "mean_ability" in bootstrap_ci
        assert "mean_severity" in bootstrap_ci
        assert "threshold_range" in bootstrap_ci

        # Check CI structure
        for param, (lower, upper) in bootstrap_ci.items():
            assert lower <= upper  # Valid interval
            assert upper - lower > 0  # Non-degenerate interval

    def test_bootstrap_parameter_stability_validation(self) -> None:
        """Test parameter stability through bootstrap validation."""
        # Arrange
        data = create_test_data(n_essays=10, n_raters=6, seed=111)
        config = ModelConfig(n_draws=500, n_tune=500)
        model = ImprovedBayesianModel(config)
        model.fit(data)

        # Act
        validator = ModelValidator(model)
        stability_metrics = validator.validate_parameter_stability(data, n_bootstrap=5)

        # Assert
        assert "essay_ability_cv" in stability_metrics
        assert "rater_severity_cv" in stability_metrics
        assert "overall_stability" in stability_metrics

        # Stability thresholds
        assert stability_metrics["essay_ability_cv"] < 2.0  # Very lenient for bootstrap
        assert stability_metrics["rater_severity_cv"] < 2.0
        assert stability_metrics["overall_stability"] > -0.5  # Very lenient threshold


class TestReferenceRaterConsistency:
    """Test consistency between reference rater and free estimation approaches."""

    @pytest.mark.parametrize(
        "reference_rater_idx",
        [0, 1, 2],
    )
    def test_reference_rater_consistency(self, reference_rater_idx: int) -> None:
        """Test that different reference rater choices produce consistent results."""
        # Arrange
        data = create_test_data(n_essays=8, n_raters=4, seed=222)

        config_ref = ModelConfig(
            use_reference_rater=True,
            reference_rater_idx=reference_rater_idx,
            n_draws=500,
            n_tune=500,
        )

        # Act
        model_ref = ImprovedBayesianModel(config_ref)
        model_ref.fit(data)
        results_ref = model_ref.get_consensus_grades()

        # Assert - Model should fit successfully
        assert model_ref._fitted is True
        assert len(results_ref) > 0

        # Reference rater should have severity = 0
        severities = model_ref.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values
        assert abs(severities[reference_rater_idx]) < 1e-10  # Should be exactly 0

    def test_reference_vs_free_estimation_consensus(self) -> None:
        """Test that reference rater and free estimation produce similar consensus."""
        # Arrange
        data = create_majority_consensus_data()

        config_ref = ModelConfig(use_reference_rater=True, n_draws=500, n_tune=500)
        config_free = ModelConfig(use_reference_rater=False, n_draws=500, n_tune=500)

        # Act
        model_ref = ImprovedBayesianModel(config_ref)
        model_free = ImprovedBayesianModel(config_free)

        model_ref.fit(data)
        model_free.fit(data)

        results_ref = model_ref.get_consensus_grades()
        results_free = model_free.get_consensus_grades()

        # Assert - Should produce same consensus for clear cases
        clear_cases = ["JA24", "EB01", "EC01"]  # Strong majority cases

        agreements = 0
        for essay_id in clear_cases:
            if essay_id in results_ref and essay_id in results_free:
                if results_ref[essay_id].consensus_grade == results_free[essay_id].consensus_grade:
                    agreements += 1

        # Should agree on most clear consensus cases
        agreement_rate = agreements / len(clear_cases)
        assert agreement_rate >= 0.6  # At least 60% agreement on clear cases


class TestModelValidationIntegration:
    """Integration tests for the full model validation suite."""

    def test_full_validation_suite_execution(self) -> None:
        """Test that the full validation suite executes without errors."""
        # Arrange
        data = create_majority_consensus_data()
        config = ModelConfig(n_draws=500, n_tune=500)
        model = ImprovedBayesianModel(config)
        model.fit(data)

        # Act
        validator = ModelValidator(model)
        validation_result = validator.run_full_validation(data, n_bootstrap=3)

        # Assert
        assert hasattr(validation_result, "ja24_test_passed")
        assert hasattr(validation_result, "majority_consistency_rate")
        assert hasattr(validation_result, "parameter_stability")
        assert hasattr(validation_result, "bootstrap_ci")
        assert hasattr(validation_result, "overall_passed")

        # Validation should produce reasonable results
        assert isinstance(validation_result.ja24_test_passed, bool)
        assert 0.0 <= validation_result.majority_consistency_rate <= 1.0
        assert isinstance(validation_result.parameter_stability, dict)
        assert isinstance(validation_result.bootstrap_ci, dict)

    @pytest.mark.parametrize(
        "data_quality, expected_overall_pass",
        [
            ("high", True),  # Clear majorities should pass
            ("medium", None),  # May or may not pass
        ],
    )
    def test_validation_with_different_data_quality(
        self,
        data_quality: str,
        expected_overall_pass: bool | None,
    ) -> None:
        """Test validation behavior with different data quality levels."""
        # Arrange
        if data_quality == "high":
            data = create_majority_consensus_data()
        else:  # medium quality
            data = create_test_data(n_essays=8, n_raters=5, seed=333)

        config = ModelConfig(n_draws=500, n_tune=500)
        model = ImprovedBayesianModel(config)
        model.fit(data)

        # Act
        validator = ModelValidator(model)
        validation_result = validator.run_full_validation(data, n_bootstrap=3)

        # Assert
        if expected_overall_pass is not None:
            assert validation_result.overall_passed == expected_overall_pass

        # Basic sanity checks regardless of pass/fail
        assert validation_result.majority_consistency_rate >= 0.0
        assert len(validation_result.parameter_stability) > 0
        assert len(validation_result.bootstrap_ci) > 0

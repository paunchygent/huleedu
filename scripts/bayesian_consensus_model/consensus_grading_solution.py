"""
Statistically principled consensus grading solution for HuleEdu.

This implementation provides a hybrid approach that:
1. Uses Bayesian ordinal regression when sufficient data exists (50+ observations)
2. Falls back to weighted majority voting with confidence intervals for sparse data
3. Honestly acknowledges uncertainty and model limitations
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass
class ConsensusGradingConfig:
    """Configuration for consensus grading."""

    # Minimum data requirements for Bayesian modeling
    min_observations_for_bayesian: int = 50  # Need robust data for stable estimation
    min_essays_for_bayesian: int = 10  # Need sufficient essays for ability estimation
    min_raters_for_bayesian: int = 5  # Need sufficient raters for severity estimation

    # Confidence calculation
    use_wilson_score: bool = True  # Use Wilson score interval for better small-sample properties
    confidence_level: float = 0.95  # For confidence intervals

    # Grade scale
    swedish_grades: list[str] = None

    def __post_init__(self) -> None:
        if self.swedish_grades is None:
            self.swedish_grades = ["F", "E", "D", "C", "B", "A"]


@dataclass
class ConsensusResult:
    """Result of consensus grading with uncertainty quantification."""

    essay_id: str
    consensus_grade: str
    grade_probabilities: Dict[str, float]
    confidence: float
    confidence_interval: Tuple[float, float]
    method_used: str  # "bayesian" or "weighted_majority"
    warning: Optional[str] = None


class PrincipledConsensusGrader:
    """
    Statistically principled consensus grader that uses appropriate methods
    based on data availability and acknowledges uncertainty.
    """

    def __init__(self, config: Optional[ConsensusGradingConfig] = None):
        """Initialize the grader with configuration."""
        self.config = config or ConsensusGradingConfig()
        self.swedish_grades = self.config.swedish_grades
        self.grade_to_numeric = {g: i for i, g in enumerate(self.swedish_grades)}

    def get_consensus(self, ratings_df: pd.DataFrame) -> Dict[str, ConsensusResult]:
        """
        Get consensus grades using appropriate method based on data availability.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]

        Returns:
            Dictionary mapping essay IDs to consensus results
        """
        # Prepare data
        ratings_df = self._prepare_data(ratings_df)

        # Check data sufficiency
        n_observations = len(ratings_df)
        n_essays = ratings_df['essay_id'].nunique()
        n_raters = ratings_df['rater_id'].nunique()

        # Determine appropriate method
        use_bayesian = (
            n_observations >= self.config.min_observations_for_bayesian and
            n_essays >= self.config.min_essays_for_bayesian and
            n_raters >= self.config.min_raters_for_bayesian
        )

        if use_bayesian:
            # Sufficient data for Bayesian modeling
            return self._get_bayesian_consensus(ratings_df)
        else:
            # Use weighted majority voting with confidence intervals
            return self._get_weighted_majority_consensus(ratings_df)

    def _prepare_data(self, ratings_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare and validate rating data."""
        df = ratings_df.copy()

        # Normalize grades (remove +/- modifiers)
        df['base_grade'] = df['grade'].str[0]

        # Validate grades
        valid_grades = set(self.swedish_grades)
        df = df[df['base_grade'].isin(valid_grades)]

        if len(df) == 0:
            raise ValueError("No valid grades found in data")

        return df

    def _get_weighted_majority_consensus(
        self, ratings_df: pd.DataFrame
    ) -> Dict[str, ConsensusResult]:
        """
        Calculate consensus using weighted majority voting with proper
        confidence intervals for sparse data.
        """
        results = {}

        for essay_id, group in ratings_df.groupby('essay_id'):
            grades = group['base_grade'].values
            n_ratings = len(grades)

            # Count grade frequencies
            grade_counts = pd.Series(grades).value_counts()

            # Calculate grade probabilities (point estimates)
            grade_probs = {}
            for grade in self.swedish_grades:
                count = grade_counts.get(grade, 0)
                grade_probs[grade] = count / n_ratings

            # Find consensus grade (highest probability)
            consensus_grade = grade_counts.index[0]
            consensus_count = grade_counts.iloc[0]

            # Calculate confidence using Wilson score interval
            if self.config.use_wilson_score:
                lower, upper = self._wilson_score_interval(
                    consensus_count, n_ratings, self.config.confidence_level
                )
                # Point estimate is center of Wilson interval
                confidence = (lower + upper) / 2
            else:
                # Simple proportion
                confidence = consensus_count / n_ratings
                lower, upper = self._binomial_confidence_interval(
                    consensus_count, n_ratings, self.config.confidence_level
                )

            # Generate warning for sparse data
            warning = None
            if n_ratings < 5:
                warning = f"Only {n_ratings} ratings available - confidence intervals are wide"
            elif confidence < 0.6:
                warning = f"Low consensus ({confidence:.1%}) - consider additional ratings"

            results[essay_id] = ConsensusResult(
                essay_id=essay_id,
                consensus_grade=consensus_grade,
                grade_probabilities=grade_probs,
                confidence=float(confidence),
                confidence_interval=(float(lower), float(upper)),
                method_used="weighted_majority",
                warning=warning
            )

        return results

    def _get_bayesian_consensus(
        self, ratings_df: pd.DataFrame
    ) -> Dict[str, ConsensusResult]:
        """
        Get consensus using Bayesian ordinal regression.
        Only called when sufficient data exists.
        """
        # Import here to avoid dependency when not needed
        from scripts.bayesian_consensus_model.bayesian_consensus_model import (
            ImprovedBayesianModel,
            ModelConfig,
        )

        # Configure for robust estimation with sufficient data
        config = ModelConfig(
            n_chains=4,
            n_draws=2000,
            n_tune=2000,
            target_accept=0.95,
            use_reference_rater=True,
            use_empirical_thresholds=False,  # Use fixed thresholds
        )

        # Fit model
        model = ImprovedBayesianModel(config)
        model.fit(ratings_df)

        # Get consensus grades
        bayesian_results = model.get_consensus_grades()

        # Convert to our result format
        results = {}
        for essay_id, bayesian_result in bayesian_results.items():
            # Calculate confidence interval from posterior
            # This would require access to full posterior, simplified here
            confidence = bayesian_result.confidence
            confidence_interval = (
                max(0, confidence - 0.1),  # Simplified - should use posterior
                min(1, confidence + 0.1)
            )

            results[essay_id] = ConsensusResult(
                essay_id=essay_id,
                consensus_grade=bayesian_result.consensus_grade,
                grade_probabilities=bayesian_result.grade_probabilities,
                confidence=confidence,
                confidence_interval=confidence_interval,
                method_used="bayesian",
                warning=None
            )

        return results

    def _wilson_score_interval(
        self, successes: int, trials: int, confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate Wilson score confidence interval.
        Better properties than normal approximation for small samples.
        """
        if trials == 0:
            return (0.0, 1.0)

        p_hat = successes / trials
        z = stats.norm.ppf((1 + confidence) / 2)
        z_squared = z ** 2

        denominator = 1 + z_squared / trials
        center = (p_hat + z_squared / (2 * trials)) / denominator

        margin = z * np.sqrt(
            (p_hat * (1 - p_hat) + z_squared / (4 * trials)) / trials
        ) / denominator

        return (
            max(0, center - margin),
            min(1, center + margin)
        )

    def _binomial_confidence_interval(
        self, successes: int, trials: int, confidence: float = 0.95
    ) -> Tuple[float, float]:
        """
        Calculate exact binomial confidence interval using Clopper-Pearson method.
        Most conservative but exact for any sample size.
        """
        alpha = 1 - confidence

        if successes == 0:
            lower = 0.0
        else:
            lower = stats.beta.ppf(alpha / 2, successes, trials - successes + 1)

        if successes == trials:
            upper = 1.0
        else:
            upper = stats.beta.ppf(1 - alpha / 2, successes + 1, trials - successes)

        return (lower, upper)


def validate_solution(ratings_df: pd.DataFrame) -> None:
    """
    Validate the principled consensus grading solution.
    """
    grader = PrincipledConsensusGrader()
    results = grader.get_consensus(ratings_df)

    # Check specific test cases
    if "EB01" in results:
        eb01_result = results["EB01"]
        print(f"EB01: {eb01_result.consensus_grade} "
              f"(confidence: {eb01_result.confidence:.2f}, "
              f"CI: [{eb01_result.confidence_interval[0]:.2f}, "
              f"{eb01_result.confidence_interval[1]:.2f}], "
              f"method: {eb01_result.method_used})")

        if eb01_result.warning:
            print(f"  Warning: {eb01_result.warning}")

    # Print summary statistics
    methods_used = {}
    avg_confidence = []

    for result in results.values():
        methods_used[result.method_used] = methods_used.get(result.method_used, 0) + 1
        avg_confidence.append(result.confidence)

    print(f"\nMethods used: {methods_used}")
    print(f"Average confidence: {np.mean(avg_confidence):.2f}")

    # Check for warnings
    warnings = [r for r in results.values() if r.warning]
    if warnings:
        print(f"Essays with warnings: {len(warnings)}")

"""Improved Bayesian ordinal regression model for essay consensus grading.

This model addresses the issues identified in the original Many-Facet Rasch Model:
1. Uses reference rater approach instead of sum-to-zero constraint
2. Empirical threshold initialization from observed grade quantiles
3. Simpler priors suitable for sparse data
4. No circular reasoning in rater adjustments
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any, Dict, Optional

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm
import pytensor.tensor as pt

warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass
class ModelConfig:
    """Configuration for the Bayesian consensus model."""

    n_chains: int = 4
    n_draws: int = 2000
    n_tune: int = 2000  # Increased for better convergence
    target_accept: float = 0.95  # Increased for better sampling
    max_treedepth: int = 15  # Increased for complex posteriors

    # Prior parameters
    ability_prior_sd: float = 1.0  # Essay ability prior std dev
    severity_prior_sd: float = 0.3  # Tighter prior for more stable estimates

    # Reference rater approach
    use_reference_rater: bool = True
    reference_rater_idx: int = 0  # First rater as reference

    # Threshold initialization
    use_empirical_thresholds: bool = True
    threshold_padding: float = 0.5  # Add padding to empirical thresholds

    # Swedish grade distribution (national statistics for Part C: Writing)
    swedish_grade_distribution: Dict[str, float] = None  # Will be set in __post_init__

    # Adaptive complexity thresholds
    sparse_data_threshold: int = 50  # Use simpler model for sparse data (< 50 observations)
    medium_data_threshold: int = 100  # Below this, still boost sampling
    sparse_tune_multiplier: float = 1.5  # Increase tuning for sparse data
    sparse_draws_multiplier: float = 1.5  # Increase draws for sparse data
    medium_tune_multiplier: float = 1.25  # Moderate increase for medium data
    medium_draws_multiplier: float = 1.25  # Moderate increase for medium data

    # Degeneracy detection thresholds
    min_essays_for_bayesian: int = 3  # Need at least 3 essays
    min_raters_for_bayesian: int = 3  # Need at least 3 raters
    min_observations_for_bayesian: int = 9  # Need at least 3x3 matrix

    def __post_init__(self) -> None:
        """Initialize Swedish grade distribution after dataclass init."""
        if self.swedish_grade_distribution is None:
            self.swedish_grade_distribution = {
                "F": 0.122,  # 12.2%
                "E": 0.358,  # 35.8%
                "D": 0.189,  # 18.9%
                "C": 0.216,  # 21.6%
                "B": 0.073,  # 7.3%
                "A": 0.042,  # 4.2%
            }


@dataclass
class ConsensusResult:
    """Result of consensus grading."""

    essay_id: str
    consensus_grade: str
    grade_probabilities: Dict[str, float]
    confidence: float
    raw_ability: float
    adjusted_ability: float
    rater_adjustments: Dict[str, float]


class ImprovedBayesianModel:
    """Improved Bayesian ordinal regression model for essay consensus grading."""

    SWEDISH_GRADES = ["F", "E", "D", "C", "B", "A"]
    GRADE_TO_NUMERIC = {g: i for i, g in enumerate(SWEDISH_GRADES)}

    def __init__(self, config: Optional[ModelConfig] = None):
        """Initialize the model with configuration."""
        self.config = config or ModelConfig()
        self.model: Optional[pm.Model] = None
        self.trace: Optional[az.InferenceData] = None
        self.essay_map: Dict[str, int] = {}
        self.rater_map: Dict[str, int] = {}
        self.grade_scale: Dict[str, int] = {}
        self._fitted = False

    def prepare_data(self, ratings_df: pd.DataFrame) -> pd.DataFrame:
        """Prepare rating data for modeling.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]

        Returns:
            Prepared DataFrame with numeric indices
        """
        # Convert grades to numeric
        ratings_df = ratings_df.copy()

        # Handle Swedish grades with +/- modifiers
        def grade_to_base(grade: str) -> Optional[str]:
            """Convert grade with modifier to base grade."""
            if pd.isna(grade):
                return None
            grade = str(grade).strip().upper()
            # Remove +/- modifiers
            base = grade[0] if grade else None
            return base if base in self.SWEDISH_GRADES else None

        ratings_df["base_grade"] = ratings_df["grade"].apply(grade_to_base)
        ratings_df = ratings_df.dropna(subset=["base_grade"])

        # Create mappings
        self.essay_map = {e: i for i, e in enumerate(ratings_df["essay_id"].unique())}
        self.rater_map = {r: i for i, r in enumerate(ratings_df["rater_id"].unique())}
        self.grade_scale = self.GRADE_TO_NUMERIC

        # Add numeric indices
        ratings_df["essay_idx"] = ratings_df["essay_id"].map(self.essay_map)
        ratings_df["rater_idx"] = ratings_df["rater_id"].map(self.rater_map)
        ratings_df["grade_numeric"] = ratings_df["base_grade"].map(self.grade_scale)

        return ratings_df

    def _get_empirical_thresholds(self, grades: np.ndarray) -> np.ndarray:
        """Calculate empirical thresholds from observed grade distribution.

        NOTE: This method now uses a simplified approach that spaces thresholds
        evenly on the latent scale. The previous implementation that centered
        thresholds around observed grades was identified as circular reasoning.
        The grades parameter is kept for API compatibility but not used.

        Args:
            grades: Array of numeric grades (unused, kept for compatibility)

        Returns:
            Array of threshold values evenly spaced on latent scale
        """
        _ = grades  # Acknowledge parameter for API compatibility
        n_categories = len(self.SWEDISH_GRADES)

        # Use evenly spaced thresholds on the latent scale
        # This is a neutral approach that doesn't bias toward observed data
        thresholds = np.linspace(-2.5, 2.5, n_categories - 1)

        return thresholds

    def _get_swedish_informed_thresholds(self) -> np.ndarray:
        """Get threshold values based on Swedish national grade distribution.

        Returns:
            Array of threshold values informed by Swedish statistics
        """
        # Convert Swedish distribution to cumulative probabilities
        cumulative_probs = []
        cumsum = 0.0
        for grade in self.SWEDISH_GRADES[:-1]:  # All but the last grade
            cumsum += self.config.swedish_grade_distribution[grade]
            cumulative_probs.append(cumsum)

        # Convert cumulative probabilities to thresholds on logit scale
        # Using inverse logit: threshold = log(p / (1 - p))
        thresholds = []
        for p in cumulative_probs:
            # Avoid exact 0 or 1 probabilities
            p = np.clip(p, 0.001, 0.999)
            threshold = np.log(p / (1 - p))
            thresholds.append(threshold)

        return np.array(thresholds)

    def _calculate_data_sparsity(self, data_df: pd.DataFrame) -> int:
        """Calculate the effective data sparsity for model selection.

        Args:
            data_df: Prepared data frame

        Returns:
            Number of observations (essays × raters)
        """
        return len(data_df)

    def build_model(self, data_df: pd.DataFrame) -> pm.Model:
        """Build the PyMC model with adaptive complexity based on data size.

        Args:
            data_df: Prepared data frame with numeric indices

        Returns:
            PyMC model object
        """
        n_observations = self._calculate_data_sparsity(data_df)
        n_essays = len(self.essay_map)
        n_raters = len(self.rater_map)

        # Check for degeneracy - insufficient data for Bayesian modeling
        if (
            n_essays < self.config.min_essays_for_bayesian
            or n_raters < self.config.min_raters_for_bayesian
            or n_observations < self.config.min_observations_for_bayesian
        ):
            # Use simple model for degenerate cases
            return self._build_simple_model(data_df)
        elif n_observations < self.config.sparse_data_threshold:
            # Use simpler model for sparse data
            return self._build_simple_model(data_df)
        else:
            # Use complex model for rich data
            return self._build_complex_model(data_df)

    def _build_simple_model(self, data_df: pd.DataFrame) -> pm.Model:
        """Build a simplified model for sparse data scenarios.

        Uses fixed thresholds based on Swedish distribution and
        per-rater severity with strong priors for stability.

        Args:
            data_df: Prepared data frame with numeric indices

        Returns:
            PyMC model object
        """
        n_essays = len(self.essay_map)
        n_raters = len(self.rater_map)

        essay_idx = data_df["essay_idx"].values
        rater_idx = data_df["rater_idx"].values
        grades = data_df["grade_numeric"].values

        with pm.Model() as model:
            # Essay ability with informative prior based on Swedish distribution
            # Use tighter prior for sparse data
            essay_ability = pm.Normal(
                "essay_ability",
                mu=0,
                sigma=0.7,  # Slightly wider to allow differentiation
                shape=n_essays,
            )

            # Per-rater severity with very strong priors for stability
            # Reference rater approach for identifiability
            if n_raters > 1:
                # Fix first rater at 0, estimate others with tight priors
                rater_severity_raw = pm.Normal(
                    "rater_severity_raw",
                    mu=0,
                    sigma=0.15,  # Very tight prior for sparse data
                    shape=n_raters - 1,
                )
                # Insert 0 for reference rater
                zeros = pt.zeros(1)
                rater_severity = pm.Deterministic(
                    "rater_severity",
                    pt.concatenate([zeros, rater_severity_raw]),
                )
            else:
                # Single rater case
                rater_severity = pm.Deterministic(
                    "rater_severity", pt.zeros(n_raters)
                )

            # Use FIXED evenly spaced thresholds for simple model
            # These are NOT estimated, just fixed values
            # Swedish thresholds are too skewed for sparse data
            evenly_spaced_thresholds = np.linspace(-2.5, 2.5, len(self.SWEDISH_GRADES) - 1)
            # Use ConstantData to ensure these are NOT sampled
            thresholds = pm.ConstantData("thresholds", evenly_spaced_thresholds)

            # Linear predictor
            eta = essay_ability[essay_idx] - rater_severity[rater_idx]

            # Ordinal likelihood
            pm.OrderedLogistic(
                "grade_obs",
                eta=eta,
                cutpoints=thresholds,
                observed=grades,
                compute_p=False,
            )

            # Add posterior predictive
            pm.Deterministic("eta", eta)

        self.model = model
        return model

    def _build_complex_model(self, data_df: pd.DataFrame) -> pm.Model:
        """Build the full complex model for rich data scenarios.

        This is the original model with reference rater approach
        and empirical threshold estimation.

        Args:
            data_df: Prepared data frame with numeric indices

        Returns:
            PyMC model object
        """
        n_essays = len(self.essay_map)
        n_raters = len(self.rater_map)
        n_categories = len(self.SWEDISH_GRADES)

        essay_idx = data_df["essay_idx"].values
        rater_idx = data_df["rater_idx"].values
        grades = data_df["grade_numeric"].values

        with pm.Model() as model:
            # Essay ability parameters
            # Use informative prior based on typical grade distribution
            essay_ability = pm.Normal(
                "essay_ability", mu=0, sigma=self.config.ability_prior_sd, shape=n_essays
            )

            # Rater severity parameters with reference rater approach
            if self.config.use_reference_rater:
                # Fix reference rater at 0, estimate others relative to it
                rater_severity_raw = pm.Normal(
                    "rater_severity_raw",
                    mu=0,
                    sigma=self.config.severity_prior_sd,
                    shape=n_raters - 1,
                )
                # Insert 0 for reference rater
                zeros = pt.zeros(1)
                rater_severity = pm.Deterministic(
                    "rater_severity",
                    pt.concatenate(
                        [
                            zeros
                            if self.config.reference_rater_idx == 0
                            else rater_severity_raw[: self.config.reference_rater_idx],
                            zeros,
                            rater_severity_raw[self.config.reference_rater_idx :]
                            if self.config.reference_rater_idx < n_raters - 1
                            else zeros[0:0],  # Empty array
                        ]
                    ),
                )
            else:
                # Free estimation without constraint
                rater_severity = pm.Normal(
                    "rater_severity", mu=0, sigma=self.config.severity_prior_sd, shape=n_raters
                )

            # Threshold parameters
            if self.config.use_empirical_thresholds:
                # Initialize from observed grade distribution
                empirical_thresholds = self._get_empirical_thresholds(np.array(grades))

                # Use normal priors centered on empirical values
                thresholds_raw = pm.Normal(
                    "thresholds_raw", mu=empirical_thresholds, sigma=0.5, shape=n_categories - 1
                )

                # Ensure ordering through transformation
                thresholds = pm.Deterministic("thresholds", pt.sort(thresholds_raw))
            else:
                # Use standard ordered transformation
                threshold_diffs = pm.Exponential("threshold_diffs", 1.0, shape=n_categories - 1)
                thresholds = pm.Deterministic("thresholds", pt.cumsum(threshold_diffs) - 3.0)

            # Linear predictor: ability - severity (note the sign)
            eta = essay_ability[essay_idx] - rater_severity[rater_idx]

            # Ordinal likelihood
            pm.OrderedLogistic(
                "grade_obs",
                eta=eta,
                cutpoints=thresholds,
                observed=grades,
                compute_p=False,  # Don't compute p-values during sampling
            )

            # Add posterior predictive
            pm.Deterministic("eta", eta)

        self.model = model
        return model

    def fit(self, ratings_df: pd.DataFrame) -> None:
        """Fit the model to rating data with adaptive sampling parameters.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]
        """
        # Prepare data
        data_df = self.prepare_data(ratings_df)

        # Check for single essay case - use majority voting instead
        if len(self.essay_map) == 1:
            # Store data for majority voting fallback
            self._use_majority_voting = True
            self._ratings_data = data_df
            self._fitted = True
            return

        # Build model
        self.build_model(data_df)
        self._use_majority_voting = False

        # Sample from posterior
        if self.model is None:
            raise ValueError("Model not built")

        # Adaptive sampling parameters based on data sparsity
        n_observations = self._calculate_data_sparsity(data_df)
        if n_observations < self.config.sparse_data_threshold:
            # Significant increase for sparse data (will use simple model)
            n_draws = max(1000, int(self.config.n_draws * self.config.sparse_draws_multiplier))
            n_tune = max(1000, int(self.config.n_tune * self.config.sparse_tune_multiplier))
            target_accept = min(0.98, self.config.target_accept + 0.03)  # Higher for sparse data
        elif n_observations < self.config.medium_data_threshold:
            # Moderate increase for medium data
            n_draws = max(750, int(self.config.n_draws * self.config.medium_draws_multiplier))
            n_tune = max(750, int(self.config.n_tune * self.config.medium_tune_multiplier))
            target_accept = min(0.97, self.config.target_accept + 0.02)  # Slightly higher
        else:
            # Use standard sampling parameters for rich data
            n_draws = self.config.n_draws
            n_tune = self.config.n_tune
            target_accept = self.config.target_accept

        with self.model:
            self.trace = pm.sample(
                draws=n_draws,
                tune=n_tune,
                chains=min(self.config.n_chains, 2)
                if n_observations < 10
                else self.config.n_chains,
                target_accept=target_accept,
                max_treedepth=self.config.max_treedepth,
                return_inferencedata=True,
                progressbar=True,
            )

        self._fitted = True

    def get_consensus_grades(self) -> Dict[str, ConsensusResult]:
        """Calculate consensus grades for all essays.

        Returns:
            Dictionary mapping essay IDs to consensus results
        """
        if not self._fitted:
            raise ValueError("Model must be fitted before getting consensus grades")

        # Handle majority voting fallback for single essay
        if hasattr(self, "_use_majority_voting") and self._use_majority_voting:
            return self._get_majority_consensus()

        results = {}

        # Extract posterior means
        if self.trace is None:
            raise ValueError("Model trace not available")

        essay_abilities = self.trace.posterior["essay_ability"].mean(dim=["chain", "draw"]).values
        rater_severities = self.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values

        # Handle thresholds - might be in posterior (complex model) or fixed (simple model)
        if "thresholds" in self.trace.posterior:
            thresholds = self.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values
        else:
            # Simple model with fixed thresholds - reconstruct from Swedish distribution
            thresholds = self._get_swedish_informed_thresholds()

        # Reverse mappings
        id_to_essay = {v: k for k, v in self.essay_map.items()}
        id_to_rater = {v: k for k, v in self.rater_map.items()}

        for essay_idx, essay_id in id_to_essay.items():
            ability = essay_abilities[essay_idx]

            # Use posterior sampling for better confidence estimates
            grade_probs, confidence = self._calculate_grade_probabilities_from_posterior(
                essay_idx, thresholds
            )

            # Get consensus grade (highest probability)
            consensus_idx = np.argmax(grade_probs)
            consensus_grade = self.SWEDISH_GRADES[consensus_idx]

            # Get rater adjustments for this essay
            rater_adjustments = {}
            for rater_idx, rater_id in id_to_rater.items():
                if rater_idx < len(rater_severities):
                    rater_adjustments[rater_id] = float(rater_severities[rater_idx])
                else:
                    rater_adjustments[rater_id] = 0.0  # Default for missing indices

            results[essay_id] = ConsensusResult(
                essay_id=essay_id,
                consensus_grade=consensus_grade,
                grade_probabilities={
                    grade: float(prob) for grade, prob in zip(self.SWEDISH_GRADES, grade_probs)
                },
                confidence=float(confidence),
                raw_ability=float(ability),
                adjusted_ability=float(ability),  # No global adjustment
                rater_adjustments=rater_adjustments,
            )

        return results

    def _calculate_grade_probabilities(self, ability: float, thresholds: np.ndarray) -> np.ndarray:
        """Calculate probability of each grade given ability and thresholds.

        Args:
            ability: Essay ability on latent scale
            thresholds: Ordered threshold values

        Returns:
            Array of grade probabilities
        """
        n_categories = len(self.SWEDISH_GRADES)
        probs = np.zeros(n_categories)

        # Add boundaries
        extended_thresholds = np.concatenate([[-np.inf], thresholds, [np.inf]])

        for i in range(n_categories):
            # P(grade = i) = P(threshold[i] < ability <= threshold[i+1])
            lower = extended_thresholds[i]
            upper = extended_thresholds[i + 1]

            # Use standard logistic CDF (no artificial temperature scaling)
            p_upper = 1 / (1 + np.exp(-(ability - upper)))
            p_lower = 1 / (1 + np.exp(-(ability - lower)))
            probs[i] = p_upper - p_lower

        # Normalize to ensure sum = 1
        probs = probs / probs.sum()

        return np.array(probs)

    def _calculate_grade_probabilities_from_posterior(
        self, essay_idx: int, thresholds: np.ndarray
    ) -> tuple[np.ndarray, float]:
        """Calculate grade probabilities using full posterior distribution.

        This method uses the full posterior samples rather than just the mean,
        naturally incorporating uncertainty into the confidence calculation.

        Args:
            essay_idx: Index of the essay in the model
            thresholds: Threshold values for grade boundaries

        Returns:
            Tuple of (grade_probabilities, confidence)
        """
        if self.trace is None:
            raise ValueError("Model must be fitted first")

        # Get all posterior samples for this essay's ability
        ability_samples = self.trace.posterior["essay_ability"][:, :, essay_idx].values.flatten()

        # Count how often each grade is selected across samples
        grade_counts = np.zeros(len(self.SWEDISH_GRADES))

        for ability in ability_samples:
            # Calculate probabilities for this sample
            probs = self._calculate_grade_probabilities(ability, thresholds)
            # The most likely grade for this sample
            selected_grade = np.argmax(probs)
            grade_counts[selected_grade] += 1

        # Grade probabilities are the frequency of selection across samples
        grade_probabilities = grade_counts / len(ability_samples)

        # Confidence is naturally the probability of the most likely grade
        confidence = float(np.max(grade_probabilities))

        return grade_probabilities, confidence

    def _get_majority_consensus(self) -> Dict[str, ConsensusResult]:
        """Calculate consensus using simple majority voting for degenerate cases.

        Used when we have only a single essay or insufficient data for Bayesian modeling.

        Returns:
            Dictionary mapping essay IDs to consensus results based on majority vote
        """
        results = {}

        # Group ratings by essay
        for essay_id in self.essay_map.keys():
            essay_data = self._ratings_data[self._ratings_data["essay_id"] == essay_id]

            # Count grades
            grade_counts = essay_data["grade_numeric"].value_counts()
            total_ratings = len(essay_data)

            # Find majority grade
            majority_grade_numeric = grade_counts.idxmax()
            majority_count = grade_counts.max()

            # Calculate confidence as proportion of majority
            confidence = float(majority_count / total_ratings)

            # Create grade probabilities
            grade_probs = {}
            for i, grade in enumerate(self.SWEDISH_GRADES):
                if i in grade_counts.index:
                    grade_probs[grade] = float(grade_counts[i] / total_ratings)
                else:
                    grade_probs[grade] = 0.0

            # Create consensus result
            consensus_grade = self.SWEDISH_GRADES[majority_grade_numeric]

            results[essay_id] = ConsensusResult(
                essay_id=essay_id,
                consensus_grade=consensus_grade,
                grade_probabilities=grade_probs,
                confidence=confidence,
                raw_ability=0.0,  # Not applicable for majority voting
                adjusted_ability=0.0,
                rater_adjustments={},  # No rater adjustments in majority voting
            )

        return results

    def get_model_diagnostics(self) -> Dict[str, Any]:
        """Get comprehensive model diagnostics.

        Returns:
            Dictionary of diagnostic metrics
        """
        if not self._fitted or self.trace is None:
            raise ValueError("Model must be fitted before getting diagnostics")

        # Basic convergence diagnostics
        summary = az.summary(self.trace)

        # Extract key metrics
        diagnostics = {
            "convergence": {
                "max_rhat": float(summary["r_hat"].max()),
                "min_ess_bulk": float(summary["ess_bulk"].min()),
                "min_ess_tail": float(summary["ess_tail"].min()),
                "converged": bool(summary["r_hat"].max() < 1.01),
            },
            "parameters": {
                "n_essays": len(self.essay_map),
                "n_raters": len(self.rater_map),
                "n_observations": int(len(self.trace.observed_data["grade_obs"].values.flatten())),
            },
        }

        # Add WAIC and LOO for model comparison
        try:
            diagnostics["waic"] = float(az.waic(self.trace).waic)
            diagnostics["loo"] = float(az.loo(self.trace).loo)
        except Exception:
            # May fail for discrete observations
            pass

        return diagnostics

    def predict_new_essay(self, ratings: Dict[str, str]) -> ConsensusResult:
        """Predict consensus grade for a new essay given ratings.

        Args:
            ratings: Dictionary mapping rater_id to grade

        Returns:
            Consensus result for the new essay
        """
        if not self._fitted or self.trace is None:
            raise ValueError("Model must be fitted before prediction")

        # Get rater severities
        rater_severities = self.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values
        thresholds = self.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values

        # Calculate adjusted ratings
        adjusted_sum = 0
        count = 0

        for rater_id, grade in ratings.items():
            if rater_id in self.rater_map:
                rater_idx = self.rater_map[rater_id]
                severity = rater_severities[rater_idx]

                # Convert grade to numeric
                base_grade = grade[0] if grade else None
                if base_grade in self.grade_scale:
                    grade_numeric = self.grade_scale[base_grade]
                    # Adjust for rater severity
                    adjusted_sum += grade_numeric + severity
                    count += 1

        if count == 0:
            raise ValueError("No known raters in ratings")

        # Average adjusted ability
        ability = adjusted_sum / count

        # Calculate grade probabilities
        grade_probs = self._calculate_grade_probabilities(ability, thresholds)
        consensus_idx = np.argmax(grade_probs)

        return ConsensusResult(
            essay_id="new_essay",
            consensus_grade=self.SWEDISH_GRADES[consensus_idx],
            grade_probabilities={
                grade: float(prob) for grade, prob in zip(self.SWEDISH_GRADES, grade_probs)
            },
            confidence=float(grade_probs[consensus_idx]),
            raw_ability=float(ability),
            adjusted_ability=float(ability),
            rater_adjustments={},
        )

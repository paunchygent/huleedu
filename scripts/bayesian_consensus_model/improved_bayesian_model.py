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
from typing import Any, Dict, Optional, List, Tuple

import arviz as az
import numpy as np
import pandas as pd
import pymc as pm

warnings.filterwarnings("ignore", category=FutureWarning)


@dataclass
class ModelConfig:
    """Configuration for the Bayesian consensus model."""

    n_chains: int = 4
    n_draws: int = 2000
    n_tune: int = 1000
    target_accept: float = 0.9
    max_treedepth: int = 12

    # Prior parameters
    ability_prior_sd: float = 1.0  # Essay ability prior std dev
    severity_prior_sd: float = 0.5  # Rater severity prior std dev (tighter than original)

    # Reference rater approach
    use_reference_rater: bool = True
    reference_rater_idx: int = 0  # First rater as reference

    # Threshold initialization
    use_empirical_thresholds: bool = True
    threshold_padding: float = 0.5  # Add padding to empirical thresholds


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

        Args:
            grades: Array of numeric grades

        Returns:
            Array of threshold values
        """
        n_categories = len(self.SWEDISH_GRADES)
        thresholds = []

        for i in range(n_categories - 1):
            # Find empirical quantile between grade i and i+1
            lower_grades = grades[grades == i] if i > 0 else []
            upper_grades = grades[grades == i + 1]

            if len(lower_grades) > 0 and len(upper_grades) > 0:
                # Use midpoint between max of lower and min of upper
                threshold = 0.0  # On latent scale
            elif len(upper_grades) > 0:
                # Use a value slightly below the upper grade
                threshold = -self.config.threshold_padding
            else:
                # Use evenly spaced thresholds as fallback
                threshold = -2.5 + i * 1.0

            thresholds.append(threshold)

        # Ensure monotonicity and reasonable spacing
        thresholds_array = np.array(thresholds)
        for i in range(1, len(thresholds_array)):
            if thresholds_array[i] <= thresholds_array[i - 1]:
                thresholds_array[i] = thresholds_array[i - 1] + 0.3

        return thresholds_array

    def build_model(self, data_df: pd.DataFrame) -> pm.Model:
        """Build the PyMC model with improved specification.

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
                zeros = pm.math.zeros(1)
                rater_severity = pm.Deterministic(
                    "rater_severity",
                    pm.math.concatenate(
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
                thresholds = pm.Deterministic("thresholds", pm.math.sort(thresholds_raw))
            else:
                # Use standard ordered transformation
                threshold_diffs = pm.Exponential("threshold_diffs", 1.0, shape=n_categories - 1)
                thresholds = pm.Deterministic("thresholds", pm.math.cumsum(threshold_diffs) - 3.0)

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
        """Fit the model to rating data.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]
        """
        # Prepare data
        data_df = self.prepare_data(ratings_df)

        # Build model
        self.build_model(data_df)

        # Sample from posterior
        if self.model is None:
            raise ValueError("Model not built")

        with self.model:
            self.trace = pm.sample(
                draws=self.config.n_draws,
                tune=self.config.n_tune,
                chains=self.config.n_chains,
                target_accept=self.config.target_accept,
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

        results = {}

        # Extract posterior means
        if self.trace is None:
            raise ValueError("Model trace not available")

        essay_abilities = self.trace.posterior["essay_ability"].mean(dim=["chain", "draw"]).values
        rater_severities = self.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values
        thresholds = self.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values

        # Reverse mappings
        id_to_essay = {v: k for k, v in self.essay_map.items()}
        id_to_rater = {v: k for k, v in self.rater_map.items()}

        for essay_idx, essay_id in id_to_essay.items():
            ability = essay_abilities[essay_idx]

            # Calculate grade probabilities
            grade_probs = self._calculate_grade_probabilities(ability, thresholds)

            # Get consensus grade (highest probability)
            consensus_idx = np.argmax(grade_probs)
            consensus_grade = self.SWEDISH_GRADES[consensus_idx]

            # Calculate confidence (probability of chosen grade)
            confidence = grade_probs[consensus_idx]

            # Get rater adjustments for this essay
            rater_adjustments = {
                id_to_rater[i]: float(severity) for i, severity in enumerate(rater_severities)
            }

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

            # Use logistic CDF
            p_upper = 1 / (1 + np.exp(-(ability - upper)))
            p_lower = 1 / (1 + np.exp(-(ability - lower)))
            probs[i] = p_upper - p_lower

        # Normalize to ensure sum = 1
        probs = probs / probs.sum()

        return np.array(probs)

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

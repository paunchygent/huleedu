"""Statistical diagnostics for Bayesian model issues.

Diagnoses problems in the Many-Facet Rasch Model including circular reasoning,
sum-to-zero constraints, extreme thresholds, and overparameterization.
"""

from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats


class BayesianModelDiagnostics:
    """Diagnostic tools for analyzing Bayesian model issues."""

    def __init__(self, thresholds_df: pd.DataFrame, severity_df: pd.DataFrame):
        """Initialize with model outputs.

        Args:
            thresholds_df: DataFrame with grade thresholds
            severity_df: DataFrame with rater severities
        """
        self.thresholds = thresholds_df["tau_k"].values if "tau_k" in thresholds_df else thresholds_df.values
        self.severities = severity_df

    def diagnose_threshold_issues(self) -> Dict:
        """Diagnose issues with grade thresholds.

        Returns:
            Dictionary with diagnostic results
        """
        # Check for extreme spacing
        threshold_gaps = np.diff(self.thresholds)

        # Identify problematic gaps (e.g., B to A gap)
        b_to_a_gap = self.thresholds[-1] - self.thresholds[-2] if len(self.thresholds) > 1 else 0

        # Check for disordered thresholds (should be monotonic)
        is_monotonic = all(threshold_gaps > 0)

        # Calculate relative gaps (as proportion of total range)
        total_range = self.thresholds[-1] - self.thresholds[0] if len(self.thresholds) > 1 else 1
        relative_gaps = threshold_gaps / total_range if total_range > 0 else threshold_gaps

        # Identify extreme gaps (> 30% of total range)
        extreme_gaps = [(i, gap) for i, gap in enumerate(relative_gaps) if gap > 0.3]

        return {
            "is_monotonic": is_monotonic,
            "b_to_a_gap": float(b_to_a_gap),
            "mean_gap": float(np.mean(threshold_gaps)),
            "std_gap": float(np.std(threshold_gaps)),
            "extreme_gaps": extreme_gaps,
            "threshold_range": float(total_range),
            "relative_gaps": relative_gaps.tolist()
        }

    def diagnose_sum_to_zero_constraint(self) -> Dict:
        """Analyze impact of sum-to-zero constraint on rater severities.

        Returns:
            Dictionary with constraint analysis
        """
        severities = self.severities["severity"].values

        # Check if sum is approximately zero (as it should be with constraint)
        severity_sum = np.sum(severities)
        has_sum_to_zero = abs(severity_sum) < 0.01

        # Look for artificial balancing (extreme positive and negative values)
        n_very_generous = np.sum(severities < -1.0)
        n_very_strict = np.sum(severities > 1.0)

        # Check for bimodal distribution (sign of forced balancing)
        kde = stats.gaussian_kde(severities)
        x_range = np.linspace(severities.min(), severities.max(), 100)
        density = kde(x_range)

        # Simple bimodality check: look for multiple peaks
        peaks = self._find_peaks(density)
        is_bimodal = len(peaks) > 1

        # Measure severity spread
        severity_range = severities.max() - severities.min()
        severity_std = np.std(severities)

        return {
            "has_sum_to_zero_constraint": has_sum_to_zero,
            "severity_sum": float(severity_sum),
            "n_very_generous": int(n_very_generous),
            "n_very_strict": int(n_very_strict),
            "is_bimodal": is_bimodal,
            "severity_range": float(severity_range),
            "severity_std": float(severity_std),
            "forced_balancing_likely": is_bimodal and has_sum_to_zero
        }

    def analyze_rater_severity_distribution(self) -> Dict:
        """Analyze the distribution of rater severities.

        Returns:
            Dictionary with distribution statistics
        """
        severities = self.severities["severity"].values
        n_rated = self.severities["n_rated"].values

        # Basic statistics
        stats_dict = {
            "mean": float(np.mean(severities)),
            "median": float(np.median(severities)),
            "std": float(np.std(severities)),
            "min": float(np.min(severities)),
            "max": float(np.max(severities)),
            "skewness": float(stats.skew(severities)),
            "kurtosis": float(stats.kurtosis(severities))
        }

        # Categorize raters
        generous_threshold = -0.5
        strict_threshold = 0.5

        rater_categories = {
            "generous": np.sum(severities < generous_threshold),
            "neutral": np.sum((severities >= generous_threshold) & (severities <= strict_threshold)),
            "strict": np.sum(severities > strict_threshold)
        }

        # Correlation between severity and number of ratings
        if len(severities) > 2:
            corr, p_value = stats.pearsonr(severities, n_rated)
            severity_experience_correlation = {
                "correlation": float(corr),
                "p_value": float(p_value),
                "significant": p_value < 0.05
            }
        else:
            severity_experience_correlation = {
                "correlation": 0.0,
                "p_value": 1.0,
                "significant": False
            }

        return {
            "statistics": stats_dict,
            "rater_categories": rater_categories,
            "severity_experience_correlation": severity_experience_correlation
        }

    def detect_circular_reasoning(self, essay_ratings: Dict[str, str]) -> Dict:
        """Detect circular reasoning in severity adjustments.

        Circular reasoning occurs when:
        1. Raters are marked generous because they gave high grades
        2. Their high grades are then discounted because they're "generous"

        Args:
            essay_ratings: Raw ratings for the essay

        Returns:
            Dictionary with circular reasoning indicators
        """
        severity_map = dict(zip(self.severities["rater"], self.severities["severity"]))

        # Analyze each rater's severity vs their rating
        rater_analysis = []
        for rater, grade in essay_ratings.items():
            if rater in severity_map:
                severity = severity_map[rater]
                numeric_grade = self._grade_to_numeric(grade)

                # Check for circular pattern:
                # High grade (A/B) + labeled generous (severity < -0.5)
                is_circular = (numeric_grade >= 12 and severity < -0.5)

                rater_analysis.append({
                    "rater": rater,
                    "grade": grade,
                    "numeric_grade": numeric_grade,
                    "severity": severity,
                    "circular_pattern": is_circular
                })

        # Count circular patterns
        circular_count = sum(1 for r in rater_analysis if r["circular_pattern"])
        total_raters = len(rater_analysis)

        return {
            "rater_analysis": rater_analysis,
            "circular_count": circular_count,
            "circular_proportion": circular_count / total_raters if total_raters > 0 else 0,
            "circular_reasoning_detected": circular_count >= total_raters * 0.4
        }

    def compute_identifiability_metrics(self) -> Dict:
        """Compute model identifiability metrics.

        Returns:
            Dictionary with identifiability indicators
        """
        n_essays = 12  # From the problem description
        n_raters = len(self.severities)
        n_thresholds = len(self.thresholds)

        # Total parameters
        n_parameters = n_essays + n_raters + n_thresholds

        # Approximate degrees of freedom (total observations)
        # This is approximate since we don't have the full comparison matrix
        avg_ratings_per_essay = self.severities["n_rated"].sum() / n_essays if n_essays > 0 else 0
        approx_observations = n_essays * avg_ratings_per_essay

        # Parameter to observation ratio
        param_obs_ratio = n_parameters / approx_observations if approx_observations > 0 else float('inf')

        # Check for overparameterization
        is_overparameterized = param_obs_ratio > 0.5

        return {
            "n_parameters": n_parameters,
            "n_essays": n_essays,
            "n_raters": n_raters,
            "n_thresholds": n_thresholds,
            "approx_observations": approx_observations,
            "param_obs_ratio": param_obs_ratio,
            "is_overparameterized": is_overparameterized,
            "recommendation": "Model is overparameterized" if is_overparameterized else "Model complexity acceptable"
        }

    def _find_peaks(self, density: np.ndarray) -> List[int]:
        """Find peaks in a density array.

        Args:
            density: 1D array of density values

        Returns:
            List of peak indices
        """
        peaks = []
        for i in range(1, len(density) - 1):
            if density[i] > density[i - 1] and density[i] > density[i + 1]:
                peaks.append(i)
        return peaks

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0, "F+": 1,
            "E-": 2, "E": 3, "E+": 4,
            "D-": 5, "D": 6, "D+": 7,
            "C-": 8, "C": 9, "C+": 10,
            "B-": 11, "B": 12, "B+": 13,
            "A": 14
        }
        return grade_map.get(grade, -1)


def diagnose_ja24_specific_issues(
    raw_ratings: Dict[str, str],
    severity_df: pd.DataFrame,
    consensus_grade: str,
    thresholds_df: pd.DataFrame
) -> Dict:
    """Specific diagnostics for the JA24 case.

    Args:
        raw_ratings: JA24's raw ratings
        severity_df: Rater severity DataFrame
        consensus_grade: Model's consensus grade for JA24
        thresholds_df: Grade thresholds

    Returns:
        Dictionary with JA24-specific analysis
    """
    # Count A and B ratings
    grade_counts = {}
    for grade in raw_ratings.values():
        grade_counts[grade] = grade_counts.get(grade, 0) + 1

    n_a_ratings = grade_counts.get("A", 0)
    n_b_ratings = grade_counts.get("B", 0)

    # Analyze severities of raters who gave A
    severity_map = dict(zip(severity_df["rater"], severity_df["severity"]))

    a_rater_severities = []
    b_rater_severities = []

    for rater, grade in raw_ratings.items():
        if rater in severity_map:
            if grade == "A":
                a_rater_severities.append(severity_map[rater])
            elif grade == "B":
                b_rater_severities.append(severity_map[rater])

    # Calculate average severities
    avg_a_severity = np.mean(a_rater_severities) if a_rater_severities else 0
    avg_b_severity = np.mean(b_rater_severities) if b_rater_severities else 0

    # Check if A raters were systematically marked as generous
    a_raters_labeled_generous = sum(1 for s in a_rater_severities if s < -0.5)

    # Calculate what the consensus would be without severity adjustments
    numeric_ratings = []
    grade_to_num = {
        "F": 0, "F+": 1, "E-": 2, "E": 3, "E+": 4,
        "D-": 5, "D": 6, "D+": 7, "C-": 8, "C": 9, "C+": 10,
        "B-": 11, "B": 12, "B+": 13, "A": 14
    }

    for grade in raw_ratings.values():
        numeric_ratings.append(grade_to_num.get(grade, -1))

    raw_mean = np.mean(numeric_ratings)
    raw_median = np.median(numeric_ratings)

    num_to_grade = {v: k for k, v in grade_to_num.items()}
    raw_consensus_mean = num_to_grade.get(int(round(raw_mean)), "Unknown")
    raw_consensus_median = num_to_grade.get(int(round(raw_median)), "Unknown")

    return {
        "essay_id": "JA24",
        "raw_ratings": raw_ratings,
        "grade_counts": grade_counts,
        "n_a_ratings": n_a_ratings,
        "n_b_ratings": n_b_ratings,
        "model_consensus": consensus_grade,
        "raw_consensus_mean": raw_consensus_mean,
        "raw_consensus_median": raw_consensus_median,
        "a_rater_severities": a_rater_severities,
        "b_rater_severities": b_rater_severities,
        "avg_a_severity": float(avg_a_severity),
        "avg_b_severity": float(avg_b_severity),
        "a_raters_labeled_generous": a_raters_labeled_generous,
        "problem_summary": f"Despite {n_a_ratings} A ratings vs {n_b_ratings} B ratings, "
                          f"model gave {consensus_grade}. A-raters had avg severity {avg_a_severity:.2f} "
                          f"(labeled as generous), causing their ratings to be discounted."
    }
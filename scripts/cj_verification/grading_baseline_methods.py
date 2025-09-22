"""Baseline grading aggregation methods.

Simple consensus methods (majority vote, weighted median, trimmed mean) for
comparing against complex Bayesian model results.
"""

from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


class ConsensusMethod:
    """Base class for consensus methods."""

    def compute_consensus(self, ratings: Dict[str, str], **kwargs) -> Tuple[str, float, Dict]:
        """Compute consensus grade from ratings.

        Args:
            ratings: Dictionary mapping rater to grade
            **kwargs: Method-specific parameters

        Returns:
            Tuple of (consensus_grade, confidence_score, details_dict)
        """
        raise NotImplementedError


class SimpleMajorityVote(ConsensusMethod):
    """Simple majority vote - baseline method."""

    def compute_consensus(
        self, ratings: Dict[str, str], grade_map: Optional[Dict] = None
    ) -> Tuple[str, float, Dict]:
        """Compute consensus using simple majority vote.

        Args:
            ratings: Dictionary mapping rater to grade
            grade_map: Optional custom grade to numeric mapping

        Returns:
            Tuple of (consensus_grade, confidence_score, details)
        """
        if not ratings:
            raise ValueError("No ratings provided")

        # Count occurrences of each grade
        grade_counts = {}
        for grade in ratings.values():
            grade_counts[grade] = grade_counts.get(grade, 0) + 1

        # Find grade with most votes
        max_count = max(grade_counts.values())
        modal_grades = [g for g, c in grade_counts.items() if c == max_count]

        # If tie, take the higher grade (more generous)
        if len(modal_grades) > 1:
            modal_grades.sort(key=lambda x: self._grade_to_numeric(x), reverse=True)

        consensus_grade = modal_grades[0]

        # Confidence based on agreement proportion
        total_ratings = len(ratings)
        confidence = max_count / total_ratings

        details = {
            "grade_counts": grade_counts,
            "total_ratings": total_ratings,
            "majority_count": max_count,
            "tied": len(modal_grades) > 1,
        }

        return consensus_grade, confidence, details

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0,
            "F+": 1,
            "E-": 2,
            "E": 3,
            "E+": 4,
            "D-": 5,
            "D": 6,
            "D+": 7,
            "C-": 8,
            "C": 9,
            "C+": 10,
            "B-": 11,
            "B": 12,
            "B+": 13,
            "A": 14,
        }
        return grade_map.get(grade, -1)


class WeightedMedianConsensus(ConsensusMethod):
    """Weighted median consensus - robust to outliers."""

    def compute_consensus(
        self, ratings: Dict[str, str], rater_weights: Optional[Dict[str, float]] = None
    ) -> Tuple[str, float, Dict]:
        """Compute consensus using weighted median.

        Args:
            ratings: Dictionary mapping rater to grade
            rater_weights: Optional dictionary of rater weights (e.g., based on experience)

        Returns:
            Tuple of (consensus_grade, confidence_score, details)
        """
        if not ratings:
            raise ValueError("No ratings provided")

        # Convert grades to numeric values
        numeric_ratings = []
        weights = []

        for rater, grade in ratings.items():
            numeric_value = self._grade_to_numeric(grade)
            numeric_ratings.append(numeric_value)

            if rater_weights:
                weights.append(rater_weights.get(rater, 1.0))
            else:
                weights.append(1.0)

        # Normalize weights
        weights = np.array(weights)
        weights = weights / weights.sum()

        # Compute weighted median
        sorted_indices = np.argsort(numeric_ratings)
        sorted_values = np.array(numeric_ratings)[sorted_indices]
        sorted_weights = weights[sorted_indices]

        cumsum = np.cumsum(sorted_weights)
        median_idx = np.searchsorted(cumsum, 0.5)

        weighted_median = sorted_values[median_idx]
        consensus_grade = self._numeric_to_grade(weighted_median)

        # Compute confidence based on concentration around median
        deviations = np.abs(np.array(numeric_ratings) - weighted_median)
        weighted_mad = np.sum(weights * deviations)  # Weighted Mean Absolute Deviation
        # Convert MAD to confidence (lower MAD = higher confidence)
        confidence = 1.0 / (1.0 + weighted_mad)

        details = {
            "numeric_ratings": numeric_ratings,
            "weights": weights.tolist(),
            "weighted_median_numeric": float(weighted_median),
            "weighted_mad": float(weighted_mad),
        }

        return consensus_grade, confidence, details

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0,
            "F+": 1,
            "E-": 2,
            "E": 3,
            "E+": 4,
            "D-": 5,
            "D": 6,
            "D+": 7,
            "C-": 8,
            "C": 9,
            "C+": 10,
            "B-": 11,
            "B": 12,
            "B+": 13,
            "A": 14,
        }
        return grade_map.get(grade, -1)

    def _numeric_to_grade(self, numeric: float) -> str:
        """Convert numeric value to grade."""
        grade_map = {
            0: "F",
            1: "F+",
            2: "E-",
            3: "E",
            4: "E+",
            5: "D-",
            6: "D",
            7: "D+",
            8: "C-",
            9: "C",
            10: "C+",
            11: "B-",
            12: "B",
            13: "B+",
            14: "A",
        }
        rounded = int(round(numeric))
        rounded = max(0, min(14, rounded))
        return grade_map[rounded]


class TrimmedMeanConsensus(ConsensusMethod):
    """Trimmed mean consensus - removes extremes."""

    def __init__(self, trim_proportion: float = 0.2):
        """Initialize with trim proportion.

        Args:
            trim_proportion: Proportion to trim from each end (0.2 = 20%)
        """
        self.trim_proportion = trim_proportion

    def compute_consensus(self, ratings: Dict[str, str], **kwargs) -> Tuple[str, float, Dict]:
        """Compute consensus using trimmed mean.

        Args:
            ratings: Dictionary mapping rater to grade

        Returns:
            Tuple of (consensus_grade, confidence_score, details)
        """
        if not ratings:
            raise ValueError("No ratings provided")

        # Convert to numeric
        numeric_ratings = [self._grade_to_numeric(g) for g in ratings.values()]

        # Need at least 3 ratings for trimmed mean to make sense
        if len(numeric_ratings) < 3:
            # Fall back to regular mean
            mean_value = np.mean(numeric_ratings)
            consensus_grade = self._numeric_to_grade(mean_value)
            confidence = 1.0 / (1.0 + np.std(numeric_ratings))

            return (
                consensus_grade,
                confidence,
                {
                    "method": "mean (too few ratings for trimming)",
                    "numeric_mean": float(mean_value),
                    "n_ratings": len(numeric_ratings),
                },
            )

        # Compute trimmed mean
        trimmed_mean = stats.trim_mean(numeric_ratings, self.trim_proportion)
        consensus_grade = self._numeric_to_grade(trimmed_mean)

        # Identify trimmed values
        sorted_ratings = sorted(numeric_ratings)
        n_trim = int(len(sorted_ratings) * self.trim_proportion)

        if n_trim > 0:
            trimmed_low = sorted_ratings[:n_trim]
            trimmed_high = sorted_ratings[-n_trim:] if n_trim > 0 else []
            kept_ratings = sorted_ratings[n_trim:-n_trim] if n_trim > 0 else sorted_ratings
        else:
            trimmed_low = []
            trimmed_high = []
            kept_ratings = sorted_ratings

        # Confidence based on variance of kept ratings
        if len(kept_ratings) > 1:
            kept_std = np.std(kept_ratings)
            confidence = 1.0 / (1.0 + kept_std)
        else:
            confidence = 1.0

        details = {
            "trimmed_mean_numeric": float(trimmed_mean),
            "trim_proportion": self.trim_proportion,
            "n_trimmed_each_end": n_trim,
            "trimmed_low": [self._numeric_to_grade(x) for x in trimmed_low],
            "trimmed_high": [self._numeric_to_grade(x) for x in trimmed_high],
            "kept_ratings": [self._numeric_to_grade(x) for x in kept_ratings],
        }

        return consensus_grade, confidence, details

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0,
            "F+": 1,
            "E-": 2,
            "E": 3,
            "E+": 4,
            "D-": 5,
            "D": 6,
            "D+": 7,
            "C-": 8,
            "C": 9,
            "C+": 10,
            "B-": 11,
            "B": 12,
            "B+": 13,
            "A": 14,
        }
        return grade_map.get(grade, -1)

    def _numeric_to_grade(self, numeric: float) -> str:
        """Convert numeric value to grade."""
        grade_map = {
            0: "F",
            1: "F+",
            2: "E-",
            3: "E",
            4: "E+",
            5: "D-",
            6: "D",
            7: "D+",
            8: "C-",
            9: "C",
            10: "C+",
            11: "B-",
            12: "B",
            13: "B+",
            14: "A",
        }
        rounded = int(round(numeric))
        rounded = max(0, min(14, rounded))
        return grade_map[rounded]


class RaterAdjustedConsensus(ConsensusMethod):
    """Consensus with simple rater adjustments (not Bayesian)."""

    def compute_consensus(
        self, ratings: Dict[str, str], rater_severities: Optional[Dict[str, float]] = None
    ) -> Tuple[str, float, Dict]:
        """Compute consensus with rater severity adjustments.

        This is a simpler version of what the Bayesian model does,
        but with transparent adjustments.

        Args:
            ratings: Dictionary mapping rater to grade
            rater_severities: Optional severity scores (-ve = generous, +ve = strict)

        Returns:
            Tuple of (consensus_grade, confidence_score, details)
        """
        if not ratings:
            raise ValueError("No ratings provided")

        # Convert to numeric and apply adjustments
        adjusted_ratings = []
        raw_ratings = []

        for rater, grade in ratings.items():
            numeric_value = self._grade_to_numeric(grade)
            raw_ratings.append(numeric_value)

            if rater_severities and rater in rater_severities:
                # Apply adjustment: generous raters get positive adjustment,
                # strict raters get negative adjustment (opposite of severity)
                adjustment = -rater_severities[rater] * 0.5  # Scale down adjustment
                adjusted_value = numeric_value + adjustment
            else:
                adjusted_value = numeric_value

            adjusted_ratings.append(adjusted_value)

        # Compute mean of adjusted ratings
        adjusted_mean = np.mean(adjusted_ratings)
        raw_mean = np.mean(raw_ratings)

        consensus_grade = self._numeric_to_grade(adjusted_mean)
        raw_consensus = self._numeric_to_grade(raw_mean)

        # Confidence based on agreement after adjustment
        adjusted_std = np.std(adjusted_ratings)
        confidence = 1.0 / (1.0 + adjusted_std)

        details = {
            "raw_mean_numeric": float(raw_mean),
            "adjusted_mean_numeric": float(adjusted_mean),
            "raw_consensus_grade": raw_consensus,
            "adjustment_impact": float(adjusted_mean - raw_mean),
            "adjusted_ratings": adjusted_ratings,
            "raw_ratings": raw_ratings,
        }

        return consensus_grade, confidence, details

    def _grade_to_numeric(self, grade: str) -> float:
        """Convert grade to numeric value."""
        grade_map = {
            "F": 0,
            "F+": 1,
            "E-": 2,
            "E": 3,
            "E+": 4,
            "D-": 5,
            "D": 6,
            "D+": 7,
            "C-": 8,
            "C": 9,
            "C+": 10,
            "B-": 11,
            "B": 12,
            "B+": 13,
            "A": 14,
        }
        return grade_map.get(grade, -1)

    def _numeric_to_grade(self, numeric: float) -> str:
        """Convert numeric value to grade."""
        grade_map = {
            0: "F",
            1: "F+",
            2: "E-",
            3: "E",
            4: "E+",
            5: "D-",
            6: "D",
            7: "D+",
            8: "C-",
            9: "C",
            10: "C+",
            11: "B-",
            12: "B",
            13: "B+",
            14: "A",
        }
        rounded = int(round(numeric))
        rounded = max(0, min(14, rounded))
        return grade_map[rounded]


def compare_all_methods(
    ratings: Dict[str, str],
    rater_severities: Optional[Dict[str, float]] = None,
    rater_weights: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """Compare all consensus methods on the same ratings.

    Args:
        ratings: Dictionary mapping rater to grade
        rater_severities: Optional severity scores for adjustment method
        rater_weights: Optional weights for weighted median

    Returns:
        DataFrame comparing all methods
    """
    methods = {
        "Simple Majority": SimpleMajorityVote(),
        "Weighted Median": WeightedMedianConsensus(),
        "Trimmed Mean (20%)": TrimmedMeanConsensus(0.2),
        "Rater Adjusted": RaterAdjustedConsensus(),
    }

    results = []

    for method_name, method in methods.items():
        try:
            if method_name == "Weighted Median" and rater_weights:
                grade, confidence, details = method.compute_consensus(
                    ratings, rater_weights=rater_weights
                )
            elif method_name == "Rater Adjusted" and rater_severities:
                grade, confidence, details = method.compute_consensus(
                    ratings, rater_severities=rater_severities
                )
            else:
                grade, confidence, details = method.compute_consensus(ratings)

            results.append(
                {
                    "Method": method_name,
                    "Consensus Grade": grade,
                    "Confidence": round(confidence, 3),
                    "Details": details,
                }
            )
        except Exception as e:
            results.append(
                {
                    "Method": method_name,
                    "Consensus Grade": "ERROR",
                    "Confidence": 0.0,
                    "Details": {"error": str(e)},
                }
            )

    return pd.DataFrame(results)

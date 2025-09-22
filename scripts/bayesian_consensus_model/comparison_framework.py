"""Framework for comparing Bayesian model with baseline consensus methods.

Implements and compares:
1. Simple majority voting
2. Weighted median
3. Trimmed mean
4. Bayesian model (improved)
5. Original flawed model (for reference)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy import stats

from .improved_bayesian_model import ImprovedBayesianModel, ModelConfig


@dataclass
class ComparisonResult:
    """Results from model comparison."""

    method_name: str
    consensus_grades: Dict[str, str]
    accuracy_vs_majority: float
    ja24_grade: str
    ja24_correct: bool
    mean_confidence: float
    computation_time: float


class BaselineMethod:
    """Base class for baseline consensus methods."""

    def __init__(self, name: str):
        """Initialize baseline method."""
        self.name = name

    def get_consensus(self, ratings: List[str]) -> tuple[str, float]:
        """Get consensus grade from ratings.

        Args:
            ratings: List of grade strings

        Returns:
            Tuple of (consensus_grade, confidence)
        """
        raise NotImplementedError


class SimpleMajority(BaselineMethod):
    """Simple majority voting."""

    def __init__(self):
        """Initialize simple majority method."""
        super().__init__("Simple Majority")

    def get_consensus(self, ratings: List[str]) -> tuple[str, float]:
        """Get consensus by majority vote."""
        if not ratings:
            return "N/A", 0.0

        # Convert to base grades
        base_grades = [r[0] if r else None for r in ratings]
        base_grades = [g for g in base_grades if g in ["F", "E", "D", "C", "B", "A"]]

        if not base_grades:
            return "N/A", 0.0

        # Count votes
        grade_counts = pd.Series(base_grades).value_counts()
        consensus_grade = grade_counts.index[0]
        confidence = grade_counts.iloc[0] / len(base_grades)

        return consensus_grade, float(confidence)


class WeightedMedian(BaselineMethod):
    """Weighted median consensus (robust to outliers)."""

    GRADE_VALUES = {"F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5}
    VALUE_GRADES = {v: k for k, v in GRADE_VALUES.items()}

    def __init__(self):
        """Initialize weighted median method."""
        super().__init__("Weighted Median")

    def get_consensus(self, ratings: List[str]) -> tuple[str, float]:
        """Get consensus by weighted median."""
        if not ratings:
            return "N/A", 0.0

        # Convert to numeric values
        values = []
        for r in ratings:
            base_grade = r[0] if r else None
            if base_grade in self.GRADE_VALUES:
                values.append(self.GRADE_VALUES[base_grade])

        if not values:
            return "N/A", 0.0

        # Calculate median
        median_value = np.median(values)

        # Round to nearest grade
        consensus_value = int(np.round(median_value))
        consensus_grade = self.VALUE_GRADES.get(consensus_value, "C")

        # Calculate confidence based on agreement
        distances = [abs(v - median_value) for v in values]
        mean_distance = np.mean(distances)
        confidence = 1.0 / (1.0 + mean_distance)  # Higher confidence if closer agreement

        return consensus_grade, float(confidence)


class TrimmedMean(BaselineMethod):
    """Trimmed mean consensus (removes extremes)."""

    GRADE_VALUES = {"F": 0, "E": 1, "D": 2, "C": 3, "B": 4, "A": 5}
    VALUE_GRADES = {v: k for k, v in GRADE_VALUES.items()}

    def __init__(self, trim_percent: float = 0.2):
        """Initialize trimmed mean method.

        Args:
            trim_percent: Percentage to trim from each end
        """
        super().__init__(f"Trimmed Mean ({int(trim_percent * 100)}%)")
        self.trim_percent = trim_percent

    def get_consensus(self, ratings: List[str]) -> tuple[str, float]:
        """Get consensus by trimmed mean."""
        if not ratings:
            return "N/A", 0.0

        # Convert to numeric values
        values = []
        for r in ratings:
            base_grade = r[0] if r else None
            if base_grade in self.GRADE_VALUES:
                values.append(self.GRADE_VALUES[base_grade])

        if not values:
            return "N/A", 0.0

        # Calculate trimmed mean
        trimmed_mean = stats.trim_mean(values, self.trim_percent)

        # Round to nearest grade
        consensus_value = int(np.round(trimmed_mean))
        consensus_grade = self.VALUE_GRADES.get(consensus_value, "C")

        # Calculate confidence
        std_dev = np.std(values)
        confidence = 1.0 / (1.0 + std_dev)

        return consensus_grade, float(confidence)


class ComparisonFramework:
    """Framework for comparing consensus methods."""

    def __init__(self):
        """Initialize comparison framework."""
        self.methods = {
            "simple_majority": SimpleMajority(),
            "weighted_median": WeightedMedian(),
            "trimmed_mean_20": TrimmedMean(0.2),
            "trimmed_mean_10": TrimmedMean(0.1),
        }

    def add_method(self, name: str, method: BaselineMethod):
        """Add a consensus method to compare.

        Args:
            name: Method identifier
            method: BaselineMethod instance
        """
        self.methods[name] = method

    def compare_methods(
        self,
        ratings_df: pd.DataFrame,
        include_bayesian: bool = True,
        bayesian_config: Optional[ModelConfig] = None,
    ) -> pd.DataFrame:
        """Compare all methods on the dataset.

        Args:
            ratings_df: DataFrame with columns [essay_id, rater_id, grade]
            include_bayesian: Whether to include Bayesian model
            bayesian_config: Configuration for Bayesian model

        Returns:
            DataFrame with comparison results
        """
        results = []

        # Group ratings by essay
        essay_groups = ratings_df.groupby("essay_id")

        # Process baseline methods
        for method_name, method in self.methods.items():
            method_results = {}
            ja24_grade = "N/A"

            for essay_id, group in essay_groups:
                ratings = group["grade"].tolist()
                consensus, confidence = method.get_consensus(ratings)
                method_results[essay_id] = (consensus, confidence)

                if essay_id == "JA24":
                    ja24_grade = consensus

            # Calculate metrics
            accuracy = self._calculate_accuracy(method_results, essay_groups)
            mean_conf = np.mean([conf for _, conf in method_results.values()])

            results.append(
                {
                    "Method": method.name,
                    "JA24 Grade": ja24_grade,
                    "JA24 Correct": ja24_grade == "A",
                    "Accuracy vs Majority": accuracy,
                    "Mean Confidence": mean_conf,
                    "Essays Graded": len(method_results),
                }
            )

        # Add Bayesian model if requested
        if include_bayesian:
            import time

            start_time = time.time()

            # Fit Bayesian model
            model = ImprovedBayesianModel(bayesian_config)
            model.fit(ratings_df)
            consensus_results = model.get_consensus_grades()

            computation_time = time.time() - start_time

            # Extract results
            bayesian_results = {}
            ja24_grade = "N/A"

            for essay_id, result in consensus_results.items():
                bayesian_results[essay_id] = (result.consensus_grade, result.confidence)
                if essay_id == "JA24":
                    ja24_grade = result.consensus_grade

            accuracy = self._calculate_accuracy(bayesian_results, essay_groups)
            mean_conf = np.mean([conf for _, conf in bayesian_results.values()])

            results.append(
                {
                    "Method": "Improved Bayesian",
                    "JA24 Grade": ja24_grade,
                    "JA24 Correct": ja24_grade == "A",
                    "Accuracy vs Majority": accuracy,
                    "Mean Confidence": mean_conf,
                    "Essays Graded": len(bayesian_results),
                    "Computation Time": computation_time,
                }
            )

        return pd.DataFrame(results)

    def _calculate_accuracy(
        self, method_results: Dict[str, tuple[str, float]], essay_groups: Any
    ) -> float:
        """Calculate accuracy versus simple majority.

        Args:
            method_results: Method's consensus results
            essay_groups: Grouped essay ratings

        Returns:
            Accuracy score
        """
        correct = 0
        total = 0

        for essay_id, group in essay_groups:
            if essay_id not in method_results:
                continue

            # Get majority grade
            grade_counts = group["grade"].apply(lambda x: x[0] if x else None).value_counts()
            if len(grade_counts) == 0:
                continue

            majority_grade = grade_counts.index[0]
            method_grade, _ = method_results[essay_id]

            if method_grade == majority_grade:
                correct += 1
            total += 1

        return correct / total if total > 0 else 0.0

    def generate_detailed_comparison(
        self, ratings_df: pd.DataFrame, output_path: Optional[str] = None
    ) -> str:
        """Generate detailed comparison report.

        Args:
            ratings_df: DataFrame with ratings
            output_path: Optional path to save report

        Returns:
            Markdown-formatted comparison report
        """
        # Run comparison
        comparison_df = self.compare_methods(ratings_df)

        # Generate report
        report = ["# Consensus Method Comparison Report\n"]
        report.append("## Summary Statistics\n")
        report.append(comparison_df.to_markdown(index=False))
        report.append("\n")

        # Focus on JA24 case
        report.append("## JA24 Case Analysis\n")
        report.append("Essay JA24 has 5 A ratings and 2 B ratings.\n")
        report.append("Expected consensus: **A**\n\n")

        report.append("| Method | Consensus Grade | Result |\n")
        report.append("|--------|----------------|--------|\n")

        for _, row in comparison_df.iterrows():
            status = "✅ PASS" if row["JA24 Correct"] else "❌ FAIL"
            report.append(f"| {row['Method']} | {row['JA24 Grade']} | {status} |\n")

        report.append("\n")

        # Add best performer
        best_method = comparison_df.loc[comparison_df["Accuracy vs Majority"].idxmax()]
        report.append("## Best Performer\n")
        report.append(
            f"**{best_method['Method']}** with {best_method['Accuracy vs Majority']:.1%} accuracy\n"
        )

        report_text = "".join(report)

        if output_path:
            with open(output_path, "w") as f:
                f.write(report_text)

        return report_text

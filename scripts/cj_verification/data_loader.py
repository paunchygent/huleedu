"""Data loader for Bayesian model verification.

Loads and parses CSV outputs from the Bayesian ordinal regression model,
providing access to raw ratings, rater severities, thresholds, and consensus grades.
"""

from pathlib import Path
from typing import Dict, Tuple

import pandas as pd


class BayesianDataLoader:
    """Load and parse Bayesian model data and results."""

    def __init__(self, data_path: Path):
        """Initialize with path to data directory.

        Args:
            data_path: Path to BAYESIAN_ANALYSIS_GPT_5_PRO directory
        """
        self.data_path = Path(data_path)
        self._validate_data_path()

    def _validate_data_path(self) -> None:
        """Ensure all required files exist."""
        required_files = [
            "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv",
            "ordinal_rater_severity.csv",
            "ordinal_thresholds.csv",
            "ordinal_true_scores_essays.csv",
            "ordinal_agreement_metrics.txt",
        ]

        for file in required_files:
            if not (self.data_path / file).exists():
                raise FileNotFoundError(f"Required file not found: {file}")

    def load_raw_ratings(self) -> pd.DataFrame:
        """Load raw rating data from CSV.

        Returns:
            DataFrame with essays as rows and raters as columns
        """
        df = pd.read_csv(self.data_path / "ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv")
        # Set ANCHOR-ID as index for easier access
        df = df.set_index("ANCHOR-ID")
        return df

    def load_rater_severity(self) -> pd.DataFrame:
        """Load rater severity adjustments.

        Returns:
            DataFrame with columns: rater, severity, n_rated
        """
        return pd.read_csv(self.data_path / "ordinal_rater_severity.csv")

    def load_thresholds(self) -> pd.DataFrame:
        """Load grade thresholds.

        Returns:
            DataFrame with columns: k, tau_k, between_grades
        """
        return pd.read_csv(self.data_path / "ordinal_thresholds.csv")

    def load_consensus_grades(self) -> pd.DataFrame:
        """Load final consensus grades and scores.

        Returns:
            DataFrame with columns: ANCHOR-ID, latent_ability, pred_mode_grade, etc.
        """
        return pd.read_csv(self.data_path / "ordinal_true_scores_essays.csv")

    def get_essay_ratings(self, essay_id: str) -> Dict[str, str]:
        """Get all ratings for a specific essay.

        Args:
            essay_id: Essay identifier (e.g., "JA24")

        Returns:
            Dictionary mapping rater name to grade
        """
        raw_data = self.load_raw_ratings()

        if essay_id not in raw_data.index:
            raise ValueError(f"Essay {essay_id} not found in data")

        # Get the row for this essay
        essay_row = raw_data.loc[essay_id]

        # Extract non-null ratings (skip FILE-NAME column)
        ratings = {}
        for rater in raw_data.columns[1:]:  # Skip FILE-NAME
            rating = essay_row[rater]
            if pd.notna(rating):
                ratings[rater] = rating

        return ratings

    def get_rater_severity_map(self) -> Dict[str, float]:
        """Create mapping of rater names to severity scores.

        Returns:
            Dictionary mapping rater name to severity score
        """
        severity_df = self.load_rater_severity()
        return dict(zip(severity_df["rater"], severity_df["severity"]))

    def analyze_essay_adjustments(self, essay_id: str) -> pd.DataFrame:
        """Analyze how rater adjustments affected a specific essay.

        Args:
            essay_id: Essay identifier

        Returns:
            DataFrame showing rater, raw_grade, severity, and impact
        """
        ratings = self.get_essay_ratings(essay_id)
        severities = self.get_rater_severity_map()

        analysis_data = []
        for rater, grade in ratings.items():
            severity = severities.get(rater, 0.0)

            # Determine if this rater's rating was likely discounted
            is_generous = severity < -0.5
            is_strict = severity > 0.5

            analysis_data.append(
                {
                    "rater": rater,
                    "raw_grade": grade,
                    "severity": severity,
                    "rater_type": "generous"
                    if is_generous
                    else "strict"
                    if is_strict
                    else "neutral",
                    "adjustment_impact": "discounted"
                    if is_generous
                    else "amplified"
                    if is_strict
                    else "normal",
                }
            )

        return pd.DataFrame(analysis_data).sort_values("severity")

    def grade_to_numeric(self, grade: str) -> float:
        """Convert letter grade to numeric value for analysis.

        Args:
            grade: Letter grade (e.g., "A", "B", "C+")

        Returns:
            Numeric value for comparison
        """
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

    def numeric_to_grade(self, numeric: float) -> str:
        """Convert numeric value back to letter grade.

        Args:
            numeric: Numeric grade value

        Returns:
            Closest letter grade
        """
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

        # Find closest grade
        rounded = int(round(numeric))
        rounded = max(0, min(14, rounded))  # Clamp to valid range
        return grade_map[rounded]

    def get_consensus_for_essay(self, essay_id: str) -> Dict:
        """Get consensus results for a specific essay.

        Args:
            essay_id: Essay identifier

        Returns:
            Dictionary with latent_ability, predicted_grade, etc.
        """
        consensus_df = self.load_consensus_grades()
        essay_data = consensus_df[consensus_df["ANCHOR-ID"] == essay_id]

        if essay_data.empty:
            raise ValueError(f"No consensus data found for essay {essay_id}")

        row = essay_data.iloc[0]
        return {
            "latent_ability": row["latent_ability"],
            "predicted_grade": row["pred_mode_grade"],
            "predicted_category": row["pred_mode_category"],
            "expected_category": row["expected_category"],
        }

    def load_agreement_metrics(self) -> Dict[str, float]:
        """Load agreement metrics from text file.

        Returns:
            Dictionary of metric names to values
        """
        metrics = {}
        metrics_file = self.data_path / "ordinal_agreement_metrics.txt"

        with open(metrics_file, "r") as f:
            for line in f:
                if "=" in line:
                    key, value = line.strip().split(" = ")
                    try:
                        metrics[key] = float(value)
                    except ValueError:
                        metrics[key] = value

        return metrics


def load_all_data(data_path: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Convenience function to load all data at once.

    Args:
        data_path: Path to data directory

    Returns:
        Tuple of (raw_ratings, rater_severity, thresholds, consensus_grades)
    """
    loader = BayesianDataLoader(Path(data_path))
    return (
        loader.load_raw_ratings(),
        loader.load_rater_severity(),
        loader.load_thresholds(),
        loader.load_consensus_grades(),
    )

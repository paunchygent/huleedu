"""Generate consensus grading reports from rater data.

This utility loads a wide-format CSV containing essay ratings, fits the
Bayesian consensus model, and exports analytic CSV files with consensus
results, grade probabilities, rater adjustments, and threshold estimates.

Example usage:

    pdm run python -m scripts.bayesian_consensus_model.generate_reports \
        --ratings-csv data/ratings.csv \
        --output-dir output/

The input CSV must contain two leading columns (essay identifier and file
name) followed by one column per rater, with letter grades as values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from . import (
    ConsensusGradingConfig,
    ImprovedBayesianModel,
    ModelConfig,
    PrincipledConsensusGrader,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ratings-csv",
        type=Path,
        required=True,
        help=
        "Path to the wide-format ratings CSV (essay id + file name + rater columns).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory where report CSV files will be written.",
    )
    parser.add_argument(
        "--sparse-threshold",
        type=int,
        default=50,
        help="Observation threshold for switching to the complex Bayesian model.",
    )
    parser.add_argument(
        "--majority-threshold",
        type=float,
        default=0.6,
        help="Minimum vote share that triggers the majority override for sparse essays.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information during execution.",
    )
    parser.add_argument(
        "--use-production-grader",
        action="store_true",
        help=(
            "Use PrincipledConsensusGrader for production-ready "
            "consensus with Wilson-score confidence intervals."
        ),
    )
    return parser.parse_args()


def _load_ratings(path: Path, verbose: bool = False) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Load ratings from a wide-format CSV file.

    Args:
        path: Path to the CSV file

    Returns:
        Tuple of (long-format ratings DataFrame, essay metadata dict)

    Raises:
        ValueError: If CSV format is invalid or no valid ratings found
        FileNotFoundError: If the CSV file doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Ratings CSV file not found: {path}")

    try:
        # Check if the file uses semicolon delimiter (v2 format)
        with open(path, 'r') as f:
            first_lines = f.read(500)

        if ';' in first_lines and ',' not in first_lines.split('\n')[1]:
            # V2 format: semicolon-delimited with header line to skip
            df = pd.read_csv(path, sep=';', skiprows=1)
            if verbose:
                print("Detected v2 format (semicolon-delimited)")
        else:
            # Original format: comma-delimited
            df = pd.read_csv(path)
            if verbose:
                print("Detected v1 format (comma-delimited)")
    except Exception as e:
        raise ValueError(f"Failed to read CSV file: {e}")

    if df.shape[1] < 3:
        raise ValueError(
            "Ratings CSV must contain at least essay id, "
            "file name, and one rater column."
        )

    essay_col, file_col = df.columns[:2]
    rater_cols = df.columns[2:]

    metadata = (
        df[[essay_col, file_col]]
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
        .set_index("essay_id")
        ["file_name"].to_dict()
    )

    long_df = (
        df.melt(
            id_vars=[essay_col, file_col],
            value_vars=rater_cols,
            var_name="rater_id",
            value_name="grade",
        )
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
    )
    long_df["grade"] = (
        long_df["grade"].astype(str).str.strip().str.upper().replace({"": np.nan, "NAN": np.nan})
    )
    long_df = long_df.dropna(subset=["grade"])

    if long_df.empty:
        raise ValueError(
            "No valid ratings found after cleaning the CSV. "
            "Ensure grades are populated and in Swedish format."
        )

    # Note: The model uses the full Swedish 10-level ordinal scale
    # Each grade (F, F+, E-, E+, D-, D+, C-, C+, B, A) is a distinct ordinal category
    if verbose:
        unique_grades = sorted(long_df["grade"].unique())
        print(f"Found {len(unique_grades)} distinct grades: {unique_grades}")

    return long_df[["essay_id", "rater_id", "grade"]], metadata


def _build_model_config(args: argparse.Namespace) -> ModelConfig:
    config = ModelConfig()
    config.sparse_data_threshold = args.sparse_threshold
    config.majority_override_ratio = args.majority_threshold
    return config


def _fit_bayesian_model(ratings_long: pd.DataFrame, config: ModelConfig) -> ImprovedBayesianModel:
    model = ImprovedBayesianModel(config)
    model.fit(ratings_long)
    return model


def _extract_rater_adjustments(model: ImprovedBayesianModel) -> pd.DataFrame:
    if not model.trace:
        return pd.DataFrame()
    posterior = model.trace.posterior["rater_severity"].mean(
        dim=["chain", "draw"]
    ).values
    rater_inverse = {idx: rater_id for rater_id, idx in model.rater_map.items()}

    records = [
        {
            "rater_id": rater_inverse.get(idx, f"Unknown_{idx}"),
            "severity_adjustment": float(posterior[idx]),
        }
        for idx in range(len(posterior))
        if idx in rater_inverse
    ]
    return pd.DataFrame(records).sort_values("rater_id")


def _extract_thresholds(model: ImprovedBayesianModel) -> pd.DataFrame:
    if not model.trace:
        return pd.DataFrame()
    thresholds = model.trace.posterior["thresholds"].mean(
        dim=["chain", "draw"]
    ).values
    records = []
    for k, tau_k in enumerate(thresholds, start=1):
        grades = ImprovedBayesianModel.SWEDISH_GRADES
        lower_grade = grades[k - 1]
        upper_grade = grades[k]
        records.append(
            {
                "boundary": k,
                "cutpoint": float(tau_k),
                "between_grades": f"{lower_grade} | {upper_grade}",
            }
        )
    return pd.DataFrame(records)


def _essay_results(
    model: ImprovedBayesianModel,
    metadata: Dict[str, str],
    majority_threshold: float,
    ratings_data: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    consensus = model.get_consensus_grades()
    if not model.trace:
        return pd.DataFrame(), pd.DataFrame()
    essay_abilities = model.trace.posterior["essay_ability"].mean(
        dim=["chain", "draw"]
    ).values
    ability_map = {
        essay_id: float(essay_abilities[idx])
        for essay_id, idx in model.essay_map.items()
    }

    # Prepare ratings data with numeric values
    prepared = ratings_data.copy()
    prepared["grade_numeric"] = prepared["grade"].map(model.GRADE_TO_NUMERIC)

    records = []
    prob_records = []

    for essay_id, result in consensus.items():
        ability = ability_map[essay_id]
        file_name = metadata.get(essay_id, "")

        essay_rows = prepared[prepared["essay_id"] == essay_id]
        total_ratings = len(essay_rows)
        grade_counts = essay_rows["grade_numeric"].value_counts()
        top_count = grade_counts.max() if not grade_counts.empty else 0
        majority_ratio = top_count / total_ratings if total_ratings else 0.0
        override_used = (
            total_ratings < model.config.sparse_data_threshold
            and majority_ratio >= majority_threshold
            and total_ratings > 0
        )

        grades = ImprovedBayesianModel.SWEDISH_GRADES
        grade_indices = list(range(len(grades)))
        grade_probs = np.array(
            [result.grade_probabilities.get(grade, 0.0) for grade in grades]
        )
        expected_index = float(np.dot(grade_probs, grade_indices))
        mode_index = int(np.argmax(grade_probs))

        records.append(
            {
                "essay_id": essay_id,
                "file_name": file_name,
                "consensus_grade": result.consensus_grade,
                "confidence": result.confidence,
                "consensus_method": (
                    "majority_override" if override_used else "bayesian"
                ),
                "total_ratings": total_ratings,
                "majority_ratio": majority_ratio,
                "latent_ability": ability,
                "expected_grade_index": expected_index,
                "mode_grade_index": mode_index,
            }
        )

        prob_row = {"essay_id": essay_id, "file_name": file_name}
        grades = ImprovedBayesianModel.SWEDISH_GRADES
        prob_row.update(
            {grade: float(prob) for grade, prob in zip(grades, grade_probs)}
        )
        prob_records.append(prob_row)

    essay_df = pd.DataFrame(records).sort_values("essay_id")
    probs_df = pd.DataFrame(prob_records).sort_values("essay_id")
    return essay_df, probs_df


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _use_production_grader(
    ratings_long: pd.DataFrame,
    metadata: Dict[str, str],
    config: ConsensusGradingConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Use the production-ready PrincipledConsensusGrader for consensus grading.

    Args:
        ratings_long: Long-format ratings DataFrame
        metadata: Essay metadata mapping
        config: Consensus grading configuration

    Returns:
        Tuple of (consensus results DataFrame, grade probabilities DataFrame)
    """
    grader = PrincipledConsensusGrader(config)
    consensus_results = grader.get_consensus(ratings_long)

    records = []
    prob_records = []

    for essay_id, result in consensus_results.items():
        file_name = metadata.get(essay_id, "")

        records.append(
            {
                "essay_id": essay_id,
                "file_name": file_name,
                "consensus_grade": result.consensus_grade,
                "confidence": result.confidence,
                "confidence_lower": result.confidence_interval[0],
                "confidence_upper": result.confidence_interval[1],
                "method_used": result.method_used,
                "warning": result.warning_message or "",
            }
        )

        prob_row = {"essay_id": essay_id, "file_name": file_name}
        prob_row.update(result.grade_probabilities)
        prob_records.append(prob_row)

    essay_df = pd.DataFrame(records).sort_values("essay_id")
    probs_df = pd.DataFrame(prob_records).sort_values("essay_id")
    return essay_df, probs_df


def main() -> None:
    args = _parse_args()
    ratings_long, metadata = _load_ratings(args.ratings_csv, args.verbose)
    if args.verbose:
        num_essays = ratings_long["essay_id"].nunique()
        num_raters = ratings_long["rater_id"].nunique()
        print(
            f"Loaded {len(ratings_long)} ratings covering "
            f"{num_essays} essays and {num_raters} raters."
        )

    if args.use_production_grader:
        # Use the production-ready consensus grader
        config = ConsensusGradingConfig(
            min_observations_for_bayesian=args.sparse_threshold,
        )
        essay_df, probs_df = _use_production_grader(ratings_long, metadata, config)

        # No rater adjustments or thresholds with production grader
        rater_df = pd.DataFrame()
        threshold_df = pd.DataFrame()
        diagnostics = {"method": "PrincipledConsensusGrader", "config": config.__dict__}
    else:
        # Use the direct Bayesian model
        config = _build_model_config(args)
        model = _fit_bayesian_model(ratings_long, config)

        essay_df, probs_df = _essay_results(
            model, metadata, args.majority_threshold, ratings_long
        )
        rater_df = _extract_rater_adjustments(model)
        threshold_df = _extract_thresholds(model)
        diagnostics = model.get_model_diagnostics()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    essay_df.to_csv(output_dir / "essay_consensus.csv", index=False)
    probs_df.to_csv(output_dir / "essay_grade_probabilities.csv", index=False)

    if not rater_df.empty:
        rater_df.to_csv(output_dir / "rater_adjustments.csv", index=False)
    if not threshold_df.empty:
        threshold_df.to_csv(output_dir / "grade_thresholds.csv", index=False)

    _write_json(output_dir / "model_diagnostics.json", diagnostics)

    if args.verbose:
        print(f"Reports written to {output_dir}")


if __name__ == "__main__":
    main()

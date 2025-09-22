"""Generate consensus grading reports from rater data.

This utility loads a wide-format CSV containing essay ratings, fits the
Bayesian consensus model, and exports analytic CSV files with consensus
results, grade probabilities, rater adjustments, and threshold estimates.

Example usage:

    pdm run python -m scripts.bayesian_consensus_model.generate_reports \
        --ratings-csv docs/rapport_till_kollegor/BAYESIAN_ANALYSIS_GPT_5_PRO/ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.csv \
        --output-dir docs/rapport_till_kollegor/BAYESIAN_ANALYSIS_GPT_5_PRO/updated

The input CSV must contain two leading columns (essay identifier and file
name) followed by one column per rater, with letter grades as values.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Iterable

import numpy as np
import pandas as pd

from . import ImprovedBayesianModel, ModelConfig

SWEDISH_GRADES: tuple[str, ...] = ("F", "E", "D", "C", "B", "A")


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
    return parser.parse_args()


def _load_ratings(path: Path) -> tuple[pd.DataFrame, Dict[str, str]]:
    df = pd.read_csv(path)
    if df.shape[1] < 3:
        raise ValueError("Ratings CSV must contain at least essay id, file name, and one rater column.")

    essay_col, file_col = df.columns[:2]
    rater_cols = df.columns[2:]

    metadata = (
        df[[essay_col, file_col]]
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
        .set_index("essay_id")
        ["file_name"].to_dict()
    )

    long_df = (
        df.melt(id_vars=[essay_col, file_col], value_vars=rater_cols, var_name="rater_id", value_name="grade")
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
    )
    long_df["grade"] = (
        long_df["grade"].astype(str).str.strip().str.upper().replace({"": np.nan, "NAN": np.nan})
    )
    long_df = long_df.dropna(subset=["grade"])

    if long_df.empty:
        raise ValueError("No ratings found after cleaning the CSV. Ensure grades are populated.")

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
    posterior = model.trace.posterior["rater_severity"].mean(dim=["chain", "draw"]).values
    rater_inverse = {idx: rater_id for rater_id, idx in model.rater_map.items()}

    records = [
        {
            "rater_id": rater_inverse[idx],
            "severity_adjustment": float(posterior[idx]),
        }
        for idx in range(len(posterior))
    ]
    return pd.DataFrame(records).sort_values("rater_id")


def _extract_thresholds(model: ImprovedBayesianModel) -> pd.DataFrame:
    thresholds = model.trace.posterior["thresholds"].mean(dim=["chain", "draw"]).values
    records = []
    for k, tau_k in enumerate(thresholds, start=1):
        lower_grade = SWEDISH_GRADES[k - 1]
        upper_grade = SWEDISH_GRADES[k]
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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    consensus = model.get_consensus_grades()
    essay_abilities = model.trace.posterior["essay_ability"].mean(dim=["chain", "draw"]).values
    ability_map = {essay_id: float(essay_abilities[idx]) for essay_id, idx in model.essay_map.items()}

    prepared = model._ratings_data  # Prepared DataFrame with integer grades

    records = []
    prob_records = []

    for essay_id, result in consensus.items():
        essay_idx = model.essay_map[essay_id]
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

        grade_indices = list(range(len(SWEDISH_GRADES)))
        grade_probs = np.array([result.grade_probabilities.get(grade, 0.0) for grade in SWEDISH_GRADES])
        expected_index = float(np.dot(grade_probs, grade_indices))
        mode_index = int(np.argmax(grade_probs))

        records.append(
            {
                "essay_id": essay_id,
                "file_name": file_name,
                "consensus_grade": result.consensus_grade,
                "confidence": result.confidence,
                "consensus_method": "majority_override" if override_used else "bayesian",
                "total_ratings": total_ratings,
                "majority_ratio": majority_ratio,
                "latent_ability": ability,
                "expected_grade_index": expected_index,
                "mode_grade_index": mode_index,
            }
        )

        prob_row = {"essay_id": essay_id, "file_name": file_name}
        prob_row.update({grade: float(prob) for grade, prob in zip(SWEDISH_GRADES, grade_probs)})
        prob_records.append(prob_row)

    essay_df = pd.DataFrame(records).sort_values("essay_id")
    probs_df = pd.DataFrame(prob_records).sort_values("essay_id")
    return essay_df, probs_df


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def main() -> None:
    args = _parse_args()
    ratings_long, metadata = _load_ratings(args.ratings_csv)
    if args.verbose:
        print(f"Loaded {len(ratings_long)} ratings covering {ratings_long['essay_id'].nunique()} essays and {ratings_long['rater_id'].nunique()} raters.")

    config = _build_model_config(args)
    model = _fit_bayesian_model(ratings_long, config)

    essay_df, probs_df = _essay_results(model, metadata, args.majority_threshold)
    rater_df = _extract_rater_adjustments(model)
    threshold_df = _extract_thresholds(model)
    diagnostics = model.get_model_diagnostics()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    essay_df.to_csv(output_dir / "essay_consensus.csv", index=False)
    probs_df.to_csv(output_dir / "essay_grade_probabilities.csv", index=False)
    rater_df.to_csv(output_dir / "rater_adjustments.csv", index=False)
    threshold_df.to_csv(output_dir / "grade_thresholds.csv", index=False)
    _write_json(output_dir / "model_diagnostics.json", diagnostics)

    if args.verbose:
        print(f"Reports written to {output_dir}")


if __name__ == "__main__":
    main()

"""Generate consensus grading reports from rater data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .bayesian_consensus_model import ConsensusModel, ConsensusResult, KernelConfig, GRADES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


def _load_ratings(path: Path, verbose: bool = False) -> Tuple[pd.DataFrame, Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Ratings CSV not found: {path}")

    with path.open("r", encoding="utf-8") as handle:
        preview = handle.read(512)

    if ";" in preview and "," not in preview.splitlines()[1]:
        df = pd.read_csv(path, sep=";", skiprows=1)
        fmt = "semicolon"
    else:
        df = pd.read_csv(path)
        fmt = "comma"

    if df.shape[1] < 3:
        raise ValueError("Ratings CSV must contain essay id, file name, and at least one rater column")

    if verbose:
        print(f"Detected {fmt}-delimited file with {df.shape[0]} essays")

    essay_col, file_col = df.columns[:2]
    metadata = (
        df[[essay_col, file_col]]
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
        .set_index("essay_id")["file_name"].to_dict()
    )

    long_df = (
        df.melt(
            id_vars=[essay_col, file_col],
            var_name="rater_id",
            value_name="grade",
        )
        .rename(columns={essay_col: "essay_id", file_col: "file_name"})
    )
    long_df["grade"] = long_df["grade"].astype(str).str.strip().str.upper()
    long_df = long_df.replace({"": np.nan, "NAN": np.nan}).dropna(subset=["grade"])

    if long_df.empty:
        raise ValueError("No valid grades found in ratings CSV")

    if verbose:
        print(f"Found {len(long_df)} total ratings across {long_df['essay_id'].nunique()} essays")

    return long_df[["essay_id", "rater_id", "grade"]], metadata


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_outputs(
    output_dir: Path,
    consensus: Dict[str, "ConsensusResult"],
    metadata: Dict[str, str],
) -> None:
    records = []
    prob_rows = []
    for essay_id, result in consensus.items():
        file_name = metadata.get(essay_id, "")
        records.append(
            {
                "essay_id": essay_id,
                "file_name": file_name,
                "consensus_grade": result.consensus_grade,
                "confidence": result.confidence,
                "sample_size": result.sample_size,
                "ability": result.ability,
                "expected_grade_index": result.expected_grade_index,
            }
        )
        prob_row = {"essay_id": essay_id, "file_name": file_name}
        prob_row.update(result.grade_probabilities)
        prob_rows.append(prob_row)

    consensus_df = pd.DataFrame(records).sort_values("essay_id")
    probs_df = pd.DataFrame(prob_rows).sort_values("essay_id")

    (output_dir / "essay_consensus.csv").write_text(consensus_df.to_csv(index=False), encoding="utf-8")
    (output_dir / "essay_grade_probabilities.csv").write_text(probs_df.to_csv(index=False), encoding="utf-8")


def _write_rater_reports(
    output_dir: Path,
    metrics: pd.DataFrame,
    bias_posteriors: pd.DataFrame,
) -> None:
    metrics = metrics.sort_values("rater_id").reset_index(drop=True)
    (output_dir / "rater_weights.csv").write_text(
        metrics[["rater_id", "weight", "n_rated"]].to_csv(index=False),
        encoding="utf-8",
    )
    (output_dir / "rater_severity.csv").write_text(
        metrics[["rater_id", "rms_alignment", "mad_alignment", "n_rated"]].to_csv(index=False),
        encoding="utf-8",
    )
    (output_dir / "rater_agreement.csv").write_text(
        metrics[["rater_id", "mad_alignment", "std_grade_index", "grade_range"]].to_csv(index=False),
        encoding="utf-8",
    )
    (output_dir / "rater_spread.csv").write_text(
        metrics[["rater_id", "unique_grades", "grade_range", "min_grade_index", "max_grade_index"]].to_csv(index=False),
        encoding="utf-8",
    )
    bias = bias_posteriors.sort_values("rater_id").reset_index(drop=True)
    (output_dir / "rater_bias_posteriors_eb.csv").write_text(
        bias.to_csv(index=False),
        encoding="utf-8",
    )


def _essay_inter_rater_stats(ratings: pd.DataFrame, consensus: Dict[str, "ConsensusResult"]) -> pd.DataFrame:
    rows = []
    grade_map = {grade: idx for idx, grade in enumerate(GRADES)}
    for essay_id, group in ratings.groupby("essay_id"):
        indices = group["grade"].map(grade_map)
        if indices.empty:
            continue
        counts = indices.value_counts().sort_index()
        entropy = -np.sum((counts / counts.sum()) * np.log((counts / counts.sum()) + 1e-12))
        rows.append(
            {
                "essay_id": essay_id,
                "sample_size": int(len(indices)),
                "grade_std": float(indices.std(ddof=0)),
                "grade_range": float(indices.max() - indices.min()),
                "shannon_entropy": float(entropy),
                "majority_ratio": float(counts.max() / counts.sum()),
                "consensus_grade": consensus[essay_id].consensus_grade if essay_id in consensus else "",
                "consensus_confidence": consensus[essay_id].confidence if essay_id in consensus else np.nan,
            }
        )
    return pd.DataFrame(rows).sort_values("essay_id")


def main() -> None:
    args = _parse_args()
    ratings, metadata = _load_ratings(args.ratings_csv, verbose=args.verbose)
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    config = KernelConfig()
    model = ConsensusModel(config)
    model.fit(ratings)

    consensus_objects = model.get_consensus()
    _write_outputs(output_dir, consensus_objects, metadata)
    metrics_df = model.rater_metrics
    bias_posteriors = model.rater_bias_posteriors
    _write_rater_reports(output_dir, metrics_df, bias_posteriors)
    inter_rater_df = _essay_inter_rater_stats(ratings, consensus_objects)
    (output_dir / "essay_inter_rater_stats.csv").write_text(inter_rater_df.to_csv(index=False), encoding="utf-8")
    (output_dir / "grade_thresholds.csv").unlink(missing_ok=True)
    _write_json(
        output_dir / "model_diagnostics.json",
        {
            "model": "ordinal_kernel",
            "sigma": config.sigma,
            "pseudo_count": config.pseudo_count,
        },
    )


if __name__ == "__main__":
    main()

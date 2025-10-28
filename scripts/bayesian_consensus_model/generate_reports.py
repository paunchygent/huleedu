"""Generate consensus grading reports from rater data."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import numpy as np
import pandas as pd

from .bayesian_consensus_model import ConsensusModel, ConsensusResult, KernelConfig, GRADES


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ratings-csv", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output/bayesian_consensus_model"))
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--bias-correction", choices=["on", "off"], default="on")
    parser.add_argument("--compare-without-bias", action="store_true")
    parser.add_argument("--run-label", type=str, default="", help="Optional label for run directory; defaults to timestamp")
    parser.add_argument("--use-argmax-decision", action="store_true", help="Select consensus grade via argmax over smoothed probabilities")
    parser.add_argument("--use-loo-alignment", action="store_true", help="Enable leave-one-out essay means for rater alignment")
    parser.add_argument("--use-precision-weights", action="store_true", help="Scale rater weights by bias posterior precision")
    parser.add_argument("--use-neutral-gating", action="store_true", help="Compute neutral evidence ESS metrics")
    parser.add_argument("--neutral-delta-mu", type=float, default=0.25, help="Bias magnitude threshold for neutral ESS computation")
    parser.add_argument("--neutral-var-max", type=float, default=0.20, help="Posterior variance ceiling for neutral ESS computation")
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


def _build_kernel_config(*, bias_correction: bool, args: argparse.Namespace) -> KernelConfig:
    return KernelConfig(
        bias_correction=bias_correction,
        use_argmax_decision=getattr(args, "use_argmax_decision", False),
        use_loo_alignment=getattr(args, "use_loo_alignment", False),
        use_precision_weights=getattr(args, "use_precision_weights", False),
        use_neutral_gating=getattr(args, "use_neutral_gating", False),
        neutral_delta_mu=getattr(args, "neutral_delta_mu", 0.25),
        neutral_var_max=getattr(args, "neutral_var_max", 0.20),
    )


def _write_json(path: Path, payload: Dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_outputs(
    output_dir: Path,
    consensus: Dict[str, "ConsensusResult"],
    metadata: Dict[str, str],
) -> Tuple[pd.DataFrame, pd.DataFrame]:
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
                "neutral_ess": result.neutral_ess,
                "needs_more_ratings": result.needs_more_ratings,
            }
        )
        prob_row = {"essay_id": essay_id, "file_name": file_name}
        prob_row.update(result.grade_probabilities)
        prob_rows.append(prob_row)

    consensus_df = pd.DataFrame(records).sort_values("essay_id")
    probs_df = pd.DataFrame(prob_rows).sort_values("essay_id")

    (output_dir / "essay_consensus.csv").write_text(consensus_df.to_csv(index=False), encoding="utf-8")
    (output_dir / "essay_grade_probabilities.csv").write_text(probs_df.to_csv(index=False), encoding="utf-8")
    return consensus_df, probs_df


def _write_rater_reports(
    output_dir: Path,
    metrics: pd.DataFrame,
    bias_posteriors: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
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
    return metrics, bias

def _run_pipeline(
    ratings: pd.DataFrame,
    metadata: Dict[str, str],
    output_dir: Path,
    *,
    config: KernelConfig,
    verbose: bool = False,
) -> Dict[str, object]:
    model = ConsensusModel(config)
    model.fit(ratings)

    consensus = model.get_consensus()
    consensus_df, probs_df = _write_outputs(output_dir, consensus, metadata)
    metrics_df = model.rater_metrics
    bias_posteriors = model.rater_bias_posteriors
    metrics_sorted, bias_sorted = _write_rater_reports(output_dir, metrics_df, bias_posteriors)
    plot_created = _plot_bias_vs_weight(output_dir, metrics_sorted, bias_sorted)
    inter_rater_df = _essay_inter_rater_stats(ratings, consensus)
    (output_dir / "essay_inter_rater_stats.csv").write_text(
        inter_rater_df.to_csv(index=False), encoding="utf-8"
    )
    (output_dir / "grade_thresholds.csv").unlink(missing_ok=True)
    diagnostics = asdict(config)
    diagnostics.update({
        "model": "ordinal_kernel",
        "bias_correction": config.bias_correction,
    })
    _write_json(output_dir / "model_diagnostics.json", diagnostics)
    if verbose and plot_created:
        print(f"Saved rater bias vs weight plot to {output_dir}")
    return {
        "config": config,
        "model": model,
        "consensus": consensus,
        "consensus_df": consensus_df,
        "probabilities_df": probs_df,
        "metrics_df": metrics_sorted,
        "bias_df": bias_sorted,
    }


def _write_comparison_outputs(
    output_dir: Path,
    base: Dict[str, object],
    alt: Dict[str, object],
    *,
    base_bias_correction: bool,
) -> None:
    base_label = "bias_on" if base_bias_correction else "bias_off"
    alt_label = "bias_off" if base_bias_correction else "bias_on"

    base_df = base["consensus_df"].copy()
    alt_df = alt["consensus_df"].copy()
    base_df = base_df.rename(
        columns={
            "consensus_grade": f"consensus_grade_{base_label}",
            "confidence": f"confidence_{base_label}",
            "expected_grade_index": f"expected_grade_index_{base_label}",
            "ability": f"ability_{base_label}",
            "neutral_ess": f"neutral_ess_{base_label}",
            "needs_more_ratings": f"needs_more_ratings_{base_label}",
        }
    )
    alt_df = alt_df.rename(
        columns={
            "consensus_grade": f"consensus_grade_{alt_label}",
            "confidence": f"confidence_{alt_label}",
            "expected_grade_index": f"expected_grade_index_{alt_label}",
            "ability": f"ability_{alt_label}",
            "neutral_ess": f"neutral_ess_{alt_label}",
            "needs_more_ratings": f"needs_more_ratings_{alt_label}",
        }
    )
    merged = base_df.merge(alt_df, on=["essay_id", "file_name", "sample_size"], how="inner")
    merged["delta_expected"] = (
        merged[f"expected_grade_index_{base_label}"]
        - merged[f"expected_grade_index_{alt_label}"]
    )
    merged["delta_confidence"] = (
        merged[f"confidence_{base_label}"]
        - merged[f"confidence_{alt_label}"]
    )
    merged["grade_changed"] = (
        merged[f"consensus_grade_{base_label}"]
        != merged[f"consensus_grade_{alt_label}"]
    )
    merged = merged.sort_values("delta_expected", key=lambda s: s.abs(), ascending=False)

    comparison_csv = output_dir / f"comparison_{base_label}_vs_{alt_label}.csv"
    comparison_csv.write_text(merged.to_csv(index=False), encoding="utf-8")

    summary = {
        "base_bias_correction": base_bias_correction,
        "grade_changes": int(merged["grade_changed"].sum()),
        "mean_abs_delta_expected": float(merged["delta_expected"].abs().mean()),
        "median_abs_delta_expected": float(merged["delta_expected"].abs().median()),
        "max_abs_delta_expected": float(merged["delta_expected"].abs().max()),
        "neutral_ess_mean_variant": float(merged[f"neutral_ess_{alt_label}"].mean()),
        "needs_more_ratings_variant": int(merged[f"needs_more_ratings_{alt_label}"].sum()),
    }
    _write_json(
        output_dir / f"comparison_{base_label}_vs_{alt_label}.json", summary
    )


def _plot_bias_vs_weight(output_dir: Path, metrics: pd.DataFrame, bias_posteriors: pd.DataFrame) -> bool:
    """Create a scatter plot of posterior bias versus reliability weight."""

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    df = bias_posteriors.merge(metrics[["rater_id", "weight"]], on="rater_id", how="left")
    if df.empty:
        return False
    df = df.copy()
    df["abs_mu"] = df["mu_post"].abs()

    fig, ax = plt.subplots(figsize=(7, 5))
    scatter = ax.scatter(
        df["weight"],
        df["mu_post"],
        c=df["shrinkage"],
        cmap="coolwarm",
        s=80,
        edgecolor="black",
        linewidth=0.5,
    )
    ax.axhline(0.0, color="grey", linewidth=1, linestyle="--")
    ax.set_xlabel("Reliability weight")
    ax.set_ylabel("Posterior bias (grade index units)")
    ax.set_title("Rater bias vs reliability weight")
    fig.colorbar(scatter, ax=ax, label="Shrinkage factor")

    flagged = df[df["abs_mu"] >= 0.5]
    for _, row in flagged.iterrows():
        ax.annotate(
            row["rater_id"],
            (row["weight"], row["mu_post"]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=9,
            ha="left",
        )

    output_path = output_dir / "rater_bias_vs_weight.png"
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True



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
                "neutral_ess": consensus[essay_id].neutral_ess if essay_id in consensus else 0.0,
                "needs_more_ratings": consensus[essay_id].needs_more_ratings if essay_id in consensus else False,
            }
        )
    return pd.DataFrame(rows).sort_values("essay_id")


def main() -> None:
    args = _parse_args()
    ratings, metadata = _load_ratings(args.ratings_csv, verbose=args.verbose)
    base_output = args.output_dir
    base_output.mkdir(parents=True, exist_ok=True)

    if args.run_label:
        run_label = args.run_label
    else:
        run_label = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    run_dir = base_output / run_label
    run_dir.mkdir(parents=True, exist_ok=True)

    apply_bias = args.bias_correction == "on"
    if args.verbose:
        state = "enabled" if apply_bias else "disabled"
        print(f"Bias correction {state} for primary run")
        print(f"Writing outputs to {run_dir}")

    base_config = _build_kernel_config(bias_correction=apply_bias, args=args)
    base_results = _run_pipeline(
        ratings, metadata, run_dir, config=base_config, verbose=args.verbose
    )

    if args.compare_without_bias:
        alt_dir = run_dir / ("bias_off" if apply_bias else "bias_on")
        alt_dir.mkdir(parents=True, exist_ok=True)
        alt_config = _build_kernel_config(bias_correction=not apply_bias, args=args)
        alt_results = _run_pipeline(
            ratings,
            metadata,
            alt_dir,
            config=alt_config,
            verbose=args.verbose,
        )
        _write_comparison_outputs(
            run_dir, base_results, alt_results, base_bias_correction=apply_bias
        )


if __name__ == "__main__":
    main()

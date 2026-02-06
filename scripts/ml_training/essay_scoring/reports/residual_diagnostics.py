"""Residual diagnostics artifacts and report generation for essay scoring runs.

Purpose:
    Persist per-record predictions and residuals (with construct-relevant covariates) and generate
    a Markdown report that highlights where the model fails by:
    - prompt (topic)
    - grade band (tails vs middle)
    - key covariates (length, error densities, prompt similarity)

Relationships:
    - Used by `scripts.ml_training.essay_scoring.cross_validation` for CV-first Gate C diagnostics.
    - Consumes predictions produced by XGBoost models trained via
      `scripts.ml_training.essay_scoring.training.trainer`.
    - Uses covariates stored in feature matrices defined by
      `scripts.ml_training.essay_scoring.features.schema`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from scripts.ml_training.essay_scoring.features.combiner import FeatureMatrix
from scripts.ml_training.essay_scoring.training.evaluation import evaluate_predictions
from scripts.ml_training.essay_scoring.training.qwk import clip_bands, round_to_half_band

_DEFAULT_COVARIATE_FEATURES = (
    "word_count",
    "grammar_errors_per_100_words",
    "spelling_errors_per_100_words",
    "punctuation_errors_per_100_words",
    "prompt_similarity",
)


@dataclass(frozen=True)
class ResidualArtifacts:
    """Paths written for residual diagnostics."""

    csv_path: Path
    jsonl_path: Path


def build_residual_frame(
    *,
    record_ids: list[str],
    prompts: list[str],
    y_true: np.ndarray,
    y_pred_raw: np.ndarray,
    y_pred_mapped: np.ndarray | None = None,
    min_band: float,
    max_band: float,
    split_label: str,
    feature_matrix: FeatureMatrix | None,
    row_indices: np.ndarray | None = None,
    fold_ids: list[int] | None = None,
    covariate_feature_names: tuple[str, ...] = _DEFAULT_COVARIATE_FEATURES,
) -> pd.DataFrame:
    """Build a DataFrame of per-record predictions/residuals with covariates.

    Args:
        record_ids: Stable record identifiers.
        prompts: Prompt/topic for each record (same order as record_ids).
        y_true: Ground-truth labels.
        y_pred_raw: Raw model predictions (continuous).
        min_band: Minimum valid score band.
        max_band: Maximum valid score band.
        split_label: Split identifier (e.g. "cv_val_oof", "locked_test").
        feature_matrix: Feature matrix containing covariate columns.
        row_indices: Optional indices mapping these rows into feature_matrix.matrix.
        fold_ids: Optional fold id per record (for CV OOF val predictions).
        covariate_feature_names: Covariate columns to extract from feature_matrix when present.

    Returns:
        DataFrame containing per-record residual diagnostics.
    """

    if len(record_ids) != len(prompts):
        raise ValueError("record_ids and prompts must have matching lengths.")
    if len(record_ids) != int(y_true.shape[0]) or len(record_ids) != int(y_pred_raw.shape[0]):
        raise ValueError("record_ids, y_true, and y_pred_raw must have matching lengths.")
    if y_pred_mapped is not None and len(record_ids) != int(y_pred_mapped.shape[0]):
        raise ValueError("y_pred_mapped must be None or have the same length as y_pred_raw.")
    if fold_ids is not None and len(fold_ids) != len(record_ids):
        raise ValueError("fold_ids must be None or have the same length as record_ids.")

    if y_pred_mapped is None:
        y_pred = clip_bands(round_to_half_band(y_pred_raw), min_band=min_band, max_band=max_band)
    else:
        y_pred = clip_bands(
            round_to_half_band(y_pred_mapped.astype(float)),
            min_band=min_band,
            max_band=max_band,
        )
    residual = y_pred - y_true
    abs_residual = np.abs(residual)

    frame = pd.DataFrame(
        {
            "split": [split_label] * len(record_ids),
            "record_id": record_ids,
            "prompt": prompts,
            "y_true": y_true.astype(float),
            "y_pred_raw": y_pred_raw.astype(float),
            "y_pred": y_pred.astype(float),
            "residual": residual.astype(float),
            "abs_residual": abs_residual.astype(float),
            "within_half_band": (abs_residual <= 0.5).astype(int),
        }
    )
    if fold_ids is not None:
        frame.insert(1, "fold", fold_ids)

    if feature_matrix is not None:
        _add_covariates(
            frame=frame,
            feature_matrix=feature_matrix,
            row_indices=row_indices,
            covariate_feature_names=covariate_feature_names,
        )

    return frame


def persist_residual_artifacts(
    frame: pd.DataFrame,
    *,
    output_stem: Path,
) -> ResidualArtifacts:
    """Persist residual diagnostics rows as CSV + JSONL.

    Args:
        frame: Residual diagnostics rows.
        output_stem: Path without extension (e.g. artifacts/residuals_cv_val_oof).

    Returns:
        ResidualArtifacts paths.
    """

    csv_path = output_stem.with_suffix(".csv")
    jsonl_path = output_stem.with_suffix(".jsonl")

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(csv_path, index=False)
    jsonl_path.write_text(
        frame.to_json(orient="records", lines=True),
        encoding="utf-8",
    )
    return ResidualArtifacts(csv_path=csv_path, jsonl_path=jsonl_path)


def generate_residual_diagnostics_report(
    *,
    frames: dict[str, pd.DataFrame],
    min_band: float,
    max_band: float,
    output_path: Path,
    min_prompt_n: int = 30,
    top_prompts: int = 15,
    worst_examples: int = 20,
) -> None:
    """Generate a residual diagnostics report as Markdown.

    Args:
        frames: Mapping of split name -> per-record residual DataFrame.
        min_band: Minimum valid score band.
        max_band: Maximum valid score band.
        output_path: Where to write the report.
        min_prompt_n: Minimum prompt sample size for prompt-level tables.
        top_prompts: Number of prompts to show in prompt-level tables.
        worst_examples: Number of worst residual examples to list per split.
    """

    sections: list[str] = [
        "# Residual Diagnostics Report",
        "",
        "## Purpose",
        "",
        "- Identify failure modes by prompt, grade band, and key covariates.",
        "- Use this report to guide feature selection and objective tuning.",
        "- Guard construct validity by inspecting prompt slices and tails.",
        "",
    ]

    for split_name, frame in frames.items():
        sections.extend(
            _build_split_section(
                split_name=split_name,
                frame=frame,
                min_band=min_band,
                max_band=max_band,
                min_prompt_n=min_prompt_n,
                top_prompts=top_prompts,
                worst_examples=worst_examples,
            )
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(sections), encoding="utf-8")


def _add_covariates(
    *,
    frame: pd.DataFrame,
    feature_matrix: FeatureMatrix,
    row_indices: np.ndarray | None,
    covariate_feature_names: tuple[str, ...],
) -> None:
    name_to_idx = {name: idx for idx, name in enumerate(feature_matrix.feature_names)}
    for feature_name in covariate_feature_names:
        col_idx = name_to_idx.get(feature_name)
        if col_idx is None:
            frame[feature_name] = np.nan
            continue
        if row_indices is None:
            values = feature_matrix.matrix[:, col_idx]
        else:
            values = feature_matrix.matrix[row_indices, col_idx]
        frame[feature_name] = values.astype(float)


def _build_split_section(
    *,
    split_name: str,
    frame: pd.DataFrame,
    min_band: float,
    max_band: float,
    min_prompt_n: int,
    top_prompts: int,
    worst_examples: int,
) -> list[str]:
    y_true = frame["y_true"].to_numpy(dtype=float)
    y_pred = frame["y_pred"].to_numpy(dtype=float)
    evaluation = evaluate_predictions(y_true, y_pred, min_band=min_band, max_band=max_band)

    prompt_table = _per_prompt_table(
        frame=frame,
        min_band=min_band,
        max_band=max_band,
        min_prompt_n=min_prompt_n,
        top_prompts=top_prompts,
    )
    band_table = _per_band_table(frame)
    corr_table = _covariate_correlation_table(frame)
    worst_table = _worst_examples_table(frame, n=worst_examples)

    lines = [
        f"## Split: `{split_name}`",
        "",
        "### Global Metrics",
        "",
        f"- records: `{len(frame)}`",
        f"- qwk: `{evaluation.qwk:.4f}`",
        f"- mae (rounded bands): `{evaluation.mean_absolute_error:.4f}`",
        f"- adjacent_accuracy: `{evaluation.adjacent_accuracy:.4f}`",
        "",
        "### By Prompt (min_n safeguard)",
        "",
        f"- min_prompt_n: `{min_prompt_n}`",
        "",
        "```text",
        prompt_table,
        "```",
        "",
        "### By Grade Band",
        "",
        "```text",
        band_table,
        "```",
        "",
        "### Covariates (Spearman correlation)",
        "",
        "```text",
        corr_table,
        "```",
        "",
        "### Worst Residual Examples",
        "",
        "```text",
        worst_table,
        "```",
        "",
    ]
    return lines


def _per_prompt_table(
    *,
    frame: pd.DataFrame,
    min_band: float,
    max_band: float,
    min_prompt_n: int,
    top_prompts: int,
) -> str:
    rows: list[dict[str, object]] = []
    for prompt, group in frame.groupby("prompt"):
        n = int(group.shape[0])
        if n < min_prompt_n:
            continue
        y_true = group["y_true"].to_numpy(dtype=float)
        y_pred = group["y_pred"].to_numpy(dtype=float)
        evaluation = evaluate_predictions(y_true, y_pred, min_band=min_band, max_band=max_band)
        rows.append(
            {
                "prompt": prompt,
                "n": n,
                "qwk": float(evaluation.qwk),
                "mae": float(evaluation.mean_absolute_error),
                "adjacent_acc": float(evaluation.adjacent_accuracy),
            }
        )

    if not rows:
        return "No prompts meet min_prompt_n threshold."

    table = pd.DataFrame(rows).sort_values(["mae", "n"], ascending=[False, False]).head(top_prompts)
    return table.to_string(index=False)


def _per_band_table(frame: pd.DataFrame) -> str:
    grouped = frame.groupby("y_true", dropna=False)
    summary = grouped.agg(
        n=("record_id", "count"),
        mae=("abs_residual", "mean"),
        mean_residual=("residual", "mean"),
        adjacent_acc=("within_half_band", "mean"),
    )
    summary = summary.sort_index()
    return summary.to_string()


def _covariate_correlation_table(frame: pd.DataFrame) -> str:
    covariates = [name for name in _DEFAULT_COVARIATE_FEATURES if name in frame.columns]
    rows: list[dict[str, object]] = []
    for covariate in covariates:
        values = frame[covariate].to_numpy(dtype=float)
        if np.all(np.isnan(values)):
            continue
        rows.append(
            {
                "covariate": covariate,
                "spearman(cov,residual)": _safe_spearman(values, frame["residual"].to_numpy()),
                "spearman(cov,abs_residual)": _safe_spearman(
                    values, frame["abs_residual"].to_numpy()
                ),
            }
        )

    if not rows:
        return "No covariate columns available in frame."

    table = pd.DataFrame(rows)
    return table.to_string(index=False)


def _worst_examples_table(frame: pd.DataFrame, *, n: int) -> str:
    cols = [
        "record_id",
        "prompt",
        "y_true",
        "y_pred",
        "residual",
        "abs_residual",
        "word_count",
        "grammar_errors_per_100_words",
        "spelling_errors_per_100_words",
        "prompt_similarity",
    ]
    present = [col for col in cols if col in frame.columns]
    worst = frame.sort_values("abs_residual", ascending=False).head(n)[present]
    return worst.to_string(index=False)


def _safe_spearman(x: np.ndarray, y: np.ndarray) -> float:
    mask = ~(np.isnan(x) | np.isnan(y))
    if int(np.sum(mask)) < 2:
        return 0.0
    result = spearmanr(x[mask], y[mask]).correlation
    return float(result or 0.0)

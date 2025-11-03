"""Rater severity weighting utilities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
import pandas as pd


@dataclass
class RaterSeverityConfig:
    count_scale: float = 4.0
    alignment_scale: float = 1.0
    min_weight: float = 0.2


def _prepare_alignment_frame(
    ratings: pd.DataFrame,
    grade_to_index: Dict[str, int],
    *,
    use_loo_alignment: bool,
) -> pd.DataFrame:
    """Attach grade indices, essay means, and deviations for alignment metrics."""

    if ratings.empty:
        return ratings.copy()

    df = ratings.copy()
    df["grade_index"] = df["grade"].map(grade_to_index).astype(float)
    df = df.dropna(subset=["grade_index"])  # Drop rows with unmapped grades
    if df.empty:
        return df

    essay_group = df.groupby("essay_id")["grade_index"]
    if use_loo_alignment:
        essay_sum = essay_group.sum()
        essay_count = essay_group.count()
        df = df.join(essay_sum.rename("essay_sum"), on="essay_id")
        df = df.join(essay_count.rename("essay_count"), on="essay_id")
        adjusted_sum = df["essay_sum"] - df["grade_index"]
        adjusted_count = df["essay_count"] - 1
        loo_mean = np.where(adjusted_count > 0, adjusted_sum / adjusted_count, df["grade_index"])
        df = df.drop(columns=["essay_sum", "essay_count"])
        df["grade_index_essay_mean"] = loo_mean
    else:
        essay_mean = essay_group.mean()
        df = df.join(essay_mean.rename("grade_index_essay_mean"), on="essay_id")

    df["deviation"] = df["grade_index"] - df["grade_index_essay_mean"]
    return df


def compute_rater_weights(
    ratings: pd.DataFrame,
    grade_to_index: Dict[str, int],
    config: RaterSeverityConfig | None = None,
    *,
    use_loo_alignment: bool = False,
) -> Tuple[Dict[str, float], pd.DataFrame]:
    """Return per-rater weights and diagnostics."""

    if ratings.empty:
        empty = pd.DataFrame(
            columns=[
                "rater_id",
                "weight",
                "n_rated",
                "rms_alignment",
                "mad_alignment",
                "mean_grade_index",
                "std_grade_index",
                "min_grade_index",
                "max_grade_index",
                "grade_range",
                "unique_grades",
            ]
        )
        return {}, empty

    cfg = config or RaterSeverityConfig()
    aligned = _prepare_alignment_frame(ratings, grade_to_index, use_loo_alignment=use_loo_alignment)
    if aligned.empty:
        empty = pd.DataFrame(
            columns=[
                "rater_id",
                "weight",
                "n_rated",
                "rms_alignment",
                "mad_alignment",
                "mean_grade_index",
                "std_grade_index",
                "min_grade_index",
                "max_grade_index",
                "grade_range",
                "unique_grades",
            ]
        )
        return {}, empty

    counts = aligned.groupby("rater_id").size().astype(float)
    count_weight = counts / (counts + cfg.count_scale)

    deviations = aligned["deviation"]
    rms_alignment = (
        aligned.assign(dev_sq=deviations**2).groupby("rater_id")["dev_sq"].mean().pipe(np.sqrt)
    )
    mad_alignment = aligned.assign(abs_dev=deviations.abs()).groupby("rater_id")["abs_dev"].mean()

    alignment_weight = 1.0 / (1.0 + cfg.alignment_scale * rms_alignment)

    grade_group = aligned.groupby("rater_id")["grade_index"]
    mean_grade = grade_group.mean()
    std_grade = grade_group.std(ddof=0).fillna(0.0)
    min_grade = grade_group.min()
    max_grade = grade_group.max()
    grade_range = max_grade - min_grade
    unique_grades = grade_group.nunique()

    raw_weight = count_weight * alignment_weight
    raw_weight = raw_weight.fillna(0.0)
    if raw_weight.max() > 0:
        raw_weight = raw_weight / raw_weight.max()
    weights = raw_weight.clip(lower=cfg.min_weight)

    metrics = pd.DataFrame(
        {
            "rater_id": counts.index,
            "weight": weights[counts.index],
            "n_rated": counts[counts.index],
            "rms_alignment": rms_alignment.reindex(counts.index).fillna(0.0),
            "mad_alignment": mad_alignment.reindex(counts.index).fillna(0.0),
            "mean_grade_index": mean_grade.reindex(counts.index).fillna(0.0),
            "std_grade_index": std_grade.reindex(counts.index).fillna(0.0),
            "min_grade_index": min_grade.reindex(counts.index).fillna(0.0),
            "max_grade_index": max_grade.reindex(counts.index).fillna(0.0),
            "grade_range": grade_range.reindex(counts.index).fillna(0.0),
            "unique_grades": unique_grades.reindex(counts.index).fillna(0.0),
        }
    ).reset_index(drop=True)

    return weights.to_dict(), metrics


def compute_rater_bias_posteriors_eb(
    ratings: pd.DataFrame,
    grade_to_index: Dict[str, int],
    *,
    min_sigma2: float = 1e-6,
    min_tau2: float = 1e-6,
    use_loo_alignment: bool = False,
) -> pd.DataFrame:
    """Estimate empirical-Bayes rater bias posteriors on the grade-index scale."""

    columns = [
        "rater_id",
        "n_rated",
        "b_data",
        "se2",
        "tau2",
        "shrinkage",
        "mu_post",
        "var_post",
        "sigma2_used",
    ]

    if ratings.empty:
        return pd.DataFrame(columns=columns)

    aligned = _prepare_alignment_frame(ratings, grade_to_index, use_loo_alignment=use_loo_alignment)
    if aligned.empty:
        return pd.DataFrame(columns=columns)

    grouped = aligned.groupby("rater_id")
    counts = grouped.size().astype(float)
    b_data = grouped["deviation"].mean()

    sigma2 = float(aligned["deviation"].var(ddof=0)) if len(aligned) > 1 else 0.0
    if np.isnan(sigma2) or sigma2 < min_sigma2:
        sigma2 = min_sigma2

    se2 = sigma2 / counts.replace(0.0, np.nan)
    se2 = se2.fillna(np.inf)

    var_b = float(b_data.var(ddof=0)) if len(b_data) > 1 else 0.0
    if np.isnan(var_b):
        var_b = 0.0

    mean_se2 = float(se2.replace(np.inf, 0.0).mean()) if len(se2) > 0 else 0.0
    tau2 = max(var_b - mean_se2, min_tau2)

    shrinkage = tau2 / (tau2 + se2)
    shrinkage = shrinkage.replace({np.inf: 0.0}).fillna(0.0)

    mu_post = shrinkage * b_data
    var_post = (tau2 * se2) / (tau2 + se2)
    var_post = var_post.replace({np.inf: tau2})

    result = pd.DataFrame(
        {
            "rater_id": counts.index,
            "n_rated": counts[counts.index],
            "b_data": b_data.reindex(counts.index).fillna(0.0),
            "se2": se2.reindex(counts.index).fillna(np.inf),
            "tau2": tau2,
            "shrinkage": shrinkage.reindex(counts.index).fillna(0.0),
            "mu_post": mu_post.reindex(counts.index).fillna(0.0),
            "var_post": var_post.reindex(counts.index).fillna(tau2),
            "sigma2_used": sigma2,
        }
    ).reset_index(drop=True)

    return result[columns]


def apply_precision_weights(
    weights: Dict[str, float],
    bias_posteriors: pd.DataFrame,
    *,
    epsilon: float = 1e-6,
) -> Tuple[Dict[str, float], pd.DataFrame]:
    """Scale rater weights by posterior precision and report multipliers."""

    if not weights:
        empty = pd.DataFrame(columns=["rater_id", "precision_factor"])
        return {}, empty

    if bias_posteriors.empty:
        factors = pd.DataFrame(
            {
                "rater_id": list(weights.keys()),
                "precision_factor": [1.0] * len(weights),
            }
        )
        return dict(weights), factors

    se2_series = bias_posteriors.set_index("rater_id")["se2"].astype(float)
    precision_raw = 1.0 / (se2_series + epsilon)
    precision_raw = precision_raw.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    max_precision = float(precision_raw.max())
    if max_precision > 0:
        precision_norm = precision_raw / max_precision
    else:
        precision_norm = precision_raw.fillna(0.0)

    bias_abs = bias_posteriors.set_index("rater_id")["mu_post"].abs()

    factors = {}
    for rater, base_weight in weights.items():
        factor = float(precision_norm.get(rater, 1.0))
        if not np.isfinite(factor) or factor <= 0.0:
            factor = epsilon
        bias_penalty = float(1.0 / (1.0 + bias_abs.get(rater, 0.0)))
        factor *= bias_penalty
        factors[rater] = factor

    adjusted = {rater: base_weight * factors[rater] for rater, base_weight in weights.items()}
    precision_factors = pd.DataFrame(
        {
            "rater_id": list(factors.keys()),
            "precision_factor": [float(factors[r]) for r in factors],
        }
    )

    return adjusted, precision_factors

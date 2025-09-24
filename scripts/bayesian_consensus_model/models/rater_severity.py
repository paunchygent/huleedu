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


def compute_rater_weights(
    ratings: pd.DataFrame,
    grade_to_index: Dict[str, int],
    config: RaterSeverityConfig | None = None,
) -> Tuple[Dict[str, float], pd.DataFrame]:
    """Return per-rater weights and diagnostics."""

    if ratings.empty:
        empty = pd.DataFrame(columns=[
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
        ])
        return {}, empty

    cfg = config or RaterSeverityConfig()

    df = ratings.copy()
    df["grade_index"] = df["grade"].map(grade_to_index)

    counts = df.groupby("rater_id").size().astype(float)
    count_weight = counts / (counts + cfg.count_scale)

    essay_means = df.groupby("essay_id")["grade_index"].mean()
    df = df.join(essay_means, on="essay_id", rsuffix="_essay_mean")

    deviations = df["grade_index"] - df["grade_index_essay_mean"]
    rms_alignment = (
        df.assign(dev_sq=deviations**2)
        .groupby("rater_id")["dev_sq"]
        .mean()
        .pipe(np.sqrt)
    )
    mad_alignment = (
        df.assign(abs_dev=deviations.abs())
        .groupby("rater_id")["abs_dev"]
        .mean()
    )

    alignment_weight = 1.0 / (1.0 + cfg.alignment_scale * rms_alignment)

    grade_group = df.groupby("rater_id")["grade_index"]
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
) -> pd.DataFrame:
    """Estimate empirical-Bayes rater bias posteriors on the grade-index scale.

    Returns a DataFrame with posterior summaries per rater, including the
    shrinkage-adjusted bias mean ("mu_post") that should be subtracted from the
    rater's grade indices. All values are expressed on the integer grade index
    scale used by the kernel smoother."""

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

    df = ratings.copy()
    df["grade_index"] = df["grade"].map(grade_to_index).astype(float)
    df = df.dropna(subset=["grade_index"])
    if df.empty:
        return pd.DataFrame(columns=columns)

    essay_means = df.groupby("essay_id")["grade_index"].mean()
    df = df.join(essay_means, on="essay_id", rsuffix="_essay_mean")
    df["deviation"] = df["grade_index"] - df["grade_index_essay_mean"]

    grouped = df.groupby("rater_id")
    counts = grouped.size().astype(float)
    b_data = grouped["deviation"].mean()

    sigma2 = float(df["deviation"].var(ddof=0)) if len(df) > 1 else 0.0
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

    result = pd.DataFrame({
        "rater_id": counts.index,
        "n_rated": counts[counts.index],
        "b_data": b_data.reindex(counts.index).fillna(0.0),
        "se2": se2.reindex(counts.index).fillna(np.inf),
        "tau2": tau2,
        "shrinkage": shrinkage.reindex(counts.index).fillna(0.0),
        "mu_post": mu_post.reindex(counts.index).fillna(0.0),
        "var_post": var_post.reindex(counts.index).fillna(tau2),
        "sigma2_used": sigma2,
    }).reset_index(drop=True)

    return result[columns]

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

"""Consensus via expected grade index with Gaussian smoothing for confidence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

import numpy as np
import pandas as pd

from .rater_severity import (
    RaterSeverityConfig,
    compute_rater_bias_posteriors_eb,
    compute_rater_weights,
)

GRADES: tuple[str, ...] = (
    "F",
    "F+",
    "E-",
    "E+",
    "D-",
    "D+",
    "C-",
    "C+",
    "B",
    "A",
)
GRADE_TO_INDEX = {grade: idx for idx, grade in enumerate(GRADES)}
INDEX_TO_GRADE = {idx: grade for grade, idx in GRADE_TO_INDEX.items()}
INDICES = np.arange(len(GRADES), dtype=float)


def _gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return np.eye(size, dtype=float)
    grid = np.arange(size, dtype=float)
    kernel = np.zeros((size, size), dtype=float)
    for idx in range(size):
        weights = np.exp(-0.5 * ((grid - idx) / sigma) ** 2)
        kernel[idx] = weights / weights.sum()
    return kernel


def _fractional_kernel_row(kernel: np.ndarray, position: float) -> np.ndarray:
    """Linearly interpolate the kernel row for a fractional grade index."""

    max_idx = kernel.shape[0] - 1
    if position <= 0.0:
        return kernel[0]
    if position >= max_idx:
        return kernel[max_idx]
    lower = int(np.floor(position))
    upper = int(np.ceil(position))
    if lower == upper:
        return kernel[lower]
    frac = position - lower
    return (1.0 - frac) * kernel[lower] + frac * kernel[upper]


@dataclass
class KernelConfig:
    sigma: float = 0.85
    pseudo_count: float = 0.02
    severity: RaterSeverityConfig | None = None
    bias_correction: bool = True


class OrdinalKernelModel:
    def __init__(self, config: KernelConfig | None = None) -> None:
        self.config = config or KernelConfig()
        self._expected_index: Dict[str, float] = {}
        self._probabilities: Dict[str, np.ndarray] = {}
        self._sample_sizes: Dict[str, int] = {}
        self._rater_metrics: pd.DataFrame | None = None
        self._rater_bias_posteriors: pd.DataFrame | None = None

    @staticmethod
    def prepare_data(ratings: pd.DataFrame) -> pd.DataFrame:
        required = {"essay_id", "rater_id", "grade"}
        missing = required - set(ratings.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        df = ratings.copy()
        df["grade"] = df["grade"].astype(str).str.strip().str.upper()
        df = df[df["grade"].isin(GRADES)]
        if df.empty:
            raise ValueError("No valid grades supplied")
        return df.reset_index(drop=True)

    def fit(self, ratings: pd.DataFrame) -> None:
        cleaned = self.prepare_data(ratings)
        kernel = _gaussian_kernel(len(GRADES), self.config.sigma)
        weights, metrics = compute_rater_weights(cleaned, GRADE_TO_INDEX, self.config.severity)
        self._rater_metrics = metrics
        bias_df = compute_rater_bias_posteriors_eb(cleaned, GRADE_TO_INDEX)
        bias_df = bias_df.copy()
        bias_df["applied"] = self.config.bias_correction
        self._rater_bias_posteriors = bias_df
        if self.config.bias_correction and not bias_df.empty:
            bias_lookup = bias_df.set_index("rater_id")["mu_post"].to_dict()
        else:
            bias_lookup = {rater: 0.0 for rater in cleaned["rater_id"].unique()}
        self._expected_index.clear()
        self._probabilities.clear()
        self._sample_sizes.clear()

        base = np.full(len(GRADES), self.config.pseudo_count, dtype=float)
        max_idx = len(GRADES) - 1

        for essay_id, group in cleaned.groupby("essay_id"):
            expected_sum = 0.0
            total_weight = 0.0
            smoothed = base.copy()

            for _, row in group.iterrows():
                grade = row["grade"]
                idx = GRADE_TO_INDEX[grade]
                weight = weights.get(row["rater_id"], 1.0)
                bias_shift = float(bias_lookup.get(row["rater_id"], 0.0))
                adjusted_idx = float(idx) - bias_shift
                smoothed += weight * _fractional_kernel_row(kernel, adjusted_idx)
                expected_sum += weight * float(np.clip(adjusted_idx, 0.0, max_idx))
                total_weight += weight

            if total_weight == 0.0:
                continue
            expected_idx = float(expected_sum / total_weight)
            self._expected_index[essay_id] = expected_idx

            probs = smoothed / smoothed.sum()
            self._probabilities[essay_id] = probs
            self._sample_sizes[essay_id] = int(group.shape[0])

    @property
    def rater_metrics(self) -> pd.DataFrame:
        if self._rater_metrics is None:
            raise ValueError("Model must be fitted before accessing rater metrics")
        return self._rater_metrics.copy()

    @property
    def rater_bias_posteriors(self) -> pd.DataFrame:
        if self._rater_bias_posteriors is None:
            raise ValueError("Model must be fitted before accessing rater bias posteriors")
        return self._rater_bias_posteriors.copy()

    def consensus(self) -> Dict[str, Dict[str, float | Dict[str, float]]]:
        if not self._probabilities:
            raise ValueError("Model must be fitted before requesting consensus")

        results: Dict[str, Dict[str, float | Dict[str, float]]] = {}
        for essay_id, probs in self._probabilities.items():
            expected_index = self._expected_index[essay_id]
            consensus_idx = int(np.clip(round(expected_index), 0, len(GRADES) - 1))
            consensus_grade = INDEX_TO_GRADE[consensus_idx]
            confidence = float(probs[consensus_idx])
            results[essay_id] = {
                "consensus_grade": consensus_grade,
                "confidence": confidence,
                "probabilities": {grade: float(prob) for grade, prob in zip(GRADES, probs)},
                "sample_size": self._sample_sizes[essay_id],
                "expected_grade_index": expected_index,
            }
        return results

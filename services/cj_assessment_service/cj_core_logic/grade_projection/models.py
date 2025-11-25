from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Tuple

import numpy as np
from common_core.grade_scales import GradeScaleMetadata


@dataclass(frozen=True)
class ScaleConfiguration:
    """Runtime configuration derived from grade scale metadata."""

    metadata: GradeScaleMetadata
    anchor_grades: list[str]
    population_priors: dict[str, float]
    minus_enabled_for: set[str]
    plus_enabled_for: set[str]
    allows_below_lowest: bool
    below_lowest_grade: str | None

    @property
    def scale_id(self) -> str:
        return self.metadata.scale_id


@dataclass
class GradeDistribution:
    """Parameters for a grade's score distribution."""

    mean: float
    variance: float
    n_anchors: int
    prior: float = 0.0667  # Default: 1/15 for uniform prior

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)


class CalibrationResult:
    """Result of grade calibration from anchor essays."""

    def __init__(
        self,
        is_valid: bool,
        grade_params: Dict[str, GradeDistribution] | None = None,
        grade_boundaries: Dict[str, Tuple[float, float]] | None = None,
        pooled_variance: float | None = None,
        error_reason: str | None = None,
        anchor_grades: list[str] | None = None,
        scale_id: str | None = None,
    ):
        self.is_valid = is_valid
        self.grade_params = grade_params or {}
        self.grade_boundaries = grade_boundaries or {}
        self.pooled_variance = pooled_variance
        self.error_reason = error_reason
        self.anchor_grades = anchor_grades or list(self.grade_params.keys())
        self.scale_id = scale_id

    @property
    def grade_centers(self) -> dict[str, float]:
        """Get grade center points (means)."""
        return {grade: params.mean for grade, params in self.grade_params.items()}

    @property
    def grade_boundaries_dict(self) -> dict[str, tuple[float, float]]:
        """Get boundaries as string keys for JSON serialization."""
        result = {}
        for grade, (lower, upper) in self.grade_boundaries.items():
            json_lower = -1e10 if lower == -np.inf else lower
            json_upper = 1e10 if upper == np.inf else upper
            result[grade] = (json_lower, json_upper)
        return result


class ProjectionsData:
    """Container for computed grade projections."""

    def __init__(
        self,
        primary_grades: dict[str, str],
        anchor_primary_grades: dict[str, str],
        confidence_labels: dict[str, str],
        confidence_scores: dict[str, float],
        grade_probabilities: dict[str, dict[str, float]],
        bt_stats: dict[str, dict[str, float]],
    ):
        self.primary_grades = primary_grades
        self.anchor_primary_grades = anchor_primary_grades
        self.confidence_labels = confidence_labels
        self.confidence_scores = confidence_scores
        self.grade_probabilities = grade_probabilities
        self.bt_stats = bt_stats

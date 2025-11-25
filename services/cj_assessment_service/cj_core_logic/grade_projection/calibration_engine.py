from __future__ import annotations

from typing import Any
from uuid import UUID

import numpy as np
from huleedu_service_libs.logging_utils import create_service_logger
from sklearn.isotonic import IsotonicRegression

from services.cj_assessment_service.cj_core_logic.grade_projection.models import (
    CalibrationResult,
    GradeDistribution,
    ScaleConfiguration,
)

logger = create_service_logger("cj_assessment.calibration_engine")


class CalibrationEngine:
    """Compute grade calibration from anchor essays."""

    def __init__(
        self, *, min_anchors_for_empirical: int = 3, min_anchors_for_variance: int = 5
    ) -> None:
        self.min_anchors_for_empirical = min_anchors_for_empirical
        self.min_anchors_for_variance = min_anchors_for_variance

    def calibrate(
        self,
        anchors: list[dict[str, Any]],
        anchor_grades: dict[str, str],
        correlation_id: UUID,
        *,
        scale_config: ScaleConfiguration,
    ) -> CalibrationResult:
        anchors_by_grade = self._group_anchors_by_grade(anchors, anchor_grades, scale_config)
        all_scores = [score for scores in anchors_by_grade.values() for score in scores]
        pooled_variance = float(np.var(all_scores)) if len(all_scores) > 1 else 0.1

        grade_params: dict[str, GradeDistribution] = {}
        for grade in scale_config.anchor_grades:
            n_anchors = len(anchors_by_grade.get(grade, []))
            if n_anchors >= self.min_anchors_for_empirical:
                mean = float(np.mean(anchors_by_grade[grade]))
                variance = float(np.var(anchors_by_grade[grade]))
            elif n_anchors > 0:
                empirical_mean = float(np.mean(anchors_by_grade[grade]))
                expected_position = self._get_expected_grade_position(
                    grade, scale_config.anchor_grades
                )
                weight = n_anchors / self.min_anchors_for_empirical
                mean = weight * empirical_mean + (1 - weight) * expected_position
                variance = pooled_variance * (self.min_anchors_for_empirical / n_anchors)
            else:
                mean = self._get_expected_grade_position(grade, scale_config.anchor_grades)
                variance = pooled_variance * 2.0
                logger.warning(
                    "Grade %s has no anchors, using expected position %.3f",
                    grade,
                    mean,
                    extra={"correlation_id": str(correlation_id), "grade": grade},
                )

            grade_params[grade] = GradeDistribution(
                mean=mean,
                variance=max(variance, 0.01),
                n_anchors=n_anchors,
                prior=scale_config.population_priors.get(
                    grade, 1.0 / len(scale_config.anchor_grades)
                ),
            )

        grade_params = self._apply_isotonic_constraint(grade_params, scale_config.anchor_grades)
        grade_boundaries = self._calculate_grade_boundaries(
            grade_params, scale_config.anchor_grades
        )

        return CalibrationResult(
            is_valid=True,
            grade_params=grade_params,
            grade_boundaries=grade_boundaries,
            pooled_variance=pooled_variance,
            anchor_grades=scale_config.anchor_grades,
            scale_id=scale_config.scale_id,
        )

    def _group_anchors_by_grade(
        self,
        anchors: list[dict[str, Any]],
        anchor_grades: dict[str, str],
        scale_config: ScaleConfiguration,
    ) -> dict[str, list[float]]:
        anchors_by_grade: dict[str, list[float]] = {}
        for anchor in anchors:
            if anchor["els_essay_id"] in anchor_grades:
                grade = anchor_grades[str(anchor["els_essay_id"])]
                if grade in scale_config.anchor_grades:
                    bt_score = float(anchor.get("bradley_terry_score", 0.0))
                    anchors_by_grade.setdefault(grade, []).append(bt_score)
        return anchors_by_grade

    def _get_expected_grade_position(self, grade: str, anchor_grades: list[str]) -> float:
        try:
            index = anchor_grades.index(grade)
            return (index + 0.5) / len(anchor_grades)
        except ValueError:
            return 0.5

    def _apply_isotonic_constraint(
        self,
        grade_params: dict[str, GradeDistribution],
        anchor_grades: list[str],
    ) -> dict[str, GradeDistribution]:
        means = np.array([grade_params[g].mean for g in anchor_grades])
        iso_reg = IsotonicRegression(increasing=True)
        corrected_means = iso_reg.fit_transform(np.arange(len(anchor_grades)), means)
        for i, grade in enumerate(anchor_grades):
            grade_params[grade].mean = corrected_means[i]
        return grade_params

    def _calculate_grade_boundaries(
        self,
        grade_params: dict[str, GradeDistribution],
        anchor_grades: list[str],
    ) -> dict[str, tuple[float, float]]:
        boundaries: dict[str, tuple[float, float]] = {}
        for i, grade in enumerate(anchor_grades):
            lower_bound = (
                -np.inf
                if i == 0
                else (grade_params[anchor_grades[i - 1]].mean + grade_params[grade].mean) / 2
            )
            if i == len(anchor_grades) - 1:
                upper_bound = np.inf
            else:
                next_grade = anchor_grades[i + 1]
                upper_bound = (grade_params[grade].mean + grade_params[next_grade].mean) / 2
            boundaries[grade] = (lower_bound, upper_bound)
        return boundaries

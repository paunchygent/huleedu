from __future__ import annotations

import math
from typing import Any
from uuid import UUID

import numpy as np

from services.cj_assessment_service.cj_core_logic.grade_projection.models import (
    CalibrationResult,
    ProjectionsData,
    ScaleConfiguration,
)


class ProjectionEngine:
    """Compute per-student grade projections from calibration inputs."""

    def compute_student_projections(
        self,
        students: list[dict[str, Any]],
        calibration: CalibrationResult,
        correlation_id: UUID,
        *,
        scale_config: ScaleConfiguration,
    ) -> ProjectionsData:
        primary_grades: dict[str, str] = {}
        anchor_primary_grades: dict[str, str] = {}
        confidence_labels: dict[str, str] = {}
        confidence_scores: dict[str, float] = {}
        grade_probabilities: dict[str, dict[str, float]] = {}
        bt_stats: dict[str, dict[str, float]] = {}

        for student in students:
            essay_id = str(student["els_essay_id"])
            bt_score = float(student.get("bradley_terry_score", 0.0))
            bt_se = float(student.get("bradley_terry_se", 0.1))

            probs = self._compute_grade_probabilities(
                bt_score,
                bt_se,
                calibration,
                scale_config=scale_config,
            )
            primary_anchor_grade = max(probs.items(), key=lambda item: item[1])[0]
            anchor_primary_grades[essay_id] = primary_anchor_grade

            final_grade = self._assign_final_grade(
                bt_score,
                primary_anchor_grade,
                calibration,
                scale_config=scale_config,
            )

            entropy = self._compute_normalized_entropy(probs)
            conf_score, conf_label = self._entropy_to_confidence(entropy)

            primary_grades[essay_id] = final_grade
            confidence_labels[essay_id] = conf_label
            confidence_scores[essay_id] = conf_score
            grade_probabilities[essay_id] = probs
            bt_stats[essay_id] = {"bt_mean": bt_score, "bt_se": bt_se}

        return ProjectionsData(
            primary_grades=primary_grades,
            anchor_primary_grades=anchor_primary_grades,
            confidence_labels=confidence_labels,
            confidence_scores=confidence_scores,
            grade_probabilities=grade_probabilities,
            bt_stats=bt_stats,
        )

    def _assign_final_grade(
        self,
        bt_score: float,
        primary_grade: str,
        calibration: CalibrationResult,
        *,
        scale_config: ScaleConfiguration,
    ) -> str:
        grade_boundaries = calibration.grade_boundaries
        lower_bound, upper_bound = grade_boundaries[primary_grade]
        grade_width = upper_bound - lower_bound
        relative_position = (
            (bt_score - lower_bound) / grade_width
            if math.isfinite(grade_width) and grade_width > 0
            else 0.5
        )

        if scale_config.scale_id == "swedish_8_anchor":
            if primary_grade in {"F", "D+", "C+"}:
                return primary_grade
            if primary_grade in scale_config.minus_enabled_for and relative_position < 0.25:
                return f"{primary_grade}-"
            if primary_grade in scale_config.plus_enabled_for and relative_position > 0.75:
                return f"{primary_grade}+"
            return primary_grade

        if (
            scale_config.allows_below_lowest
            and scale_config.below_lowest_grade
            and primary_grade == scale_config.anchor_grades[0]
        ):
            lowest_params = calibration.grade_params[primary_grade]
            threshold = lowest_params.mean - (2 * lowest_params.std)
            if bt_score < threshold:
                return scale_config.below_lowest_grade

        return primary_grade

    def _compute_grade_probabilities(
        self,
        bt_score: float,
        bt_se: float,
        calibration: CalibrationResult,
        *,
        scale_config: ScaleConfiguration,
    ) -> dict[str, float]:
        log_probs: dict[str, float] = {}
        for grade in calibration.anchor_grades:
            params = calibration.grade_params[grade]
            if grade in calibration.grade_boundaries:
                lower, upper = calibration.grade_boundaries[grade]
                if not (lower <= bt_score <= upper):
                    log_probs[grade] = -np.inf
                    continue

            combined_variance = params.variance + bt_se**2
            log_likelihood = -0.5 * (
                np.log(2 * np.pi * combined_variance)
                + (bt_score - params.mean) ** 2 / combined_variance
            )
            prior = scale_config.population_priors.get(grade, params.prior)
            log_prior = np.log(prior) if prior > 0 else -np.inf
            log_probs[grade] = log_likelihood + log_prior

        return self._normalize_log_probs(log_probs)

    def _normalize_log_probs(self, log_probs: dict[str, float]) -> dict[str, float]:
        max_log = max(log_probs.values())
        probs: dict[str, float] = {}
        for grade, log_prob in log_probs.items():
            probs[grade] = 0.0 if log_prob == -np.inf else np.exp(log_prob - max_log)

        total = sum(probs.values())
        if total > 0:
            for grade in probs:
                probs[grade] /= total
        else:
            count = len(probs) if probs else 1
            uniform = 1.0 / count
            for grade in probs:
                probs[grade] = uniform
        return probs

    def _compute_normalized_entropy(self, probs: dict[str, float]) -> float:
        nonzero_probs = [p for p in probs.values() if p > 1e-10]
        if len(nonzero_probs) <= 1:
            return 0.0
        entropy = -sum(p * math.log(p) for p in nonzero_probs)
        max_entropy = math.log(len(probs)) if probs else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _entropy_to_confidence(self, normalized_entropy: float) -> tuple[float, str]:
        confidence_score = 1.0 - normalized_entropy
        if normalized_entropy < 0.5:
            label = "HIGH"
        elif normalized_entropy < 0.75:
            label = "MID"
        else:
            label = "LOW"
        return confidence_score, label

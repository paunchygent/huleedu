"""
Grade projection module for CJ Assessment Service.

This module calculates predicted grades based on CJ rankings and anchor essays,
using statistical methods to map Bradley-Terry scores to grade boundaries with
confidence scoring based on probability distributions.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any
from uuid import UUID

import numpy as np
from common_core.events.cj_assessment_events import GradeProjectionSummary
from huleedu_service_libs.logging_utils import create_service_logger
from scipy.stats import norm
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.context_builder import (
    AssessmentContext,
    ContextBuilder,
)
from services.cj_assessment_service.models_db import (
    GradeProjection,
)
from services.cj_assessment_service.protocols import ContentClientProtocol

if TYPE_CHECKING:
    pass

logger = create_service_logger("cj_assessment.grade_projector")


class GradeProjector:
    """Main grade projection logic with anchor-based calibration.

    Uses anchor essays with known grades to establish grade boundaries,
    then computes probability distributions over grades for each student essay
    based on their Bradley-Terry score and standard error.
    """

    # Standard 5-grade system used in the HuleEdu platform
    GRADE_ORDER = ["F", "D", "C", "B", "A"]

    # Minimum anchors per grade for reliable calibration
    MIN_ANCHORS_PER_GRADE = 2

    # Regularization strength for variance pooling (0=no pooling, 1=full pooling)
    VARIANCE_REGULARIZATION = 0.3

    def __init__(self) -> None:
        self.context_builder = ContextBuilder(min_anchors_required=0)
        self.logger = logger

    async def calculate_projections(
        self,
        session: AsyncSession,
        rankings: list[dict[str, Any]],
        cj_batch_id: int,
        assignment_id: str | None,
        course_code: str,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
    ) -> GradeProjectionSummary:
        """Calculate grade projections with anchor-based calibration.

        Args:
            session: Database session for queries and persistence
            rankings: List of essay rankings from CJ assessment
            cj_batch_id: Internal CJ batch ID for storing projections
            assignment_id: Optional assignment ID for context
            course_code: Course code for fallback context
            content_client: Client for fetching anchor content
            correlation_id: Request correlation ID

        Returns:
            GradeProjectionSummary with grades, probabilities, and confidence
        """
        self.logger.info(
            "Starting grade projection calculation",
            extra={
                "correlation_id": str(correlation_id),
                "cj_batch_id": cj_batch_id,
                "essay_count": len(rankings),
                "assignment_id": assignment_id,
            },
        )

        if not rankings:
            return self._empty_projections(available=False)

        # Build assessment context (instructions and anchors)
        context = await self.context_builder.build(
            session=session,
            assignment_id=assignment_id,
            course_code=course_code,
            content_client=content_client,
            correlation_id=correlation_id,
        )

        # Split essays into anchors and students
        anchors = [r for r in rankings if r.get("is_anchor") is True]
        students = [r for r in rankings if not r.get("is_anchor")]

        # Check if we have sufficient anchors for calibration
        if not anchors:
            self.logger.info(
                "No anchor essays available - skipping grade projection",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "context_source": context.context_source,
                },
            )
            return self._empty_projections(available=False)

        # Map anchor essay IDs to their known grades
        anchor_grades = self._map_anchor_grades(anchors, context)

        # Check if we have sufficient grade coverage
        unique_grades = set(anchor_grades.values())
        if len(unique_grades) < 2:
            self.logger.warning(
                f"Insufficient grade diversity in anchors: {unique_grades}",
                extra={
                    "correlation_id": str(correlation_id),
                    "unique_grades": list(unique_grades),
                },
            )
            return self._empty_projections(available=False)

        # Compute grade calibration from anchor essays
        calibration = self._calibrate_from_anchors(anchors, anchor_grades, correlation_id)

        if not calibration.is_valid:
            self.logger.error(
                "Failed to compute valid calibration from anchors",
                extra={
                    "correlation_id": str(correlation_id),
                    "reason": calibration.error_reason,
                },
            )
            return self._empty_projections(available=False)

        # Calculate projections for each student essay
        projections_data = self._compute_student_projections(students, calibration, correlation_id)

        # Store projections in database
        await self._store_projections(
            session,
            cj_batch_id,
            projections_data,
            calibration,
            context,
        )

        # Build and return summary
        return GradeProjectionSummary(
            projections_available=True,
            primary_grades=projections_data.primary_grades,
            confidence_labels=projections_data.confidence_labels,
            confidence_scores=projections_data.confidence_scores,
            grade_probabilities=projections_data.grade_probabilities,
            calibration_info={
                "grade_centers": calibration.grade_centers,
                "grade_boundaries": calibration.grade_boundaries_dict,
                "context_source": context.context_source,
                "anchor_count": len(anchors),
                "anchor_grades": list(unique_grades),
            },
            bt_stats=projections_data.bt_stats,
        )

    def _map_anchor_grades(
        self,
        anchors: list[dict[str, Any]],
        context: AssessmentContext,
    ) -> dict[str, str]:
        """Map anchor essay IDs to their known grades.

        First tries to get grade from ranking metadata (if anchors were properly
        seeded with grades). Falls back to matching via context anchor references.
        """
        anchor_grades = {}

        # Build lookup from context anchor references
        context_grades = {}
        for ref in context.anchor_essay_refs:
            # Anchor refs use text_storage_id, need to map to essay_id somehow
            # This assumes anchor essays store text_storage_id in their metadata
            context_grades[ref.text_storage_id] = ref.grade

        for anchor in anchors:
            essay_id = anchor["els_essay_id"]

            # First try: get grade from ranking metadata (preferred)
            if "anchor_grade" in anchor and anchor["anchor_grade"]:
                anchor_grades[essay_id] = anchor["anchor_grade"]
                continue

            # Second try: match via content_id if available
            # This assumes anchors have content_id in their processing metadata
            # In practice, this mapping should be established when seeding anchors
            self.logger.warning(
                f"Anchor {essay_id} missing grade in metadata, calibration may be incomplete",
                extra={"essay_id": essay_id},
            )

        return anchor_grades

    def _calibrate_from_anchors(
        self,
        anchors: list[dict[str, Any]],
        anchor_grades: dict[str, str],
        correlation_id: UUID,
    ) -> CalibrationResult:
        """Compute grade calibration using Gaussian mixture model.

        Models each grade as a Gaussian distribution of BT scores,
        with variance regularization for stability when few anchors.
        """
        # Group anchors by grade
        anchors_by_grade: dict[str, list[dict[str, Any]]] = {grade: [] for grade in self.GRADE_ORDER}

        for anchor in anchors:
            essay_id = anchor["els_essay_id"]
            if essay_id in anchor_grades:
                grade = anchor_grades[essay_id]
                if grade in anchors_by_grade:
                    bt_score = anchor.get("bradley_terry_score", 0.0)
                    bt_se = anchor.get("bradley_terry_se", 0.1)
                    anchors_by_grade[grade].append(
                        {
                            "score": bt_score,
                            "se": bt_se,
                            "id": essay_id,
                        }
                    )

        # Compute pooled variance for regularization
        all_scores = []
        for grade_anchors in anchors_by_grade.values():
            all_scores.extend([a["score"] for a in grade_anchors])

        if len(all_scores) < 2:
            return CalibrationResult(
                is_valid=False,
                error_reason="Insufficient anchor scores for variance estimation",
            )

        pooled_variance = float(np.var(all_scores))

        # Estimate grade parameters with regularization
        grade_params = {}
        for grade in self.GRADE_ORDER:
            grade_anchors = anchors_by_grade[grade]

            if len(grade_anchors) >= self.MIN_ANCHORS_PER_GRADE:
                # Sufficient anchors: use empirical mean and regularized variance
                scores = [a["score"] for a in grade_anchors]
                mean = float(np.mean(scores))
                empirical_var = float(np.var(scores)) if len(scores) > 1 else pooled_variance

                # Regularize variance toward pooled estimate
                variance = (
                    self.VARIANCE_REGULARIZATION * pooled_variance
                    + (1 - self.VARIANCE_REGULARIZATION) * empirical_var
                )

                grade_params[grade] = GradeDistribution(
                    mean=mean,
                    variance=max(variance, 0.01),  # Ensure positive variance
                    n_anchors=len(grade_anchors),
                )
            elif len(grade_anchors) == 1:
                # Single anchor: use its score with pooled variance
                grade_params[grade] = GradeDistribution(
                    mean=grade_anchors[0]["score"],
                    variance=pooled_variance,
                    n_anchors=1,
                )
            # Skip grades with no anchors

        # Compute grade boundaries as midpoints between adjacent grade means
        boundaries: dict[tuple[str, str], float] = {}
        prev_grade = None
        prev_mean = None

        for grade in self.GRADE_ORDER:
            if grade in grade_params:
                curr_mean = grade_params[grade].mean
                if prev_grade and prev_mean is not None:
                    # Midpoint between adjacent grades
                    boundaries[(prev_grade, grade)] = (prev_mean + curr_mean) / 2
                prev_grade = grade
                prev_mean = curr_mean

        # Validate monotonicity
        if not self._validate_monotonicity(grade_params, boundaries):
            self.logger.warning(
                "Non-monotonic grade centers detected, applying correction",
                extra={"correlation_id": str(correlation_id)},
            )
            boundaries = self._enforce_monotonicity(boundaries)

        return CalibrationResult(
            is_valid=True,
            grade_params=grade_params,
            grade_boundaries=boundaries,
            pooled_variance=pooled_variance,
        )

    def _validate_monotonicity(
        self,
        grade_params: dict[str, GradeDistribution],
        boundaries: dict[tuple[str, str], float],
    ) -> bool:
        """Check if grade centers are properly ordered (F < D < C < B < A)."""
        ordered_means = []
        for grade in self.GRADE_ORDER:
            if grade in grade_params:
                ordered_means.append(grade_params[grade].mean)

        # Check if means are strictly increasing
        for i in range(1, len(ordered_means)):
            if ordered_means[i] <= ordered_means[i - 1]:
                return False
        return True

    def _enforce_monotonicity(
        self,
        boundaries: dict[tuple[str, str], float],
    ) -> dict[tuple[str, str], float]:
        """Project boundaries to nearest monotonic sequence."""
        if not boundaries:
            return boundaries

        # Sort boundaries by their values
        sorted_items = sorted(boundaries.items(), key=lambda x: x[1])
        corrected = {}

        # Ensure each boundary is greater than the previous
        prev_val = float("-inf")
        for grade_pair, val in sorted_items:
            corrected_val = max(val, prev_val + 0.01)  # Minimum separation
            corrected[grade_pair] = corrected_val
            prev_val = corrected_val

        return corrected

    def _compute_student_projections(
        self,
        students: list[dict[str, Any]],
        calibration: CalibrationResult,
        correlation_id: UUID,
    ) -> ProjectionsData:
        """Compute grade probabilities and projections for student essays."""
        primary_grades = {}
        confidence_labels = {}
        confidence_scores = {}
        grade_probabilities = {}
        bt_stats = {}

        for student in students:
            essay_id = student["els_essay_id"]
            bt_score = float(student.get("bradley_terry_score", 0.0))
            bt_se = float(student.get("bradley_terry_se", 0.1))

            # Compute probability distribution over grades
            probs = self._compute_grade_probabilities(bt_score, bt_se, calibration)

            # Select primary grade (maximum probability)
            primary_grade = max(probs.items(), key=lambda x: x[1])[0]

            # Compute confidence from distribution entropy
            entropy = self._compute_normalized_entropy(probs)
            conf_score, conf_label = self._entropy_to_confidence(entropy)

            # Store results
            primary_grades[essay_id] = primary_grade
            confidence_labels[essay_id] = conf_label
            confidence_scores[essay_id] = conf_score
            grade_probabilities[essay_id] = probs
            bt_stats[essay_id] = {
                "bt_mean": bt_score,
                "bt_se": bt_se,
            }

        return ProjectionsData(
            primary_grades=primary_grades,
            confidence_labels=confidence_labels,
            confidence_scores=confidence_scores,
            grade_probabilities=grade_probabilities,
            bt_stats=bt_stats,
        )

    def _compute_grade_probabilities(
        self,
        bt_score: float,
        bt_se: float,
        calibration: CalibrationResult,
    ) -> dict[str, float]:
        """Compute probability distribution over grades using Normal CDF."""
        # Build grade intervals from boundaries
        intervals = self._build_grade_intervals(calibration.grade_boundaries)

        # Ensure positive standard error
        sigma = max(bt_se, 0.01)

        # Compute probability for each grade
        probs = {}
        for grade in self.GRADE_ORDER:
            if grade in intervals:
                lower, upper = intervals[grade]
                # P(grade) = P(lower < X < upper) where X ~ N(bt_score, sigma^2)
                p_upper = norm.cdf((upper - bt_score) / sigma)
                p_lower = norm.cdf((lower - bt_score) / sigma)
                prob = p_upper - p_lower
                probs[grade] = max(0.0, min(1.0, prob))  # Clamp to [0, 1]
            else:
                probs[grade] = 0.0

        # Normalize to sum to 1
        total = sum(probs.values())
        if total > 0:
            for grade in probs:
                probs[grade] /= total
        else:
            # Fallback: uniform distribution
            for grade in self.GRADE_ORDER:
                probs[grade] = 1.0 / len(self.GRADE_ORDER)

        return probs

    def _build_grade_intervals(
        self,
        boundaries: dict[tuple[str, str], float],
    ) -> dict[str, tuple[float, float]]:
        """Build grade intervals from pairwise boundaries."""
        intervals = {}

        for i, grade in enumerate(self.GRADE_ORDER):
            # Find lower boundary
            if i == 0:
                lower = float("-inf")
            else:
                prev_grade = self.GRADE_ORDER[i - 1]
                boundary_key = (prev_grade, grade)
                lower = boundaries.get(boundary_key, float("-inf"))

            # Find upper boundary
            if i == len(self.GRADE_ORDER) - 1:
                upper = float("inf")
            else:
                next_grade = self.GRADE_ORDER[i + 1]
                boundary_key = (grade, next_grade)
                upper = boundaries.get(boundary_key, float("inf"))

            intervals[grade] = (lower, upper)

        return intervals

    def _compute_normalized_entropy(self, probs: dict[str, float]) -> float:
        """Compute normalized Shannon entropy of probability distribution."""
        # Filter out zero probabilities
        nonzero_probs = [p for p in probs.values() if p > 1e-10]

        if len(nonzero_probs) <= 1:
            return 0.0  # No uncertainty if single outcome

        # Compute Shannon entropy
        entropy = -sum(p * math.log(p) for p in nonzero_probs)

        # Normalize by maximum possible entropy
        max_entropy = math.log(len(self.GRADE_ORDER))

        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _entropy_to_confidence(self, normalized_entropy: float) -> tuple[float, str]:
        """Convert normalized entropy to confidence score and label.

        Lower entropy = higher confidence (more peaked distribution)
        """
        # Invert entropy to get confidence
        confidence_score = 1.0 - normalized_entropy

        # Map to label based on thresholds
        if confidence_score >= 0.75:
            label = "HIGH"
        elif confidence_score >= 0.40:
            label = "MID"
        else:
            label = "LOW"

        return confidence_score, label

    async def _store_projections(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        projections_data: ProjectionsData,
        calibration: CalibrationResult,
        context: AssessmentContext,
    ) -> None:
        """Store grade projections in database."""
        projections = []

        for essay_id in projections_data.primary_grades:
            projection = GradeProjection(
                els_essay_id=essay_id,
                cj_batch_id=cj_batch_id,
                primary_grade=projections_data.primary_grades[essay_id],
                confidence_score=projections_data.confidence_scores[essay_id],
                confidence_label=projections_data.confidence_labels[essay_id],
                calculation_metadata={
                    "bt_mean": projections_data.bt_stats[essay_id]["bt_mean"],
                    "bt_se": projections_data.bt_stats[essay_id]["bt_se"],
                    "grade_probabilities": projections_data.grade_probabilities[essay_id],
                    "grade_centers": calibration.grade_centers,
                    "grade_boundaries": calibration.grade_boundaries_dict,
                    "context_source": context.context_source,
                    "calibration_method": "gaussian_mixture",
                },
            )
            projections.append(projection)

        if projections:
            session.add_all(projections)
            await session.flush()
            self.logger.info(f"Stored {len(projections)} grade projections")

    def _empty_projections(self, available: bool = False) -> GradeProjectionSummary:
        """Return empty projections summary."""
        return GradeProjectionSummary(
            projections_available=available,
            primary_grades={},
            confidence_labels={},
            confidence_scores={},
            grade_probabilities={},
            calibration_info={},
            bt_stats={},
        )


class GradeDistribution:
    """Parameters for a grade's score distribution."""

    def __init__(self, mean: float, variance: float, n_anchors: int):
        self.mean = mean
        self.variance = variance
        self.n_anchors = n_anchors
        self.std = math.sqrt(variance)


class CalibrationResult:
    """Result of grade calibration from anchor essays."""

    def __init__(
        self,
        is_valid: bool,
        grade_params: dict[str, GradeDistribution] | None = None,
        grade_boundaries: dict[tuple[str, str], float] | None = None,
        pooled_variance: float | None = None,
        error_reason: str | None = None,
    ):
        self.is_valid = is_valid
        self.grade_params = grade_params or {}
        self.grade_boundaries = grade_boundaries or {}
        self.pooled_variance = pooled_variance
        self.error_reason = error_reason

    @property
    def grade_centers(self) -> dict[str, float]:
        """Get grade center points (means)."""
        return {grade: params.mean for grade, params in self.grade_params.items()}

    @property
    def grade_boundaries_dict(self) -> dict[str, float]:
        """Get boundaries as string keys for JSON serialization."""
        return {f"{g1}_{g2}": value for (g1, g2), value in self.grade_boundaries.items()}


class ProjectionsData:
    """Container for computed grade projections."""

    def __init__(
        self,
        primary_grades: dict[str, str],
        confidence_labels: dict[str, str],
        confidence_scores: dict[str, float],
        grade_probabilities: dict[str, dict[str, float]],
        bt_stats: dict[str, dict[str, float]],
    ):
        self.primary_grades = primary_grades
        self.confidence_labels = confidence_labels
        self.confidence_scores = confidence_scores
        self.grade_probabilities = grade_probabilities
        self.bt_stats = bt_stats


def calculate_grade_projections(rankings: list[dict[str, Any]]) -> GradeProjectionSummary:
    """Legacy synchronous entry point for grade projections.

    This simplified version does not have access to anchor essays,
    so it returns empty projections with projections_available=False.
    For full functionality with anchor essays, use GradeProjector.calculate_projections().

    Args:
        rankings: List of essay rankings from CJ assessment

    Returns:
        GradeProjectionSummary with projections_available=False (no anchors)
    """
    # Without access to anchor essays, we cannot provide grade projections
    # This is the correct behavior - grades should only be assigned when
    # we have calibration data from anchor essays

    logger.info("Legacy grade projection called - no anchor essays available, skipping grading")

    return GradeProjectionSummary(
        projections_available=False,
        primary_grades={},
        confidence_labels={},
        confidence_scores={},
        grade_probabilities={},
        calibration_info={},
        bt_stats={},
    )

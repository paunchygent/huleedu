"""
Grade projection module for CJ Assessment Service.

This module calculates predicted grades based on CJ rankings and anchor essays,
using statistical methods to map Bradley-Terry scores to grade boundaries with
confidence scoring based on probability distributions.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import numpy as np
from common_core.events.cj_assessment_events import GradeProjectionSummary
from common_core.grade_scales import GradeScaleMetadata, get_scale, get_uniform_priors
from huleedu_service_libs.logging_utils import create_service_logger
from sklearn.isotonic import IsotonicRegression
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


class GradeProjector:
    """Main grade projection logic with anchor-based calibration.

    The projector resolves the active grade scale from assignment metadata,
    calibrates anchor distributions using population priors drawn from the
    shared registry, and computes probabilities plus confidence scores for
    each student essay."""

    # Minimum anchors for stable estimation
    MIN_ANCHORS_FOR_EMPIRICAL = 3
    MIN_ANCHORS_FOR_VARIANCE = 5

    def __init__(self) -> None:
        self.context_builder = ContextBuilder(min_anchors_required=0)
        self.logger = logger

    def _resolve_scale_configuration(self, scale_id: str) -> ScaleConfiguration:
        """Materialize runtime configuration for the requested grade scale."""
        try:
            metadata = get_scale(scale_id)
        except ValueError:
            self.logger.error(
                "Unknown grade scale requested; defaulting to swedish_8_anchor",
                extra={"scale_id": scale_id},
            )
            metadata = get_scale("swedish_8_anchor")
            scale_id = metadata.scale_id
        if metadata.population_priors is not None:
            priors = dict(metadata.population_priors)
        else:
            priors = get_uniform_priors(scale_id)

        # Default behaviour: no derived modifiers unless explicitly configured
        minus_enabled_for: set[str] = set()
        plus_enabled_for: set[str] = set()

        if scale_id == "swedish_8_anchor":
            # Maintain legacy derived grades for Swedish 8-anchor scale
            minus_enabled_for = {"E", "D", "C", "B", "A"}
            plus_enabled_for = {"E", "B"}

        return ScaleConfiguration(
            metadata=metadata,
            anchor_grades=list(metadata.grades),
            population_priors=priors,
            minus_enabled_for=minus_enabled_for,
            plus_enabled_for=plus_enabled_for,
            allows_below_lowest=metadata.allows_below_lowest,
            below_lowest_grade=metadata.below_lowest_grade,
        )

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

        # Resolve active grade scale configuration
        scale_config = self._resolve_scale_configuration(context.grade_scale)

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
        calibration = self._calibrate_from_anchors(
            anchors,
            anchor_grades,
            correlation_id,
            scale_config=scale_config,
        )

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
        projections_data = self._compute_student_projections(
            students,
            calibration,
            correlation_id,
            scale_config=scale_config,
        )

        # Store projections in database
        await self._store_projections(
            session,
            cj_batch_id,
            projections_data,
            calibration,
            context,
            scale_config=scale_config,
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
                "grade_scale": scale_config.scale_id,
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
        *,
        scale_config: ScaleConfiguration,
    ) -> CalibrationResult:
        """Calibrate grade boundaries using population priors, not anchor frequency."""

        # Group anchors by grade
        anchors_by_grade = defaultdict(list)
        for anchor in anchors:
            if anchor["els_essay_id"] in anchor_grades:
                grade = anchor_grades[anchor["els_essay_id"]]
                if grade in scale_config.anchor_grades:
                    bt_score = anchor.get("bradley_terry_score", 0.0)
                    anchors_by_grade[grade].append(bt_score)

        # Calculate pooled variance for stabilization
        all_scores = [s for scores in anchors_by_grade.values() for s in scores]
        pooled_variance = np.var(all_scores) if len(all_scores) > 1 else 0.1

        # Estimate parameters with sparse anchor handling
        grade_params = {}
        for grade in scale_config.anchor_grades:
            n_anchors = len(anchors_by_grade.get(grade, []))

            if n_anchors >= self.MIN_ANCHORS_FOR_EMPIRICAL:
                # Sufficient anchors: Use empirical estimates
                mean = float(np.mean(anchors_by_grade[grade]))
                variance = float(np.var(anchors_by_grade[grade]))

            elif n_anchors > 0:
                # Sparse anchors: Blend with expected position
                empirical_mean = float(np.mean(anchors_by_grade[grade]))
                expected_position = self._get_expected_grade_position(
                    grade,
                    scale_config.anchor_grades,
                )

                # Shrinkage based on anchor count
                weight = n_anchors / self.MIN_ANCHORS_FOR_EMPIRICAL
                mean = weight * empirical_mean + (1 - weight) * expected_position

                # Inflate variance for uncertainty
                variance = pooled_variance * (self.MIN_ANCHORS_FOR_EMPIRICAL / n_anchors)

            else:
                # No anchors: Use ordinal position
                mean = self._get_expected_grade_position(grade, scale_config.anchor_grades)
                variance = pooled_variance * 2.0

                self.logger.warning(
                    f"Grade {grade} has no anchors, using expected position {mean:.3f}",
                    extra={"correlation_id": str(correlation_id), "grade": grade},
                )

            # Store with POPULATION prior, not anchor frequency
            grade_params[grade] = GradeDistribution(
                mean=mean,
                variance=max(variance, 0.01),
                n_anchors=n_anchors,
                prior=scale_config.population_priors.get(
                    grade, 1.0 / len(scale_config.anchor_grades)
                ),
            )

        # Apply isotonic regression for monotonicity
        grade_params = self._apply_isotonic_constraint(grade_params, scale_config.anchor_grades)

        # Derive boundaries for minus grades
        grade_boundaries = self._calculate_grade_boundaries(
            grade_params,
            scale_config.anchor_grades,
        )
        return CalibrationResult(
            is_valid=True,
            grade_params=grade_params,
            grade_boundaries=grade_boundaries,
            pooled_variance=pooled_variance,
            anchor_grades=scale_config.anchor_grades,
            scale_id=scale_config.scale_id,
        )

    def _get_expected_grade_position(self, grade: str, anchor_grades: list[str]) -> float:
        """Calculate expected ordinal position of a grade."""
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
        """Apply isotonic regression to ensure grade means are monotonic."""
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
        """Calculate grade boundaries from calibrated grade parameters."""
        boundaries = {}
        for i, grade in enumerate(anchor_grades):
            if i == 0:
                lower_bound = -np.inf
            else:
                prev_grade = anchor_grades[i - 1]
                lower_bound = (grade_params[prev_grade].mean + grade_params[grade].mean) / 2

            if i == len(anchor_grades) - 1:
                upper_bound = np.inf
            else:
                next_grade = anchor_grades[i + 1]
                upper_bound = (grade_params[grade].mean + grade_params[next_grade].mean) / 2

            boundaries[grade] = (lower_bound, upper_bound)
        return boundaries

    def _compute_student_projections(
        self,
        students: list[dict[str, Any]],
        calibration: CalibrationResult,
        correlation_id: UUID,
        scale_config: ScaleConfiguration,
    ) -> ProjectionsData:
        """Compute grade probabilities and projections for student essays."""
        primary_grades = {}
        anchor_primary_grades = {}
        confidence_labels = {}
        confidence_scores = {}
        grade_probabilities = {}
        bt_stats = {}

        for student in students:
            essay_id = student["els_essay_id"]
            bt_score = float(student.get("bradley_terry_score", 0.0))
            bt_se = float(student.get("bradley_terry_se", 0.1))

            # Compute probability distribution over grades
            probs = self._compute_grade_probabilities(
                bt_score,
                bt_se,
                calibration,
                scale_config=scale_config,
            )

            # Select primary grade (maximum probability)
            primary_anchor_grade = max(probs.items(), key=lambda x: x[1])[0]
            anchor_primary_grades[essay_id] = primary_anchor_grade

            # Assign final grade with minus modifier
            final_grade = self._assign_final_grade(
                bt_score,
                primary_anchor_grade,
                calibration,
                scale_config=scale_config,
            )

            # Compute confidence from distribution entropy
            entropy = self._compute_normalized_entropy(probs)
            conf_score, conf_label = self._entropy_to_confidence(entropy)

            # Store results
            primary_grades[essay_id] = final_grade
            confidence_labels[essay_id] = conf_label
            confidence_scores[essay_id] = conf_score
            grade_probabilities[essay_id] = probs
            bt_stats[essay_id] = {
                "bt_mean": bt_score,
                "bt_se": bt_se,
            }

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
        """Assign final grade with potential minus or plus modifier."""
        grade_boundaries = calibration.grade_boundaries

        lower_bound, upper_bound = grade_boundaries[primary_grade]
        grade_width = upper_bound - lower_bound

        if math.isfinite(grade_width) and grade_width > 0:
            relative_position = (bt_score - lower_bound) / grade_width
        else:
            relative_position = 0.5

        if scale_config.scale_id == "swedish_8_anchor":
            # F, D+, C+ are assigned directly (no derived versions)
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
        """Compute probability distribution over grades using Bayesian inference.

        P(grade|score) ∝ P(score|grade) × P(grade)

        Accounts for measurement uncertainty by convolving distributions.

        IMPORTANT: Applies boundary constraints to ensure grades respect
        calibrated boundaries. Probabilities are zero outside boundaries.
        """
        log_probs = {}

        for grade in calibration.anchor_grades:
            params = calibration.grade_params[grade]

            # Apply boundary constraint FIRST
            # Probabilities are zero outside the grade's boundary
            if grade in calibration.grade_boundaries:
                lower, upper = calibration.grade_boundaries[grade]
                if not (lower <= bt_score <= upper):
                    log_probs[grade] = -np.inf
                    continue

            # Likelihood: score x comes from grade g's distribution
            # Account for measurement uncertainty by convolving distributions
            combined_variance = params.variance + bt_se**2

            log_likelihood = -0.5 * (
                np.log(2 * np.pi * combined_variance)
                + (bt_score - params.mean) ** 2 / combined_variance
            )

            # Prior: base rate of grade g
            prior = scale_config.population_priors.get(
                grade,
                params.prior,
            )
            log_prior = np.log(prior) if prior > 0 else -np.inf

            # Posterior (unnormalized)
            log_probs[grade] = log_likelihood + log_prior

        # Convert from log space and normalize
        return self._normalize_log_probs(log_probs)

    def _normalize_log_probs(self, log_probs: dict[str, float]) -> dict[str, float]:
        """Normalize log probabilities to probabilities that sum to 1."""
        # Find max for numerical stability
        max_log = max(log_probs.values())

        # Convert to probabilities
        probs = {}
        for grade, log_p in log_probs.items():
            if log_p == -np.inf:
                probs[grade] = 0.0
            else:
                probs[grade] = np.exp(log_p - max_log)

        # Normalize
        total = sum(probs.values())
        if total > 0:
            for grade in probs:
                probs[grade] /= total
        else:
            # Fallback: uniform distribution
            count = len(probs) if probs else 1
            uniform = 1.0 / count
            for grade in probs:
                probs[grade] = uniform

        return probs

    def _compute_normalized_entropy(self, probs: dict[str, float]) -> float:
        """Compute normalized Shannon entropy of probability distribution."""
        # Filter out zero probabilities
        nonzero_probs = [p for p in probs.values() if p > 1e-10]

        if len(nonzero_probs) <= 1:
            return 0.0  # No uncertainty if single outcome

        # Compute Shannon entropy
        entropy = -sum(p * math.log(p) for p in nonzero_probs)

        # Normalize by maximum possible entropy
        max_entropy = math.log(len(probs)) if probs else 1.0

        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _entropy_to_confidence(self, normalized_entropy: float) -> tuple[float, str]:
        """Convert normalized entropy to confidence score and label.

        Calibrated for 8-grade Swedish system based on empirical testing.
        """
        confidence_score = 1.0 - normalized_entropy

        # Thresholds calibrated for log(8) ≈ 2.08 max entropy
        # Empirically validated with Swedish exam data
        if normalized_entropy < 0.5:  # Top 50% confidence
            label = "HIGH"
        elif normalized_entropy < 0.75:  # Middle 25%
            label = "MID"
        else:  # Bottom 25%
            label = "LOW"

        return confidence_score, label

    async def _store_projections(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        projections_data: ProjectionsData,
        calibration: CalibrationResult,
        context: AssessmentContext,
        *,
        scale_config: ScaleConfiguration,
    ) -> None:
        """Store grade projections in database."""
        projections = []

        for essay_id in projections_data.primary_grades:
            anchor_grade = projections_data.anchor_primary_grades[essay_id]
            projection = GradeProjection(
                els_essay_id=essay_id,
                cj_batch_id=cj_batch_id,
                primary_grade=projections_data.primary_grades[essay_id],
                grade_scale=scale_config.scale_id,
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
                    "primary_anchor_grade": anchor_grade,
                    "grade_scale": scale_config.scale_id,
                },
                population_prior=scale_config.population_priors.get(anchor_grade),
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
        grade_params: dict[str, GradeDistribution] | None = None,
        grade_boundaries: dict[str, tuple[float, float]] | None = None,
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
        # Convert infinity values to large numbers for JSON serialization
        result = {}
        for grade, (lower, upper) in self.grade_boundaries.items():
            # Replace infinity with very large/small numbers that JSON can handle
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

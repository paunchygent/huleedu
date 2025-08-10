"""
Grade projection module for CJ Assessment Service.

This module calculates predicted grades based on CJ rankings and anchor essays,
using statistical methods to map Bradley-Terry scores to grade boundaries with
confidence scoring based on probability distributions.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

import numpy as np
from common_core.events.cj_assessment_events import GradeProjectionSummary
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


class GradeProjector:
    """Main grade projection logic with anchor-based calibration.

    Uses anchor essays with known grades to establish grade boundaries,
    then computes probability distributions over grades for each student essay
    based on their Bradley-Terry score and standard error.

    The system uses a fine-grained 15-point grade scale:
    F, F+, E-, E, E+, D-, D, D+, C-, C, C+, B-, B, B+, A-, A

    Minimum Anchor Requirements:
    -----------------------------
    For reliable calibration, provide anchor essays for the major grades:
    F, E, D, C, B, A

    The system will:
    - Interpolate missing fine grades (e.g., B+ from B and A- anchors)
    - Extrapolate grades outside the anchor range (with reduced confidence)
    - Warn if major grades are missing from anchors
    - Function with any anchor distribution but performs best with comprehensive coverage

    Statistical Method:
    ------------------
    1. Gaussian Mixture Model: Each grade modeled as a Gaussian distribution
    2. Bayesian Inference: P(grade|score) ∝ P(score|grade) × P(grade)
    3. Isotonic Regression: Ensures monotonicity (F < F+ < E- < ... < A)
    4. Confidence Scoring: Based on entropy of probability distribution
    """

    # Fine-grained 15-point grade scale
    GRADE_ORDER_FINE = [
        "F",
        "F+",
        "E-",
        "E",
        "E+",
        "D-",
        "D",
        "D+",
        "C-",
        "C",
        "C+",
        "B-",
        "B",
        "B+",
        "A-",
        "A",
    ]

    # Minimum variance to prevent numerical issues
    MIN_VARIANCE = 0.001

    # Regularization weight for pooled variance
    VARIANCE_REGULARIZATION = 0.3

    # Minimum anchors to trust empirical variance
    MIN_ANCHORS_FOR_VARIANCE = 3

    # Required major grades for reliable calibration
    REQUIRED_MAJOR_GRADES = {"F", "E", "D", "C", "B", "A"}

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

        # Validate anchor coverage for calibration quality
        self._validate_anchor_coverage(anchor_grades, correlation_id)

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

    def _validate_anchor_coverage(
        self,
        anchor_grades: dict[str, str],
        correlation_id: UUID,
    ) -> None:
        """Validate anchor coverage and warn about missing major grades.

        For reliable calibration, we recommend anchors at F, E, D, C, B, A.
        This ensures proper coverage across the full grading spectrum.
        """
        # Extract major grades from fine-grained grades
        major_grades = set()
        for grade in anchor_grades.values():
            # Remove +/- modifiers to get major grade
            major_grade = grade.rstrip("+-")
            major_grades.add(major_grade)

        # Check which required grades are missing
        missing_grades = self.REQUIRED_MAJOR_GRADES - major_grades

        if missing_grades:
            self.logger.warning(
                f"Missing anchors for major grades: {sorted(missing_grades)}. "
                "For best calibration, provide anchors for grades F, E, D, C, B, A. "
                f"Currently have anchors for: {sorted(major_grades)}",
                extra={
                    "correlation_id": str(correlation_id),
                    "missing_grades": sorted(missing_grades),
                    "present_grades": sorted(major_grades),
                },
            )

            # Warn more strongly if too many grades are missing
            if len(missing_grades) > 3:
                self.logger.warning(
                    f"Calibration quality may be compromised with {len(missing_grades)} "
                    "major grades missing. Consider providing more anchor essays.",
                    extra={"correlation_id": str(correlation_id)},
                )
        else:
            self.logger.info(
                "Good anchor coverage: all major grades (F, E, D, C, B, A) represented",
                extra={"correlation_id": str(correlation_id)},
            )

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
        anchors_by_grade: dict[str, list[dict[str, Any]]] = {
            grade: [] for grade in self.GRADE_ORDER_FINE
        }

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

        # Estimate parameters for grades WITH anchors
        observed_params = {}
        for grade in self.GRADE_ORDER_FINE:
            grade_anchors = anchors_by_grade[grade]

            if len(grade_anchors) >= self.MIN_ANCHORS_FOR_VARIANCE:
                # Sufficient anchors: use empirical mean and regularized variance
                scores = [a["score"] for a in grade_anchors]
                mean = float(np.mean(scores))
                empirical_var = float(np.var(scores)) if len(scores) > 1 else pooled_variance

                # Regularize variance toward pooled estimate
                variance = (
                    self.VARIANCE_REGULARIZATION * pooled_variance
                    + (1 - self.VARIANCE_REGULARIZATION) * empirical_var
                )

                observed_params[grade] = GradeDistribution(
                    mean=mean,
                    variance=max(variance, self.MIN_VARIANCE),
                    n_anchors=len(grade_anchors),
                    prior=len(grade_anchors) / len(anchors),  # Data-driven prior
                )
            elif len(grade_anchors) > 0:
                # Few anchors: use mean with pooled variance
                scores = [a["score"] for a in grade_anchors]
                observed_params[grade] = GradeDistribution(
                    mean=float(np.mean(scores)),
                    variance=pooled_variance,
                    n_anchors=len(grade_anchors),
                    prior=len(grade_anchors) / len(anchors),
                )

        # Interpolate missing grades using isotonic regression
        grade_params = self._interpolate_missing_grades(observed_params, pooled_variance)

        # Enforce monotonicity if needed
        grade_params = self._enforce_monotonicity(grade_params)

        # Compute grade boundaries as midpoints between adjacent grade means
        boundaries: dict[tuple[str, str], float] = {}
        prev_grade = None
        prev_mean = None

        for grade in self.GRADE_ORDER_FINE:
            if grade in grade_params:
                curr_mean = grade_params[grade].mean
                if prev_grade and prev_mean is not None:
                    # Midpoint between adjacent grades
                    boundaries[(prev_grade, grade)] = (prev_mean + curr_mean) / 2
                prev_grade = grade
                prev_mean = curr_mean

        return CalibrationResult(
            is_valid=True,
            grade_params=grade_params,
            grade_boundaries=boundaries,
            pooled_variance=pooled_variance,
        )

    def _interpolate_missing_grades(
        self,
        observed: dict[str, GradeDistribution],
        pooled_variance: float,
    ) -> dict[str, GradeDistribution]:
        """Use isotonic regression to interpolate missing grades.

        Ensures monotonic ordering of grade centers with linear extrapolation
        for grades outside the observed range.
        """
        if len(observed) < 2:
            raise ValueError("Need at least 2 different grades with anchors")

        # Extract observed grades and their means
        observed_indices = []
        observed_means = []
        observed_variances = []
        observed_priors = []

        for i, grade in enumerate(self.GRADE_ORDER_FINE):
            if grade in observed:
                observed_indices.append(i)
                observed_means.append(observed[grade].mean)
                observed_variances.append(observed[grade].variance)
                observed_priors.append(observed[grade].prior)

        # Calculate mean step size between observed grades for extrapolation
        if len(observed_indices) >= 2:
            # Calculate average step size from observed data
            total_diff = observed_means[-1] - observed_means[0]
            total_steps = observed_indices[-1] - observed_indices[0]
            avg_step = total_diff / total_steps if total_steps > 0 else 0.05
        else:
            avg_step = 0.05  # Default step size

        # Build complete mean array with linear extrapolation
        all_indices = list(range(len(self.GRADE_ORDER_FINE)))
        interpolated_means = np.zeros(len(all_indices))

        min_obs_idx = min(observed_indices)
        max_obs_idx = max(observed_indices)
        min_obs_mean = observed_means[observed_indices.index(min_obs_idx)]
        max_obs_mean = observed_means[observed_indices.index(max_obs_idx)]

        for i in all_indices:
            if i < min_obs_idx:
                # Linear extrapolation below
                steps_below = min_obs_idx - i
                interpolated_means[i] = max(0.0, min_obs_mean - steps_below * avg_step)
            elif i > max_obs_idx:
                # Linear extrapolation above
                steps_above = i - max_obs_idx
                interpolated_means[i] = min(1.0, max_obs_mean + steps_above * avg_step)
            else:
                # Use isotonic regression for interpolation within observed range
                if i in observed_indices:
                    idx = observed_indices.index(i)
                    interpolated_means[i] = observed_means[idx]
                else:
                    # Linear interpolation between observed points
                    interpolated_means[i] = np.interp(i, observed_indices, observed_means)

        # Apply isotonic regression to ensure monotonicity
        iso_reg = IsotonicRegression(increasing=True)
        interpolated_means = iso_reg.fit_transform(all_indices, interpolated_means)

        # Interpolate variances (use local linear interpolation with extrapolation)
        # For grades outside the anchor range, use the pooled variance
        interpolated_vars = []
        for i in all_indices:
            if i < min(observed_indices):
                # Extrapolate below: use pooled variance
                interpolated_vars.append(pooled_variance)
            elif i > max(observed_indices):
                # Extrapolate above: use pooled variance
                interpolated_vars.append(pooled_variance)
            else:
                # Interpolate between observed points
                var = np.interp(i, observed_indices, observed_variances)
                interpolated_vars.append(var)

        # Use uniform priors for all grades (1/16 each)
        interpolated_priors = np.ones(len(self.GRADE_ORDER_FINE)) / len(self.GRADE_ORDER_FINE)

        # Build complete parameter set
        all_params = {}
        for i, grade in enumerate(self.GRADE_ORDER_FINE):
            if grade in observed:
                # Use observed parameters for grades with data
                all_params[grade] = observed[grade]
            else:
                # Use interpolated parameters for missing grades
                all_params[grade] = GradeDistribution(
                    mean=float(interpolated_means[i]),
                    variance=max(interpolated_vars[i], self.MIN_VARIANCE),
                    n_anchors=0,  # Interpolated grade
                    prior=float(interpolated_priors[i]),
                )

        return all_params

    def _enforce_monotonicity(
        self,
        grade_params: dict[str, GradeDistribution],
    ) -> dict[str, GradeDistribution]:
        """Ensure grade centers follow strict ordering.

        F < F+ < E- < ... < A
        """
        means = []
        for grade in self.GRADE_ORDER_FINE:
            if grade in grade_params:
                means.append(grade_params[grade].mean)
            else:
                means.append(float("nan"))

        # Check if already monotonic (ignoring NaN values)
        valid_means = [(i, m) for i, m in enumerate(means) if not np.isnan(m)]
        if all(valid_means[i][1] < valid_means[i + 1][1] for i in range(len(valid_means) - 1)):
            return grade_params

        # Apply isotonic regression to fix
        iso = IsotonicRegression(increasing=True)
        valid_indices = [i for i, _ in valid_means]
        valid_values = [m for _, m in valid_means]
        corrected_values = iso.fit_transform(valid_indices, valid_values)

        # Update parameters
        corrected_params = {}
        valid_idx = 0
        for grade in self.GRADE_ORDER_FINE:
            if grade in grade_params:
                corrected_params[grade] = GradeDistribution(
                    mean=float(corrected_values[valid_idx]),
                    variance=grade_params[grade].variance,
                    n_anchors=grade_params[grade].n_anchors,
                    prior=grade_params[grade].prior,
                )
                valid_idx += 1

        return corrected_params

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
        """Compute probability distribution over grades using Bayesian inference.

        P(grade|score) ∝ P(score|grade) × P(grade)

        Accounts for measurement uncertainty by convolving distributions.
        """
        log_probs = {}

        for grade, params in calibration.grade_params.items():
            # Likelihood: score x comes from grade g's distribution
            # Account for measurement uncertainty by convolving distributions
            combined_variance = params.variance + bt_se**2

            log_likelihood = -0.5 * (
                np.log(2 * np.pi * combined_variance)
                + (bt_score - params.mean) ** 2 / combined_variance
            )

            # Prior: base rate of grade g
            log_prior = np.log(params.prior) if params.prior > 0 else -np.inf

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
            for grade in self.GRADE_ORDER_FINE:
                probs[grade] = 1.0 / len(self.GRADE_ORDER_FINE)

        return probs

    def _build_grade_intervals(
        self,
        boundaries: dict[tuple[str, str], float],
    ) -> dict[str, tuple[float, float]]:
        """Build grade intervals from pairwise boundaries.

        Only builds intervals for grades that have boundaries defined.
        This ensures grades without anchors don't get infinite intervals.
        """
        intervals = {}

        # Find which grades have boundaries (i.e., have anchors)
        grades_with_boundaries = set()
        for grade1, grade2 in boundaries.keys():
            grades_with_boundaries.add(grade1)
            grades_with_boundaries.add(grade2)

        # Build intervals only for grades with boundaries
        for i, grade in enumerate(self.GRADE_ORDER_FINE):
            if grade not in grades_with_boundaries:
                continue

            # Find lower boundary
            lower = float("-inf")
            for j in range(i - 1, -1, -1):
                prev_grade = self.GRADE_ORDER_FINE[j]
                boundary_key = (prev_grade, grade)
                if boundary_key in boundaries:
                    lower = boundaries[boundary_key]
                    break

            # Find upper boundary
            upper = float("inf")
            for j in range(i + 1, len(self.GRADE_ORDER_FINE)):
                next_grade = self.GRADE_ORDER_FINE[j]
                boundary_key = (grade, next_grade)
                if boundary_key in boundaries:
                    upper = boundaries[boundary_key]
                    break

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
        max_entropy = math.log(len(self.GRADE_ORDER_FINE))

        return entropy / max_entropy if max_entropy > 0 else 0.0

    def _entropy_to_confidence(self, normalized_entropy: float) -> tuple[float, str]:
        """Convert normalized entropy to confidence score and label.

        Lower entropy = higher confidence (more peaked distribution)
        Uses adaptive thresholds calibrated for 15-grade scale.

        Based on empirical testing with Gaussian mixture models, typical
        normalized entropy values with comprehensive anchors range from
        0.74 (extreme scores) to 0.95 (middle scores). We calibrate
        thresholds accordingly.
        """
        # Invert entropy to get confidence
        confidence_score = 1.0 - normalized_entropy

        # Adaptive thresholds for 15-grade scale with Gaussian distributions
        # Empirically calibrated based on actual entropy distributions:
        # - Essays at extreme scores (0.95, 0.08): entropy ~0.74-0.88
        # - Essays at middle scores (0.5): entropy ~0.95
        # These thresholds ensure reasonable confidence distribution
        if normalized_entropy < 0.80:  # Top ~30% (extreme scores near anchors)
            label = "HIGH"
        elif normalized_entropy < 0.93:  # Middle ~40% (moderately near anchors)
            label = "MID"
        else:  # Bottom ~30% (far from anchors or very uncertain)
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



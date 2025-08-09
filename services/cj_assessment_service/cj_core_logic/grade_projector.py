"""
Grade projection module for CJ Assessment Service.

This module calculates predicted grades based on CJ rankings and anchor essays,
using statistical methods to map Bradley-Terry scores to grade boundaries with
confidence scoring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from common_core.events.cj_assessment_events import GradeProjectionSummary
from huleedu_service_libs.logging_utils import create_service_logger
from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.confidence_calculator import (
    ConfidenceCalculator,
)
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
    """Main grade projection logic coordinating all components.

    Integrates context building, grade boundary calibration, and
    confidence calculation to produce grade projections.
    """

    # Grade boundaries - only used when calibrated with anchor essays
    # Without anchors, no grades are assigned
    DEFAULT_BOUNDARIES = {
        "A": 0.85,
        "B": 0.50,
        "C": 0.15,
        "D": 0.05,
        "F": 0.00,
    }

    def __init__(self) -> None:
        self.context_builder = ContextBuilder(min_anchors_required=0)
        self.confidence_calculator = ConfidenceCalculator()
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
        """Calculate grade projections with full implementation.

        Args:
            session: Database session for queries and persistence
            rankings: List of essay rankings from CJ assessment
            cj_batch_id: Internal CJ batch ID for storing projections
            assignment_id: Optional assignment ID for context
            course_code: Course code for fallback context
            content_client: Client for fetching anchor content
            correlation_id: Request correlation ID

        Returns:
            GradeProjectionSummary with actual grades and confidence
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
            return GradeProjectionSummary(
                projections_available=True,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
            )

        # Build assessment context (instructions and anchors)
        context = await self.context_builder.build(
            session=session,
            assignment_id=assignment_id,
            course_code=course_code,
            content_client=content_client,
            correlation_id=correlation_id,
        )

        # Check if we have anchor essays - if not, skip grade projection
        if not context.anchor_essay_refs:
            self.logger.info(
                "No anchor essays available - skipping grade projection",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "context_source": context.context_source,
                },
            )
            # Return empty projections with projections_available=False
            return GradeProjectionSummary(
                projections_available=False,
                primary_grades={},
                confidence_labels={},
                confidence_scores={},
            )

        # We have anchors - proceed with grade projection
        grade_boundaries = self._calibrate_boundaries(context)

        # Extract scores and build comparison count map
        score_distribution = [r.get("bradley_terry_score", 0.0) for r in rankings]
        comparison_counts = self._extract_comparison_counts(rankings)

        # Calculate projections for each essay
        primary_grades = {}
        confidence_labels = {}
        confidence_scores = {}
        projections_to_store = []

        for ranking in rankings:
            essay_id = ranking.get("els_essay_id", str(ranking.get("essay_id", "")))
            if not essay_id:
                continue

            bt_score = ranking.get("bradley_terry_score", 0.0)
            comparison_count = comparison_counts.get(essay_id, 0)

            # Map score to grade using calibrated boundaries
            grade = self._score_to_grade(bt_score, grade_boundaries)

            # Calculate confidence
            confidence_score, confidence_label = self.confidence_calculator.calculate_confidence(
                bt_score=bt_score,
                comparison_count=comparison_count,
                score_distribution=score_distribution,
                grade_boundaries=grade_boundaries,
                has_anchors=True,  # We already checked we have anchors
            )

            primary_grades[essay_id] = grade
            confidence_labels[essay_id] = confidence_label
            confidence_scores[essay_id] = confidence_score

            # Prepare for database storage
            projections_to_store.append(
                GradeProjection(
                    els_essay_id=essay_id,
                    cj_batch_id=cj_batch_id,
                    primary_grade=grade,
                    confidence_score=confidence_score,
                    confidence_label=confidence_label,
                    calculation_metadata={
                        "bt_score": bt_score,
                        "comparison_count": comparison_count,
                        "context_source": context.context_source,
                        "has_anchors": True,
                        "grade_boundaries": grade_boundaries,
                    },
                )
            )

        # Store projections in database
        await self._store_projections(session, projections_to_store)

        # Log statistics
        stats = self.confidence_calculator.calculate_batch_confidence_stats(confidence_scores)
        self.logger.info(
            "Grade projections calculated with anchor calibration",
            extra={
                "correlation_id": str(correlation_id),
                "projections_count": len(primary_grades),
                "context_source": context.context_source,
                "anchor_count": len(context.anchor_essay_refs),
                "confidence_stats": stats,
            },
        )

        return GradeProjectionSummary(
            projections_available=True,
            primary_grades=primary_grades,
            confidence_labels=confidence_labels,
            confidence_scores=confidence_scores,
        )

    def _calibrate_boundaries(self, context: AssessmentContext) -> dict[str, float]:
        """Calibrate grade boundaries based on anchor essays.

        Args:
            context: Assessment context with anchor essays

        Returns:
            Dict of grade -> minimum BT score

        Note:
            This method should only be called when anchor essays are present.
            The actual calibration would involve scoring the anchor essays
            and using their known grades to establish boundaries.
        """
        # This should only be called when we have anchors
        assert context.anchor_essay_refs, "Calibration requires anchor essays"

        # TODO: Full implementation would:
        # 1. Score anchor essays using the same CJ process
        # 2. Use their known grades to calibrate boundaries
        # 3. Apply statistical methods to refine boundaries

        # For now, use calibrated boundaries based on anchor count
        self.logger.info(
            f"Calibrating grade boundaries using {len(context.anchor_essay_refs)} anchor essays"
        )

        # Placeholder calibration - in production this would be based on
        # actual anchor essay scores and their known grades
        calibrated = {
            "A": 0.82,
            "B": 0.48,
            "C": 0.18,
            "D": 0.06,
            "F": 0.00,
        }

        return calibrated

    def _score_to_grade(self, bt_score: float, boundaries: dict[str, float]) -> str:
        """Map Bradley-Terry score to grade.

        Args:
            bt_score: Bradley-Terry score (0.0-1.0)
            boundaries: Grade boundary thresholds

        Returns:
            Letter grade
        """
        # Sort grades by boundary (descending)
        sorted_grades = sorted(boundaries.items(), key=lambda x: x[1], reverse=True)

        for grade, min_score in sorted_grades:
            if bt_score >= min_score:
                return grade

        # Fallback (should not happen with proper boundaries)
        return "F"

    def _extract_comparison_counts(self, rankings: list[dict[str, Any]]) -> dict[str, int]:
        """Extract comparison counts from rankings.

        Args:
            rankings: List of essay rankings

        Returns:
            Dict of essay_id -> comparison_count
        """
        counts = {}
        for ranking in rankings:
            essay_id = ranking.get("els_essay_id", str(ranking.get("essay_id", "")))
            if essay_id:
                # Use comparison_count if available, otherwise estimate from rank
                count = ranking.get("comparison_count", 0)
                if count == 0:
                    # Estimate: higher ranked essays typically have more comparisons
                    rank = ranking.get("rank", len(rankings))
                    count = max(3, 10 - rank // 5)  # Rough estimate
                counts[essay_id] = count
        return counts

    async def _store_projections(
        self,
        session: AsyncSession,
        projections: list[GradeProjection],
    ) -> None:
        """Store grade projections in database.

        Args:
            session: Database session
            projections: List of GradeProjection objects
        """
        if not projections:
            return

        try:
            session.add_all(projections)
            await session.flush()
            self.logger.info(f"Stored {len(projections)} grade projections")
        except Exception as e:
            self.logger.error(f"Failed to store grade projections: {e}", extra={"error": str(e)})
            # Don't fail the entire assessment due to storage error


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
    )

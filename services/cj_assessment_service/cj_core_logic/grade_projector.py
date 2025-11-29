"""Grade projection orchestration for CJ Assessment Service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from common_core.events.cj_assessment_events import GradeProjectionSummary
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.context_builder import AssessmentContext
from services.cj_assessment_service.cj_core_logic.grade_projection import (
    CalibrationEngine,
    CalibrationResult,
    GradeProjectionRepository,
    GradeScaleResolver,
    ProjectionContextService,
    ProjectionEngine,
    ProjectionsData,
    ScaleConfiguration,
)
from services.cj_assessment_service.protocols import (
    ContentClientProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment.grade_projector")


@dataclass(frozen=True)
class AnchorResolutionResult:
    anchors: list[dict[str, Any]]
    students: list[dict[str, Any]]
    anchor_grades: dict[str, str]


class GradeProjector:
    """Main grade projection orchestrator coordinating SRP collaborators."""

    def __init__(
        self,
        *,
        session_provider: SessionProviderProtocol | None = None,
        context_service: ProjectionContextService | None = None,
        scale_resolver: GradeScaleResolver | None = None,
        calibration_engine: CalibrationEngine | None = None,
        projection_engine: ProjectionEngine | None = None,
        repository: GradeProjectionRepository | None = None,
    ) -> None:
        if session_provider is None:
            raise ValueError(
                "session_provider is required. GradeProjector requires SessionProviderProtocol "
                "for internal database operations. Use dependency injection to provide it."
            )
        if context_service is None:
            raise ValueError(
                "context_service is required. ProjectionContextService requires "
                "session_provider, instruction_repository, and anchor_repository. "
                "Use dependency injection to provide all required dependencies."
            )
        self._session_provider = session_provider
        self.context_service = context_service
        self.scale_resolver = scale_resolver or GradeScaleResolver()
        self.calibration_engine = calibration_engine or CalibrationEngine()
        self.projection_engine = projection_engine or ProjectionEngine()
        self.repository = repository or GradeProjectionRepository()
        # Backwards compatibility for tests expecting direct builder access
        self.context_builder = self.context_service._context_builder
        self.logger = logger

    async def calculate_projections(
        self,
        rankings: list[dict[str, Any]],
        cj_batch_id: int,
        assignment_id: str | None,
        course_code: str,
        content_client: ContentClientProtocol,
        correlation_id: UUID,
    ) -> GradeProjectionSummary:
        """Calculate grade projections for student essays using anchor calibration.

        Args:
            rankings: List of essay rankings with Bradley-Terry scores
            cj_batch_id: ID of the CJ batch being processed
            assignment_id: Optional assignment ID for context
            course_code: Course code for context
            content_client: Client for fetching content
            correlation_id: Correlation ID for tracing

        Returns:
            GradeProjectionSummary with projection results
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

        # Compute SE diagnostics from rankings for observability/diagnostics
        bt_se_summary = self._compute_bt_se_summary(rankings)

        context = await self.context_service.build_context(
            assignment_id=assignment_id,
            course_code=course_code,
            content_client=content_client,
            correlation_id=correlation_id,
        )
        scale_config = self.scale_resolver.resolve(context.grade_scale)

        anchor_resolution = self._split_and_map_anchors(rankings, context)
        if not anchor_resolution.anchors:
            self.logger.info(
                "No anchor essays available - skipping grade projection",
                extra={
                    "correlation_id": str(correlation_id),
                    "cj_batch_id": cj_batch_id,
                    "context_source": context.context_source,
                },
            )
            return self._empty_projections(available=False)

        unique_grades = set(anchor_resolution.anchor_grades.values())
        if len(unique_grades) < 2:
            self.logger.warning(
                "Insufficient grade diversity in anchors: %s",
                unique_grades,
                extra={
                    "correlation_id": str(correlation_id),
                    "unique_grades": list(unique_grades),
                },
            )
            return self._empty_projections(available=False)

        calibration = self.calibration_engine.calibrate(
            anchor_resolution.anchors,
            anchor_resolution.anchor_grades,
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

        projections_data = self.projection_engine.compute_student_projections(
            anchor_resolution.students,
            calibration,
            correlation_id,
            scale_config=scale_config,
        )

        # Use session provider for database operations
        async with self._session_provider.session() as session:
            await self.repository.store_projections(
                session,
                cj_batch_id,
                projections_data,
                calibration,
                context,
                scale_config=scale_config,
            )
            await session.commit()

        return self._build_summary(
            projections_data=projections_data,
            calibration=calibration,
            context=context,
            scale_config=scale_config,
            anchor_count=len(anchor_resolution.anchors),
            unique_anchor_grades=unique_grades,
            bt_se_summary=bt_se_summary,
        )

    def _split_and_map_anchors(
        self,
        rankings: list[dict[str, Any]],
        context: AssessmentContext,
    ) -> AnchorResolutionResult:
        anchors = [ranking for ranking in rankings if ranking.get("is_anchor") is True]
        students = [ranking for ranking in rankings if not ranking.get("is_anchor")]
        anchor_grades = self._map_anchor_grades(anchors, context)
        return AnchorResolutionResult(
            anchors=anchors,
            students=students,
            anchor_grades=anchor_grades,
        )

    def _map_anchor_grades(
        self,
        anchors: list[dict[str, Any]],
        context: AssessmentContext,
    ) -> dict[str, str]:
        anchor_grades: dict[str, str] = {}
        context_grades_by_storage: dict[str, str] = {}
        context_grades_by_ref: dict[str, str] = {}
        for ref in context.anchor_essay_refs:
            context_grades_by_storage[ref.text_storage_id] = ref.grade
            if getattr(ref, "id", None) is not None:
                context_grades_by_ref[str(ref.id)] = ref.grade

        for anchor in anchors:
            essay_id = anchor["els_essay_id"]
            metadata = anchor.get("processing_metadata") or {}

            explicit_grade = anchor.get("anchor_grade") or metadata.get("anchor_grade")
            if explicit_grade:
                anchor_grades[essay_id] = explicit_grade
                continue

            known_grade = metadata.get("known_grade")
            if known_grade:
                anchor_grades[essay_id] = known_grade
                continue

            text_storage_id = anchor.get("text_storage_id") or metadata.get("text_storage_id")
            if text_storage_id and text_storage_id in context_grades_by_storage:
                anchor_grades[essay_id] = context_grades_by_storage[text_storage_id]
                continue

            anchor_ref_id = metadata.get("anchor_ref_id")
            if anchor_ref_id and anchor_ref_id in context_grades_by_ref:
                anchor_grades[essay_id] = context_grades_by_ref[anchor_ref_id]
                continue

            self.logger.warning(
                "Anchor %s missing resolvable grade; skipping for projection",
                essay_id,
                extra={
                    "essay_id": essay_id,
                    "available_metadata": {
                        "text_storage_id": text_storage_id,
                        "anchor_ref_id": anchor_ref_id,
                    },
                },
            )

        return anchor_grades

    def _build_summary(
        self,
        *,
        projections_data: ProjectionsData,
        calibration: CalibrationResult,
        context: AssessmentContext,
        scale_config: ScaleConfiguration,
        anchor_count: int,
        unique_anchor_grades: set[str],
        bt_se_summary: dict[str, dict[str, Any]],
    ) -> GradeProjectionSummary:
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
                "anchor_count": anchor_count,
                "anchor_grades": list(unique_anchor_grades),
                "bt_se_summary": bt_se_summary,
            },
            bt_stats=projections_data.bt_stats,
        )

    def _compute_bt_se_summary(self, rankings: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Compute SE diagnostics for all essays, anchors, and students.

        This is used only for logging/diagnostics and is intentionally
        decoupled from any gating or grade decision logic.
        """

        def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
            if not rows:
                return {
                    "mean_se": 0.0,
                    "max_se": 0.0,
                    "min_se": 0.0,
                    "item_count": 0,
                }
            ses = [float(row.get("bradley_terry_se") or 0.0) for row in rows]
            return {
                "mean_se": sum(ses) / len(ses),
                "max_se": max(ses),
                "min_se": min(ses),
                "item_count": len(ses),
            }

        anchors = [r for r in rankings if r.get("is_anchor") is True]
        students = [r for r in rankings if not r.get("is_anchor")]

        return {
            "all": _summary(rankings),
            "anchors": _summary(anchors),
            "students": _summary(students),
        }

    def _empty_projections(self, available: bool = False) -> GradeProjectionSummary:
        return GradeProjectionSummary(
            projections_available=available,
            primary_grades={},
            confidence_labels={},
            confidence_scores={},
            grade_probabilities={},
            calibration_info={},
            bt_stats={},
        )

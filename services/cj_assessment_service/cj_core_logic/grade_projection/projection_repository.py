from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from services.cj_assessment_service.cj_core_logic.context_builder import AssessmentContext
from services.cj_assessment_service.cj_core_logic.grade_projection.models import (
    CalibrationResult,
    ProjectionsData,
    ScaleConfiguration,
)
from services.cj_assessment_service.models_db import GradeProjection


class GradeProjectionRepository:
    """Persist computed grade projections."""

    async def store_projections(
        self,
        session: AsyncSession,
        cj_batch_id: int,
        projections_data: ProjectionsData,
        calibration: CalibrationResult,
        context: AssessmentContext,
        *,
        scale_config: ScaleConfiguration,
    ) -> None:
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

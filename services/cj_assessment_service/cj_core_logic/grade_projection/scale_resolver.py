from __future__ import annotations

from common_core.grade_scales import GradeScaleMetadata, get_scale, get_uniform_priors
from huleedu_service_libs.logging_utils import create_service_logger

from services.cj_assessment_service.cj_core_logic.grade_projection.models import (
    ScaleConfiguration,
)

logger = create_service_logger("cj_assessment.grade_scale_resolver")


class GradeScaleResolver:
    """Resolve grade scale metadata and runtime configuration."""

    def resolve(self, scale_id: str) -> ScaleConfiguration:
        try:
            metadata: GradeScaleMetadata = get_scale(scale_id)
        except ValueError:
            logger.error(
                "Unknown grade scale requested; defaulting to swedish_8_anchor",
                extra={"scale_id": scale_id},
            )
            metadata = get_scale("swedish_8_anchor")

        if metadata.population_priors is not None:
            priors = dict(metadata.population_priors)
        else:
            priors = get_uniform_priors(metadata.scale_id)

        minus_enabled_for: set[str] = set()
        plus_enabled_for: set[str] = set()

        if metadata.scale_id == "swedish_8_anchor":
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

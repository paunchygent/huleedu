"""Admin blueprint for anchor reference inspection (preflight surfaces).

Purpose: enable tools (e.g. ENG5 runner) to verify anchors exist before executing
student-only batches. This is an admin surface by design (no public anchor listing).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from common_core.api_models.anchor_summary import AnchorSummaryItem, AnchorSummaryResponse
from dishka import FromDishka
from huleedu_service_libs.error_handling import (
    raise_processing_error,
    raise_resource_not_found,
)
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from quart import Blueprint
from quart_dishka import inject

from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    SessionProviderProtocol,
)

from .common import logger, record_admin_metric, register_admin_auth

anchors_bp = Blueprint("cj_admin_anchors", __name__, url_prefix="/admin/v1")
register_admin_auth(anchors_bp)


def _serialize_anchor(model: Any) -> AnchorSummaryItem:
    created_at = getattr(model, "created_at", None)
    if created_at is None:
        created_at = datetime.now(UTC)
    return AnchorSummaryItem(
        id=int(model.id),
        assignment_id=model.assignment_id,
        anchor_label=model.anchor_label,
        grade=model.grade,
        grade_scale=model.grade_scale,
        text_storage_id=model.text_storage_id,
        created_at=created_at,
    )


@anchors_bp.get("/anchors/assignment/<string:assignment_id>")
@inject
async def get_anchor_summary_by_assignment(  # type: ignore[override]
    assignment_id: str,
    session_provider: FromDishka[SessionProviderProtocol],
    instruction_repository: FromDishka[AssessmentInstructionRepositoryProtocol],
    anchor_repository: FromDishka[AnchorRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Return anchor summary for an assignment in the instruction grade_scale."""

    async with session_provider.session() as session:
        instructions = await instruction_repository.get_assessment_instruction(
            session,
            assignment_id=assignment_id,
            course_id=None,
        )
        if instructions is None:
            record_admin_metric("anchors_summary", "failure")
            raise_resource_not_found(
                service="cj_assessment_service",
                operation="get_anchor_summary_by_assignment",
                correlation_id=corr.uuid,
                resource_type="assessment_instruction",
                resource_id=assignment_id,
            )

        try:
            all_anchors = await anchor_repository.get_anchor_essay_references(
                session,
                assignment_id=assignment_id,
                grade_scale=None,
            )
            anchors_for_scale = await anchor_repository.get_anchor_essay_references(
                session,
                assignment_id=assignment_id,
                grade_scale=instructions.grade_scale,
            )
        except Exception as exc:  # pragma: no cover - defensive
            record_admin_metric("anchors_summary", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="get_anchor_summary_by_assignment",
                message="Failed to load anchors for assignment",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    counts_by_scale: dict[str, int] = {}
    for anchor in all_anchors:
        counts_by_scale[anchor.grade_scale] = counts_by_scale.get(anchor.grade_scale, 0) + 1

    response = AnchorSummaryResponse(
        assignment_id=assignment_id,
        grade_scale=instructions.grade_scale,
        anchor_count=len(anchors_for_scale),
        anchors=[_serialize_anchor(a) for a in anchors_for_scale],
        anchor_count_total=len(all_anchors),
        anchor_count_by_scale=counts_by_scale,
    )
    record_admin_metric("anchors_summary", "success")
    logger.info(
        "Admin anchor summary fetched",
        extra={
            "assignment_id": assignment_id,
            "grade_scale": instructions.grade_scale,
            "anchor_count": response.anchor_count,
            "anchor_count_total": response.anchor_count_total,
        },
    )
    return response.model_dump(), 200

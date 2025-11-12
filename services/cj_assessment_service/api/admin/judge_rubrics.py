"""Admin blueprint for judge rubric management."""

from __future__ import annotations

from typing import Any

from common_core.api_models.assessment_instructions import (
    JudgeRubricResponse,
    JudgeRubricUploadRequest,
)
from dishka import FromDishka
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_processing_error,
    raise_resource_not_found,
    raise_validation_error,
)
from huleedu_service_libs.error_handling.correlation import CorrelationContext
from pydantic import ValidationError
from quart import Blueprint, g, request
from quart_dishka import inject

from services.cj_assessment_service.protocols import (
    CJRepositoryProtocol,
    ContentClientProtocol,
)

from .common import logger, record_admin_metric, register_admin_auth

judge_rubrics_bp = Blueprint("cj_admin_judge_rubrics", __name__, url_prefix="/admin/v1")
register_admin_auth(judge_rubrics_bp)


@judge_rubrics_bp.post("/judge-rubrics")
@inject
async def upload_judge_rubric(  # type: ignore[override]
    repository: FromDishka[CJRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Upload judge rubric for assignment and update instruction reference."""

    payload = await request.get_json()
    if not isinstance(payload, dict):
        raise_validation_error(
            service="cj_assessment_service",
            operation="upload_judge_rubric",
            field="body",
            message="JSON body required",
            correlation_id=corr.uuid,
        )

    try:
        req = JudgeRubricUploadRequest.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        loc = first_error.get("loc", ("body",))
        field_path = ".".join(str(part) for part in loc)
        record_admin_metric("rubric_upload", "failure")
        raise_validation_error(
            service="cj_assessment_service",
            operation="upload_judge_rubric",
            field=field_path,
            message=first_error.get("msg", "Invalid payload"),
            correlation_id=corr.uuid,
        )

    async with repository.session() as session:
        try:
            existing = await repository.get_assessment_instruction(
                session,
                assignment_id=req.assignment_id,
                course_id=None,
            )

            if not existing:
                record_admin_metric("rubric_upload", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="upload_judge_rubric",
                    correlation_id=corr.uuid,
                    resource_type="AssessmentInstruction",
                    resource_id=req.assignment_id,
                )

            storage_response = await content_client.store_content(
                content=req.rubric_text,
                content_type="text/plain",
            )
            storage_id = storage_response.get("content_id")

            if not storage_id:
                record_admin_metric("rubric_upload", "failure")
                raise_processing_error(
                    service="cj_assessment_service",
                    operation="upload_judge_rubric",
                    message="Content Service did not return storage_id",
                    correlation_id=corr.uuid,
                )

            logger.info(
                "Judge rubric uploaded to Content Service",
                extra={
                    "assignment_id": req.assignment_id,
                    "storage_id": storage_id,
                    "correlation_id": str(corr.uuid),
                    "admin_user": getattr(g, "admin_payload", {}).get("sub"),
                },
            )

            updated = await repository.upsert_assessment_instruction(
                session=session,
                assignment_id=existing.assignment_id,
                course_id=existing.course_id,
                instructions_text=existing.instructions_text,
                grade_scale=existing.grade_scale,
                student_prompt_storage_id=existing.student_prompt_storage_id,
                judge_rubric_storage_id=storage_id,
            )

        except HuleEduError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            record_admin_metric("rubric_upload", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="upload_judge_rubric",
                message="Failed to upload judge rubric",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    if updated.assignment_id is None or updated.judge_rubric_storage_id is None:
        record_admin_metric("rubric_upload", "failure")
        raise_processing_error(
            service="cj_assessment_service",
            operation="upload_judge_rubric",
            message="Upsert resulted in None values for required fields",
            correlation_id=corr.uuid,
        )

    response = JudgeRubricResponse(
        assignment_id=updated.assignment_id,
        judge_rubric_storage_id=updated.judge_rubric_storage_id,
        rubric_text=req.rubric_text,
        instructions_text=updated.instructions_text,
        grade_scale=updated.grade_scale,
        created_at=updated.created_at,
    )

    logger.info(
        "Judge rubric associated with assessment instruction",
        extra={
            "assignment_id": updated.assignment_id,
            "storage_id": updated.judge_rubric_storage_id,
            "admin_user": getattr(g, "admin_payload", {}).get("sub"),
        },
    )

    record_admin_metric("rubric_upload", "success")
    return response.model_dump(), 200


@judge_rubrics_bp.get("/judge-rubrics/assignment/<string:assignment_id>")
@inject
async def get_judge_rubric(  # type: ignore[override]
    assignment_id: str,
    repository: FromDishka[CJRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Fetch judge rubric with full instruction context."""

    async with repository.session() as session:
        try:
            instruction = await repository.get_assessment_instruction(
                session,
                assignment_id=assignment_id,
                course_id=None,
            )

            if not instruction:
                record_admin_metric("rubric_get", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="get_judge_rubric",
                    correlation_id=corr.uuid,
                    resource_type="AssessmentInstruction",
                    resource_id=assignment_id,
                )

            if not instruction.judge_rubric_storage_id:
                record_admin_metric("rubric_get", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="get_judge_rubric",
                    correlation_id=corr.uuid,
                    resource_type="JudgeRubric",
                    resource_id=assignment_id,
                    message="No rubric configured for assignment",
                )

            rubric_text = await content_client.fetch_content(
                storage_id=instruction.judge_rubric_storage_id,
                correlation_id=corr.uuid,
            )

        except HuleEduError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            record_admin_metric("rubric_get", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="get_judge_rubric",
                message="Failed to fetch judge rubric",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    if instruction.assignment_id is None or instruction.judge_rubric_storage_id is None:
        record_admin_metric("rubric_get", "failure")
        raise_processing_error(
            service="cj_assessment_service",
            operation="get_judge_rubric",
            message="Instruction missing required fields",
            correlation_id=corr.uuid,
        )

    response = JudgeRubricResponse(
        assignment_id=instruction.assignment_id,
        judge_rubric_storage_id=instruction.judge_rubric_storage_id,
        rubric_text=rubric_text,
        instructions_text=instruction.instructions_text,
        grade_scale=instruction.grade_scale,
        created_at=instruction.created_at,
    )

    logger.info(
        "Judge rubric retrieved",
        extra={
            "assignment_id": assignment_id,
            "storage_id": instruction.judge_rubric_storage_id,
            "admin_user": getattr(g, "admin_payload", {}).get("sub"),
        },
    )

    record_admin_metric("rubric_get", "success")
    return response.model_dump(), 200


__all__ = ["judge_rubrics_bp"]

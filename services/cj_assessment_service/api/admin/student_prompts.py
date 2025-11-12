"""Admin blueprint for student prompt management."""

from __future__ import annotations

from typing import Any

from common_core.api_models.assessment_instructions import (
    StudentPromptResponse,
    StudentPromptUploadRequest,
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

student_prompts_bp = Blueprint("cj_admin_student_prompts", __name__, url_prefix="/admin/v1")
register_admin_auth(student_prompts_bp)


@student_prompts_bp.post("/student-prompts")
@inject
async def upload_student_prompt(  # type: ignore[override]
    repository: FromDishka[CJRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Upload student prompt for assignment and update instruction reference."""

    payload = await request.get_json()
    if not isinstance(payload, dict):
        raise_validation_error(
            service="cj_assessment_service",
            operation="upload_student_prompt",
            field="body",
            message="JSON body required",
            correlation_id=corr.uuid,
        )

    try:
        req = StudentPromptUploadRequest.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        loc = first_error.get("loc", ("body",))
        field_path = ".".join(str(part) for part in loc)
        record_admin_metric("prompt_upload", "failure")
        raise_validation_error(
            service="cj_assessment_service",
            operation="upload_student_prompt",
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
                record_admin_metric("prompt_upload", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="upload_student_prompt",
                    correlation_id=corr.uuid,
                    resource_type="AssessmentInstruction",
                    resource_id=req.assignment_id,
                )

            storage_response = await content_client.store_content(
                content=req.prompt_text,
                content_type="text/plain",
            )
            storage_id = storage_response.get("content_id")

            if not storage_id:
                record_admin_metric("prompt_upload", "failure")
                raise_processing_error(
                    service="cj_assessment_service",
                    operation="upload_student_prompt",
                    message="Content Service did not return storage_id",
                    correlation_id=corr.uuid,
                )

            logger.info(
                "Student prompt uploaded to Content Service",
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
                student_prompt_storage_id=storage_id,
            )

        except HuleEduError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            record_admin_metric("prompt_upload", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="upload_student_prompt",
                message="Failed to upload student prompt",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    if updated.assignment_id is None or updated.student_prompt_storage_id is None:
        record_admin_metric("prompt_upload", "failure")
        raise_processing_error(
            service="cj_assessment_service",
            operation="upload_student_prompt",
            message="Upsert resulted in None values for required fields",
            correlation_id=corr.uuid,
        )

    response = StudentPromptResponse(
        assignment_id=updated.assignment_id,
        student_prompt_storage_id=updated.student_prompt_storage_id,
        prompt_text=req.prompt_text,
        instructions_text=updated.instructions_text,
        grade_scale=updated.grade_scale,
        created_at=updated.created_at,
    )

    logger.info(
        "Student prompt associated with assessment instruction",
        extra={
            "assignment_id": updated.assignment_id,
            "storage_id": updated.student_prompt_storage_id,
            "admin_user": getattr(g, "admin_payload", {}).get("sub"),
        },
    )

    record_admin_metric("prompt_upload", "success")
    return response.model_dump(), 200


@student_prompts_bp.get("/student-prompts/assignment/<string:assignment_id>")
@inject
async def get_student_prompt(  # type: ignore[override]
    assignment_id: str,
    repository: FromDishka[CJRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Fetch student prompt with full instruction context."""

    async with repository.session() as session:
        try:
            instruction = await repository.get_assessment_instruction(
                session,
                assignment_id=assignment_id,
                course_id=None,
            )

            if not instruction:
                record_admin_metric("prompt_get", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="get_student_prompt",
                    correlation_id=corr.uuid,
                    resource_type="AssessmentInstruction",
                    resource_id=assignment_id,
                )

            if not instruction.student_prompt_storage_id:
                record_admin_metric("prompt_get", "failure")
                raise_resource_not_found(
                    service="cj_assessment_service",
                    operation="get_student_prompt",
                    correlation_id=corr.uuid,
                    resource_type="StudentPrompt",
                    resource_id=assignment_id,
                    message="No prompt configured for assignment",
                )

            prompt_text = await content_client.fetch_content(
                storage_id=instruction.student_prompt_storage_id,
                correlation_id=corr.uuid,
            )

        except HuleEduError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            record_admin_metric("prompt_get", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="get_student_prompt",
                message="Failed to fetch student prompt",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    if instruction.assignment_id is None or instruction.student_prompt_storage_id is None:
        record_admin_metric("prompt_get", "failure")
        raise_processing_error(
            service="cj_assessment_service",
            operation="get_student_prompt",
            message="Instruction missing required fields",
            correlation_id=corr.uuid,
        )

    response = StudentPromptResponse(
        assignment_id=instruction.assignment_id,
        student_prompt_storage_id=instruction.student_prompt_storage_id,
        prompt_text=prompt_text,
        instructions_text=instruction.instructions_text,
        grade_scale=instruction.grade_scale,
        created_at=instruction.created_at,
    )

    logger.info(
        "Student prompt retrieved",
        extra={
            "assignment_id": assignment_id,
            "storage_id": instruction.student_prompt_storage_id,
            "admin_user": getattr(g, "admin_payload", {}).get("sub"),
        },
    )

    record_admin_metric("prompt_get", "success")
    return response.model_dump(), 200


__all__ = ["student_prompts_bp"]

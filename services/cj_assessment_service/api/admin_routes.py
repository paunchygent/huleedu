"""Admin endpoints for managing CJ assessment instructions."""

from __future__ import annotations

from typing import Any, cast

from common_core.api_models.assessment_instructions import (
    AssessmentInstructionListResponse,
    AssessmentInstructionResponse,
    AssessmentInstructionUpsertRequest,
)
from common_core.grade_scales import get_scale
from dishka import FromDishka
from huleedu_service_libs.auth import decode_and_validate_jwt
from huleedu_service_libs.error_handling import (
    raise_authentication_error,
    raise_authorization_error,
    raise_processing_error,
    raise_resource_not_found,
    raise_validation_error,
)
from huleedu_service_libs.error_handling.correlation import (
    CorrelationContext,
    extract_correlation_context_from_request,
)
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import ValidationError
from quart import Blueprint, current_app, g, request
from quart_dishka import inject

from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_metrics
from services.cj_assessment_service.models_db import AssessmentInstruction
from services.cj_assessment_service.protocols import CJRepositoryProtocol

logger = create_service_logger("cj_assessment_service.api.admin")

bp = Blueprint("cj_admin", __name__, url_prefix="/admin/v1")


@bp.before_request
async def require_admin() -> None:
    """Authenticate admin access using Identity Service JWTs."""

    settings: Settings = current_app.config["settings"]
    corr = extract_correlation_context_from_request(request)
    authorization = request.headers.get("Authorization")

    if not authorization:
        raise_authentication_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Authorization header required",
            correlation_id=corr.uuid,
            reason="missing_authorization_header",
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise_authentication_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Expected 'Authorization: Bearer <token>'",
            correlation_id=corr.uuid,
            reason="invalid_authorization_format",
        )

    token = parts[1]
    payload = decode_and_validate_jwt(
        token,
        settings,
        correlation_id=corr.uuid,
        service="cj_assessment_service",
        operation="admin_auth",
    )

    roles = payload.get("roles")
    if not isinstance(roles, list) or "admin" not in roles:
        raise_authorization_error(
            service="cj_assessment_service",
            operation="admin_auth",
            message="Admin role required",
            correlation_id=corr.uuid,
            required_role="admin",
        )

    g.admin_payload = payload
    g.correlation_context = corr


def _serialize_instruction(model: AssessmentInstruction) -> AssessmentInstructionResponse:
    return AssessmentInstructionResponse(
        id=model.id,
        assignment_id=model.assignment_id,
        course_id=model.course_id,
        instructions_text=model.instructions_text,
        grade_scale=model.grade_scale,
        student_prompt_storage_id=model.student_prompt_storage_id,
        created_at=model.created_at,
    )


def _resolve_settings() -> Settings:
    return cast(Settings, current_app.config["settings"])


def _record_admin_metric(operation: str, status: str) -> None:
    metrics = get_metrics()
    counter = metrics.get("admin_instruction_operations")
    if counter is not None:
        counter.labels(operation=operation, status=status).inc()


@bp.post("/assessment-instructions")
@inject
async def upsert_assessment_instruction(  # type: ignore[override]
    repository: FromDishka[CJRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Create/update assignment-scoped assessment configuration (admin workflow).

    Optional `student_prompt_storage_id` associates Content Service prompt reference.
    Phase 4 adds dedicated prompt upload endpoint; currently provide pre-obtained storage_id.

    User ad-hoc batches bypass this - provide prompt refs directly in batch registration.
    """

    payload = await request.get_json()
    if not isinstance(payload, dict):
        raise_validation_error(
            service="cj_assessment_service",
            operation="upsert_assessment_instruction",
            field="body",
            message="JSON body required",
            correlation_id=corr.uuid,
        )

    try:
        req = AssessmentInstructionUpsertRequest.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        loc = first_error.get("loc", ("body",))
        field_path = ".".join(str(part) for part in loc)
        _record_admin_metric("upsert", "failure")
        raise_validation_error(
            service="cj_assessment_service",
            operation="upsert_assessment_instruction",
            field=field_path,
            message=first_error.get("msg", "Invalid payload"),
            correlation_id=corr.uuid,
        )

    try:
        get_scale(req.grade_scale)
    except ValueError as exc:
        raise_validation_error(
            service="cj_assessment_service",
            operation="upsert_assessment_instruction",
            field="grade_scale",
            message=str(exc),
            correlation_id=corr.uuid,
        )

    async with repository.session() as session:
        try:
            record = await repository.upsert_assessment_instruction(
                session,
                assignment_id=req.assignment_id,
                course_id=req.course_id,
                instructions_text=req.instructions_text,
                grade_scale=req.grade_scale,
                student_prompt_storage_id=req.student_prompt_storage_id,
            )
        except ValueError as exc:
            _record_admin_metric("upsert", "failure")
            raise_validation_error(
                service="cj_assessment_service",
                operation="upsert_assessment_instruction",
                field="scope",
                message=str(exc),
                correlation_id=corr.uuid,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _record_admin_metric("upsert", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="upsert_assessment_instruction",
                message="Failed to persist instructions",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    response = _serialize_instruction(record)
    logger.info(
        "Upserted assessment instructions",
        extra={
            "assignment_id": response.assignment_id,
            "course_id": response.course_id,
            "grade_scale": response.grade_scale,
            "admin_user": getattr(g, "admin_payload", {}).get("sub"),
        },
    )
    _record_admin_metric("upsert", "success")
    return response.model_dump(), 200


@bp.get("/assessment-instructions")
@inject
async def list_assessment_instructions(  # type: ignore[override]
    repository: FromDishka[CJRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """List instructions with pagination."""

    page = max(1, int(request.args.get("page", "1")))
    page_size = max(1, min(200, int(request.args.get("page_size", "50"))))
    grade_scale = request.args.get("grade_scale") or None
    offset = (page - 1) * page_size

    async with repository.session() as session:
        try:
            items, total = await repository.list_assessment_instructions(
                session,
                limit=page_size,
                offset=offset,
                grade_scale=grade_scale,
            )
        except Exception as exc:  # pragma: no cover - defensive
            _record_admin_metric("list", "failure")
            raise_processing_error(
                service="cj_assessment_service",
                operation="list_assessment_instructions",
                message="Failed to list instructions",
                correlation_id=corr.uuid,
                error=str(exc),
            )

    response = AssessmentInstructionListResponse(
        items=[_serialize_instruction(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )
    _record_admin_metric("list", "success")
    return response.model_dump(), 200


@bp.get("/assessment-instructions/assignment/<string:assignment_id>")
@inject
async def get_assessment_instruction_by_assignment(  # type: ignore[override]
    assignment_id: str,
    repository: FromDishka[CJRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Fetch assignment-specific instructions."""

    async with repository.session() as session:
        record = await repository.get_assessment_instruction(
            session,
            assignment_id=assignment_id,
            course_id=None,
        )

    if record is None:
        _record_admin_metric("get", "failure")
        raise_resource_not_found(
            service="cj_assessment_service",
            operation="get_assessment_instruction",
            correlation_id=corr.uuid,
            resource_type="assessment_instruction",
            resource_id=assignment_id,
        )

    _record_admin_metric("get", "success")
    return _serialize_instruction(record).model_dump(), 200


@bp.delete("/assessment-instructions/assignment/<string:assignment_id>")
@inject
async def delete_assignment_instruction(  # type: ignore[override]
    assignment_id: str,
    repository: FromDishka[CJRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Delete assignment-scoped instructions."""

    async with repository.session() as session:
        deleted = await repository.delete_assessment_instruction(
            session,
            assignment_id=assignment_id,
            course_id=None,
        )

    if not deleted:
        _record_admin_metric("delete", "failure")
        raise_resource_not_found(
            service="cj_assessment_service",
            operation="delete_assessment_instruction",
            correlation_id=corr.uuid,
            resource_type="assessment_instruction",
            resource_id=assignment_id,
        )

    _record_admin_metric("delete", "success")
    return {"status": "deleted", "assignment_id": assignment_id}, 200


@bp.delete("/assessment-instructions/course/<string:course_id>")
@inject
async def delete_course_instruction(  # type: ignore[override]
    course_id: str,
    repository: FromDishka[CJRepositoryProtocol],
    corr: FromDishka[CorrelationContext],
) -> tuple[dict[str, Any], int]:
    """Delete course-level fallback instructions."""

    async with repository.session() as session:
        deleted = await repository.delete_assessment_instruction(
            session,
            assignment_id=None,
            course_id=course_id,
        )

    if not deleted:
        _record_admin_metric("delete", "failure")
        raise_resource_not_found(
            service="cj_assessment_service",
            operation="delete_assessment_instruction",
            correlation_id=corr.uuid,
            resource_type="assessment_instruction_course",
            resource_id=course_id,
        )

    _record_admin_metric("delete", "success")
    return {"status": "deleted", "course_id": course_id}, 200

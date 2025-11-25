"""Anchor essay management API endpoints."""

from __future__ import annotations

from common_core.grade_scales import validate_grade_for_scale
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import ValidationError
from quart import Blueprint, request
from quart_dishka import inject

from services.cj_assessment_service.models_api import RegisterAnchorRequest
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    ContentClientProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("anchor_management")

bp = Blueprint("anchors", __name__, url_prefix="/api/v1/anchors")


@bp.post("/register")
@inject
async def register_anchor_essay(
    session_provider: FromDishka[SessionProviderProtocol],
    instruction_repository: FromDishka[AssessmentInstructionRepositoryProtocol],
    anchor_repository: FromDishka[AnchorRepositoryProtocol],
    content_client: FromDishka[ContentClientProtocol],
) -> tuple[dict, int]:
    """Register an anchor essay for calibration.

    Accepts raw text via JSON for simplicity (YAGNI).
    Future sprints can add file upload support.

    Request body:
    {
        "assignment_id": "assignment-123",
        "grade": "A",  # Valid grades: A, B, C, D, E, F
        "essay_text": "Full essay text here..."
    }

    Returns:
    {
        "anchor_id": 1,
        "storage_id": "content-abc123",
        "status": "registered"
    }
    """
    try:
        payload = await request.get_json()
    except Exception:  # pragma: no cover - Quart handles JSON errors variably
        logger.warning("Invalid JSON payload for anchor registration", exc_info=True)
        return {"error": "Invalid JSON body"}, 400

    if not isinstance(payload, dict):
        return {"error": "Invalid JSON body"}, 400

    required_fields = {"assignment_id", "grade", "essay_text"}
    if not required_fields.issubset(payload.keys()):
        return {"error": "Missing required fields"}, 400

    try:
        register_request = RegisterAnchorRequest.model_validate(payload)
    except ValidationError as exc:
        error_messages = "; ".join(error["msg"] for error in exc.errors())
        return {"error": error_messages}, 400

    try:
        async with session_provider.session() as session:
            assignment_context = await instruction_repository.get_assignment_context(
                session,
                register_request.assignment_id,
            )

            if not assignment_context:
                return {"error": f"Unknown assignment_id '{register_request.assignment_id}'"}, 400

            grade_scale = assignment_context.get("grade_scale", "swedish_8_anchor")

            anchor_label = register_request.anchor_label or register_request.grade

            try:
                grade_is_valid = validate_grade_for_scale(
                    register_request.grade,
                    grade_scale,
                )
            except ValueError as validation_error:
                logger.error(
                    "Grade scale validation failed",
                    extra={
                        "assignment_id": register_request.assignment_id,
                        "grade_scale": grade_scale,
                        "error": str(validation_error),
                    },
                )
                return {"error": str(validation_error)}, 400

            if not grade_is_valid:
                return {
                    "error": (f"Invalid grade '{register_request.grade}' for scale '{grade_scale}'")
                }, 400

            # TODO(TASK-CONTENT-SERVICE-IDEMPOTENT-UPLOADS): switch to hashed lookup-or-create flow
            # once Content Service exposes the new API (avoids duplicate blobs).
            storage_response = await content_client.store_content(
                content=register_request.essay_text,
                content_type="text/plain",
            )
            storage_id = storage_response.get("content_id")

            if not storage_id:
                logger.error("Content Service did not return storage_id")
                return {"error": "Failed to store essay content"}, 500

            anchor_id = await anchor_repository.upsert_anchor_reference(
                session,
                assignment_id=register_request.assignment_id,
                anchor_label=anchor_label,
                grade=register_request.grade,
                grade_scale=grade_scale,
                text_storage_id=storage_id,
            )

            logger.info(
                "Registered anchor essay %s for assignment %s",
                anchor_id,
                register_request.assignment_id,
                extra={
                    "anchor_id": anchor_id,
                    "assignment_id": register_request.assignment_id,
                    "grade": register_request.grade,
                    "grade_scale": grade_scale,
                    "storage_id": storage_id,
                },
            )

            return {
                "anchor_id": anchor_id,
                "storage_id": storage_id,
                "grade_scale": grade_scale,
                "status": "registered",
            }, 201

    except Exception as e:
        logger.error(f"Failed to register anchor essay: {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

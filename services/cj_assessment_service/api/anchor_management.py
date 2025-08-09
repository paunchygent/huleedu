"""Anchor essay management API endpoints."""

from __future__ import annotations

from dishka import FromDishka
from dishka.integrations.quart import inject
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, request

from services.cj_assessment_service.models_db import AnchorEssayReference
from services.cj_assessment_service.protocols import CJRepositoryProtocol, ContentClientProtocol

logger = create_service_logger("anchor_management")

bp = Blueprint("anchors", __name__, url_prefix="/api/v1/anchors")


@bp.post("/register")
@inject
async def register_anchor_essay(
    repository: FromDishka[CJRepositoryProtocol],
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
        data = await request.json

        # Basic validation
        if not all(k in data for k in ["assignment_id", "grade", "essay_text"]):
            return {"error": "Missing required fields"}, 400

        if data["grade"] not in ["A", "B", "C", "D", "E", "F"]:
            return {"error": "Invalid grade"}, 400

        if len(data["essay_text"]) < 100:
            return {"error": "Essay text too short (min 100 chars)"}, 400

        # Note: Non-atomic operation - content storage and DB write are separate
        # If DB write fails, content will be orphaned in Content Service
        # Consider implementing cleanup or two-phase commit in future iteration

        # 1. Store content in Content Service
        storage_response = await content_client.store_content(
            content=data["essay_text"], content_type="text/plain"
        )
        storage_id = storage_response.get("content_id")

        if not storage_id:
            logger.error("Content Service did not return storage_id")
            return {"error": "Failed to store essay content"}, 500

        # 2. Create AnchorEssayReference record (separate transaction)
        async with repository.session() as session:
            anchor_ref = AnchorEssayReference(
                assignment_id=data["assignment_id"],
                grade=data["grade"],
                text_storage_id=storage_id,  # Using renamed field
            )
            session.add(anchor_ref)
            await session.commit()

            logger.info(
                f"Registered anchor essay {anchor_ref.id} for assignment {data['assignment_id']}",
                extra={
                    "anchor_id": anchor_ref.id,
                    "assignment_id": data["assignment_id"],
                    "grade": data["grade"],
                    "storage_id": storage_id,
                },
            )

            return {
                "anchor_id": anchor_ref.id,
                "storage_id": storage_id,
                "status": "registered",
            }, 201

    except Exception as e:
        logger.error(f"Failed to register anchor essay: {e}", exc_info=True)
        return {"error": "Internal server error"}, 500

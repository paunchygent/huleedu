from __future__ import annotations

from uuid import UUID, uuid4

from dishka import FromDishka
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Blueprint, Response, jsonify, request
from quart_dishka import inject

from services.class_management_service.domain_handlers.student_name_handler import (
    StudentNameHandler,
)

bp = Blueprint("internal", __name__, url_prefix="/internal/v1")
logger = create_service_logger("class_management_service.internal_routes")


def _extract_correlation_id() -> UUID:
    """Extract correlation ID from request headers, generate new if missing."""
    correlation_header = request.headers.get("X-Correlation-ID")
    if correlation_header:
        try:
            return UUID(correlation_header)
        except (ValueError, TypeError):
            logger.warning(f"Invalid correlation ID in header: {correlation_header}")

    # Generate new correlation ID if missing or invalid
    return uuid4()


@bp.route("/batches/<batch_id>/student-names", methods=["GET"])
@inject
async def get_batch_student_names(
    batch_id: str,
    handler: FromDishka[StudentNameHandler],
) -> Response | tuple[Response, int]:
    """Get all student names for essays in a batch.

    Args:
        batch_id: The batch's ID as string
        handler: Injected student name handler

    Returns:
        List of essay->student name mappings with PersonNameV1 structure
    """
    try:
        correlation_id = _extract_correlation_id()

        response = await handler.get_batch_student_names(batch_id, correlation_id)

        logger.info(
            "Batch student names retrieved successfully",
            extra={
                "batch_id": batch_id,
                "count": len(response.items),
                "correlation_id": str(correlation_id),
            },
        )

        return jsonify(response.to_dict()), 200

    except HuleEduError as e:
        logger.error(
            "Failed to retrieve batch student names",
            extra={
                "batch_id": batch_id,
                "error": str(e),
                "correlation_id": str(correlation_id)
                if "correlation_id" in locals()
                else "unknown",
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400


@bp.route("/associations/essay/<essay_id>", methods=["GET"])
@inject
async def get_essay_student_association(
    essay_id: str,
    handler: FromDishka[StudentNameHandler],
) -> Response | tuple[Response, int]:
    """Get student association for a single essay.

    Args:
        essay_id: The essay's ID as string
        handler: Injected student name handler

    Returns:
        Essay->student association with PersonNameV1 structure, or 404 if not found
    """
    try:
        correlation_id = _extract_correlation_id()

        response = await handler.get_essay_student_association(essay_id, correlation_id)

        if response is None:
            logger.info(
                "No student association found for essay",
                extra={
                    "essay_id": essay_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return jsonify({"error": "Essay student association not found"}), 404

        logger.info(
            "Essay student association retrieved successfully",
            extra={
                "essay_id": essay_id,
                "student_id": str(response.student_id),
                "correlation_id": str(correlation_id),
            },
        )

        return jsonify(response.to_dict()), 200

    except HuleEduError as e:
        logger.error(
            "Failed to retrieve essay student association",
            extra={
                "essay_id": essay_id,
                "error": str(e),
                "correlation_id": str(correlation_id)
                if "correlation_id" in locals()
                else "unknown",
            },
        )
        return jsonify({"error": e.error_detail.model_dump()}), 400

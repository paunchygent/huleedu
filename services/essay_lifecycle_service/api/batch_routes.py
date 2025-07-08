"""Batch management routes for Essay Lifecycle Service."""

from __future__ import annotations

from uuid import UUID, uuid4

from common_core.observability_enums import OperationType
from common_core.status_enums import EssayStatus, OperationStatus
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter
from pydantic import BaseModel
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from services.essay_lifecycle_service.config import settings
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

logger = create_service_logger("els.api.batch")
batch_bp = Blueprint("batch_routes", __name__, url_prefix=f"/{settings.API_VERSION}/batches")

# Global metrics reference (initialized in app.py)
ESSAY_OPERATIONS: Counter | None = None


def set_essay_operations_metric(metric: Counter) -> None:
    """Set the essay operations metric reference."""
    global ESSAY_OPERATIONS
    ESSAY_OPERATIONS = metric


class BatchStatusResponse(BaseModel):
    """Response model for batch status queries."""

    batch_id: str
    total_essays: int
    status_breakdown: dict[EssayStatus, int]
    completion_percentage: float


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str
    detail: str | None = None
    correlation_id: UUID


@batch_bp.route("/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response | tuple[Response, int]:
    """Get status summary for a batch of essays."""
    logger.info(f"Getting status for batch {batch_id}")

    # Get all essays in the batch
    essays = await state_store.list_essays_by_batch(batch_id)
    if not essays:
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()
        response = ErrorResponse(
            error="Batch Not Found",
            correlation_id=uuid4(),
            detail=f"Batch with ID {batch_id} does not exist or has no essays",
        )
        return jsonify(response.model_dump()), 404

    # Get status breakdown
    status_breakdown = await state_store.get_batch_status_summary(batch_id)
    total_essays = len(essays)

    # Calculate completion percentage
    completed_statuses = {
        EssayStatus.SPELLCHECKED_SUCCESS,  # Walking skeleton terminal success
        EssayStatus.ESSAY_CRITICAL_FAILURE,
    }
    completed_count = sum(
        count for status, count in status_breakdown.items() if status in completed_statuses
    )
    completion_percentage = (completed_count / total_essays) * 100 if total_essays > 0 else 0

    batch_response = BatchStatusResponse(
        batch_id=batch_id,
        total_essays=total_essays,
        status_breakdown=status_breakdown,
        completion_percentage=completion_percentage,
    )

    return jsonify(batch_response.model_dump(mode="json"))

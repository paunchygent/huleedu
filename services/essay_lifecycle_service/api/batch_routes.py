"""Batch management routes for Essay Lifecycle Service."""

from __future__ import annotations

from uuid import UUID, uuid4

from common_core.observability_enums import OperationType
from common_core.status_enums import EssayStatus, OperationStatus
from dishka import FromDishka
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import Counter
from pydantic import BaseModel
from quart import Blueprint, Response, jsonify, request
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


def _extract_correlation_id() -> UUID:
    """Extract correlation ID from request headers or generate new one."""
    correlation_header = request.headers.get("X-Correlation-ID")
    if correlation_header:
        try:
            return UUID(correlation_header)
        except ValueError:
            # Invalid UUID format, generate new one
            pass
    return uuid4()


class BatchStatusResponse(BaseModel):
    """Response model for batch status queries."""

    batch_id: str
    total_essays: int
    status_breakdown: dict[EssayStatus, int]
    completion_percentage: float


@batch_bp.route("/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response:
    """Get status summary for a batch of essays."""
    # Extract correlation ID from request headers or generate new one
    correlation_id = _extract_correlation_id()

    logger.info(
        f"Getting status for batch {batch_id}",
        extra={"batch_id": batch_id, "correlation_id": str(correlation_id)},
    )

    # Get all essays in the batch - let HuleEduError exceptions bubble up to Quart error handlers
    essays = await state_store.list_essays_by_batch(batch_id)
    if not essays:
        # Import here to avoid circular imports
        from huleedu_service_libs.error_handling import raise_resource_not_found

        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()

        # Raise structured error instead of manual ErrorResponse
        raise_resource_not_found(
            service="essay_lifecycle_service",
            operation="get_batch_status",
            resource_type="Batch",
            resource_id=batch_id,
            correlation_id=correlation_id,
            operation_details="Batch does not exist or has no essays",
        )

    # Compute status breakdown from already-fetched essays (eliminates duplicate query)
    status_breakdown: dict[EssayStatus, int] = {}
    for essay in essays:
        status = essay.current_status
        status_breakdown[status] = status_breakdown.get(status, 0) + 1

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

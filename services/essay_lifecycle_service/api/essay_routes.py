"""Essay management routes for Essay Lifecycle Service."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from common_core.domain_enums import ContentType
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

logger = create_service_logger("els.api.essay")
essay_bp = Blueprint("essay_routes", __name__, url_prefix=f"/{settings.API_VERSION}/essays")

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


class EssayStatusResponse(BaseModel):
    """Response model for essay status queries."""

    essay_id: str
    current_status: EssayStatus
    batch_id: str | None
    processing_progress: dict[str, bool]
    timeline: dict[str, datetime]
    storage_references: dict[ContentType, str]
    created_at: datetime
    updated_at: datetime


def _calculate_processing_progress(current_status: EssayStatus) -> dict[str, bool]:
    """Calculate processing progress - walking skeleton version."""
    return {
        "essay_ready_for_processing": current_status
        in [
            EssayStatus.READY_FOR_PROCESSING,
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
        ],
        "pipeline_assigned": current_status
        in [
            EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS,
        ],
        "spellcheck_completed": current_status == EssayStatus.SPELLCHECKED_SUCCESS,
        # Walking skeleton: only spellcheck pipeline progress tracked by ELS
    }


@essay_bp.route("/<essay_id>/status", methods=["GET"])
@inject
async def get_essay_status(
    essay_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response:
    """Get current status of an essay."""
    # Extract correlation ID from request headers or generate new one
    correlation_id = _extract_correlation_id()

    logger.info(
        f"Getting status for essay {essay_id}",
        extra={"essay_id": essay_id, "correlation_id": str(correlation_id)},
    )

    # Get essay state - let HuleEduError exceptions bubble up to Quart error handlers
    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        # Import here to avoid circular imports
        from huleedu_service_libs.error_handling import raise_resource_not_found

        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()

        # Raise structured error instead of manual ErrorResponse
        raise_resource_not_found(
            service="essay_lifecycle_service",
            operation="get_essay_status",
            resource_type="Essay",
            resource_id=essay_id,
            correlation_id=correlation_id,
        )

    # Calculate processing progress
    processing_progress = _calculate_processing_progress(essay_state.current_status)

    status_response = EssayStatusResponse(
        essay_id=essay_state.essay_id,
        current_status=essay_state.current_status,
        batch_id=essay_state.batch_id,
        processing_progress=processing_progress,
        timeline=essay_state.timeline,
        storage_references=essay_state.storage_references,
        created_at=essay_state.created_at,
        updated_at=essay_state.updated_at,
    )

    if ESSAY_OPERATIONS:
        ESSAY_OPERATIONS.labels(
            operation=OperationType.DOWNLOAD.value, status=OperationStatus.SUCCESS.value
        ).inc()
    return jsonify(status_response.model_dump(mode="json"))


@essay_bp.route("/<essay_id>/timeline", methods=["GET"])
@inject
async def get_essay_timeline(
    essay_id: str,
    state_store: FromDishka[EssayRepositoryProtocol],
) -> Response:
    """Get detailed timeline for an essay."""
    # Extract correlation ID from request headers or generate new one
    correlation_id = _extract_correlation_id()

    logger.info(
        f"Getting timeline for essay {essay_id}",
        extra={"essay_id": essay_id, "correlation_id": str(correlation_id)},
    )

    # Get essay state - let HuleEduError exceptions bubble up to Quart error handlers
    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        # Import here to avoid circular imports
        from huleedu_service_libs.error_handling import raise_resource_not_found

        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()

        # Raise structured error instead of manual ErrorResponse
        raise_resource_not_found(
            service="essay_lifecycle_service",
            operation="get_essay_timeline",
            resource_type="Essay",
            resource_id=essay_id,
            correlation_id=correlation_id,
        )

    # Return just the timeline and metadata
    timeline_response = {
        "essay_id": essay_state.essay_id,
        "timeline": essay_state.timeline,
        "processing_metadata": essay_state.processing_metadata,
        "current_status": essay_state.current_status.value,
    }

    if ESSAY_OPERATIONS:
        ESSAY_OPERATIONS.labels(
            operation=OperationType.DOWNLOAD.value, status=OperationStatus.SUCCESS.value
        ).inc()
    return jsonify(timeline_response)

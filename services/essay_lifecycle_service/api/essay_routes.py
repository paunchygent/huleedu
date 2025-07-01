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
from quart import Blueprint, Response, jsonify
from quart_dishka import inject

from config import settings
from services.essay_lifecycle_service.protocols import EssayRepositoryProtocol

logger = create_service_logger("els.api.essay")
essay_bp = Blueprint("essay_routes", __name__, url_prefix=f"/{settings.API_VERSION}/essays")

# Global metrics reference (initialized in app.py)
ESSAY_OPERATIONS: Counter | None = None


def set_essay_operations_metric(metric: Counter) -> None:
    """Set the essay operations metric reference."""
    global ESSAY_OPERATIONS
    ESSAY_OPERATIONS = metric


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


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str
    detail: str | None = None
    correlation_id: UUID


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
) -> Response | tuple[Response, int]:
    """Get current status of an essay."""
    logger.info(f"Getting status for essay {essay_id}")

    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()
        error_response = ErrorResponse(
            error="Essay Not Found",
            correlation_id=uuid4(),
            detail=f"Essay with ID {essay_id} does not exist",
        )
        return jsonify(error_response.model_dump()), 404

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
) -> Response | tuple[Response, int]:
    """Get detailed timeline for an essay."""
    logger.info(f"Getting timeline for essay {essay_id}")

    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(
                operation=OperationType.DOWNLOAD.value, status=OperationStatus.NOT_FOUND.value
            ).inc()
        response = ErrorResponse(
            error="Essay Not Found",
            correlation_id=uuid4(),
            detail=f"Essay with ID {essay_id} does not exist",
        )
        return jsonify(response.model_dump()), 404

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

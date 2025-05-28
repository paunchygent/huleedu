"""
HTTP API for the Essay Lifecycle Service.

This module provides REST endpoints for querying essay state and managing
essay processing workflows.
"""

from __future__ import annotations

from datetime import datetime

from common_core.enums import ContentType, EssayStatus
from dishka import FromDishka, make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from pydantic import BaseModel, ValidationError
from quart import Quart, Response, jsonify, request
from quart_dishka import QuartDishka, inject

from config import settings
from di import EssayLifecycleServiceProvider
from protocols import EssayStateStore, EventPublisher, MetricsCollector, StateTransitionValidator

logger = create_service_logger("essay_api")


# Pydantic models for API requests and responses
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


class BatchStatusResponse(BaseModel):
    """Response model for batch status queries."""

    batch_id: str
    total_essays: int
    status_breakdown: dict[EssayStatus, int]
    completion_percentage: float


class RetryRequest(BaseModel):
    """Request model for essay retry operations."""

    phase: str  # "spellcheck", "nlp", "ai_feedback"
    force: bool = False


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str
    detail: str | None = None
    correlation_id: str | None = None


def create_app() -> Quart:
    """Create and configure the Quart application."""
    app = Quart(__name__)

    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        log_level=settings.LOG_LEVEL,
    )

    # Setup DI container
    container = make_async_container(EssayLifecycleServiceProvider())
    QuartDishka(app=app, container=container)

    logger.info("Quart application created with DI container")

    return app


app = create_app()


@app.errorhandler(ValidationError)
async def handle_validation_error(error: ValidationError) -> Response | tuple[Response, int]:
    """Handle Pydantic validation errors."""
    logger.warning(f"Validation error: {error}")
    response = ErrorResponse(error="Validation Error", detail=str(error))
    return jsonify(response.model_dump()), 400


@app.errorhandler(ValueError)
async def handle_value_error(error: ValueError) -> Response | tuple[Response, int]:
    """Handle value errors."""
    logger.warning(f"Value error: {error}")
    response = ErrorResponse(error="Invalid Value", detail=str(error))
    return jsonify(response.model_dump()), 400


@app.errorhandler(Exception)
async def handle_general_error(error: Exception) -> Response | tuple[Response, int]:
    """Handle general exceptions."""
    logger.error(f"Unexpected error: {error}")
    response = ErrorResponse(error="Internal Server Error", detail="An unexpected error occurred")
    return jsonify(response.model_dump()), 500


@app.route("/healthz", methods=["GET"])
async def health_check() -> Response:
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": settings.SERVICE_NAME})


@app.route(f"/{settings.API_VERSION}/essays/<essay_id>/status", methods=["GET"])
@inject
async def get_essay_status(
    essay_id: str,
    state_store: FromDishka[EssayStateStore],
) -> Response | tuple[Response, int]:
    """Get current status of an essay."""
    logger.info(f"Getting status for essay {essay_id}")

    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        error_response = ErrorResponse(
            error="Essay Not Found", detail=f"Essay with ID {essay_id} does not exist"
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

    return jsonify(status_response.model_dump(mode="json"))


@app.route(f"/{settings.API_VERSION}/essays/<essay_id>/timeline", methods=["GET"])
@inject
async def get_essay_timeline(
    essay_id: str,
    state_store: FromDishka[EssayStateStore],
) -> Response | tuple[Response, int]:
    """Get detailed timeline for an essay."""
    logger.info(f"Getting timeline for essay {essay_id}")

    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        response = ErrorResponse(
            error="Essay Not Found", detail=f"Essay with ID {essay_id} does not exist"
        )
        return jsonify(response.model_dump()), 404

    # Return just the timeline and metadata
    timeline_response = {
        "essay_id": essay_state.essay_id,
        "timeline": essay_state.timeline,
        "processing_metadata": essay_state.processing_metadata,
        "current_status": essay_state.current_status.value,
    }

    return jsonify(timeline_response)


@app.route(f"/{settings.API_VERSION}/batches/<batch_id>/status", methods=["GET"])
@inject
async def get_batch_status(
    batch_id: str,
    state_store: FromDishka[EssayStateStore],
) -> Response | tuple[Response, int]:
    """Get status summary for a batch of essays."""
    logger.info(f"Getting status for batch {batch_id}")

    # Get all essays in the batch
    essays = await state_store.list_essays_by_batch(batch_id)
    if not essays:
        response = ErrorResponse(
            error="Batch Not Found",
            detail=f"Batch with ID {batch_id} does not exist or has no essays",
        )
        return jsonify(response.model_dump()), 404

    # Get status breakdown
    status_breakdown = await state_store.get_batch_status_summary(batch_id)
    total_essays = len(essays)

    # Calculate completion percentage
    completed_statuses = {
        EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
        EssayStatus.ESSAY_PARTIALLY_PROCESSED_WITH_FAILURES,
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


@app.route(f"/{settings.API_VERSION}/essays/<essay_id>/retry", methods=["POST"])
@inject
async def retry_essay_processing(
    essay_id: str,
    state_store: FromDishka[EssayStateStore],
    event_publisher: FromDishka[EventPublisher],
    transition_validator: FromDishka[StateTransitionValidator],
    metrics_collector: FromDishka[MetricsCollector],
) -> Response | tuple[Response, int]:
    """Retry processing for a specific essay phase."""
    logger.info(f"Retry requested for essay {essay_id}")

    # Parse request body
    try:
        request_data = await request.get_json()
        retry_request = RetryRequest.model_validate(request_data or {})
    except ValidationError as e:
        response = ErrorResponse(error="Invalid Request", detail=str(e))
        return jsonify(response.model_dump()), 400

    # Get current essay state
    essay_state = await state_store.get_essay_state(essay_id)
    if essay_state is None:
        response = ErrorResponse(
            error="Essay Not Found", detail=f"Essay with ID {essay_id} does not exist"
        )
        return jsonify(response.model_dump()), 404

    # Determine the appropriate status for retry
    retry_status_map = {
        "spellcheck": EssayStatus.AWAITING_SPELLCHECK,
        "nlp": EssayStatus.AWAITING_NLP,
        "ai_feedback": EssayStatus.AWAITING_AI_FEEDBACK,
    }

    target_status = retry_status_map.get(retry_request.phase)
    if target_status is None:
        response = ErrorResponse(
            error="Invalid Phase",
            detail=f"Phase '{retry_request.phase}' is not supported for retry",
        )
        return jsonify(response.model_dump()), 400

    # Validate transition (allow force if specified)
    if not retry_request.force and not transition_validator.validate_transition(
        essay_state.current_status, target_status
    ):
        response = ErrorResponse(
            error="Invalid State Transition",
            detail=f"Cannot retry {retry_request.phase} from current status {essay_state.current_status.value}",
        )
        return jsonify(response.model_dump()), 400

    # Update state to retry status
    retry_metadata = {
        "retry_requested_at": datetime.now().isoformat(),
        "retry_phase": retry_request.phase,
        "retry_forced": retry_request.force,
    }
    await state_store.update_essay_state(essay_id, target_status, retry_metadata)

    # NOTE: Under batch-centric orchestration, ELS only updates essay state
    # The Batch Service is responsible for detecting retry-eligible essays
    # and issuing appropriate batch commands to re-trigger processing
    logger.info(
        f"Essay {essay_id} marked for retry in phase {retry_request.phase}",
        extra={
            "essay_id": essay_id,
            "phase": retry_request.phase,
            "target_status": target_status.value,
            "message": "Batch Service will detect and re-initiate processing",
        },
    )

    # Record metrics
    metrics_collector.record_state_transition(essay_state.current_status.value, target_status.value)
    metrics_collector.increment_counter(
        "operations", {"operation": "retry_requested", "phase": retry_request.phase}
    )

    return jsonify(
        {
            "message": f"Retry initiated for {retry_request.phase}",
            "essay_id": essay_id,
            "new_status": target_status.value,
        }
    )


def _calculate_processing_progress(current_status: EssayStatus) -> dict[str, bool]:
    """Calculate processing progress based on current status."""
    progress = {
        "uploaded": False,
        "text_extracted": False,
        "spellcheck_completed": False,
        "nlp_completed": False,
        "ai_feedback_completed": False,
        "all_processing_completed": False,
    }

    # Map status progression
    status_progression = [
        EssayStatus.UPLOADED,
        EssayStatus.TEXT_EXTRACTED,
        EssayStatus.SPELLCHECKED_SUCCESS,
        EssayStatus.NLP_COMPLETED_SUCCESS,
        EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS,
        EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED,
    ]

    progress_keys = list(progress.keys())

    for i, status in enumerate(status_progression):
        if current_status == status or _is_status_completed(current_status, status):
            if i < len(progress_keys):
                progress[progress_keys[i]] = True

    return progress


def _is_status_completed(current_status: EssayStatus, check_status: EssayStatus) -> bool:
    """Check if a status stage has been completed based on current status."""
    # Simple heuristic based on status values and progression
    status_order = {
        EssayStatus.UPLOADED: 1,
        EssayStatus.TEXT_EXTRACTED: 2,
        EssayStatus.AWAITING_SPELLCHECK: 3,
        EssayStatus.SPELLCHECKED_SUCCESS: 4,
        EssayStatus.AWAITING_NLP: 5,
        EssayStatus.NLP_COMPLETED_SUCCESS: 6,
        EssayStatus.AWAITING_AI_FEEDBACK: 7,
        EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS: 8,
        EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED: 9,
    }

    current_order = status_order.get(current_status, 0)
    check_order = status_order.get(check_status, 0)

    return current_order >= check_order


if __name__ == "__main__":
    import asyncio

    import hypercorn.asyncio
    import hypercorn.config

    # Create hypercorn config
    config = hypercorn.config.Config()
    config.bind = [f"{settings.HTTP_HOST}:{settings.HTTP_PORT}"]
    config.loglevel = settings.LOG_LEVEL.lower()

    logger.info(f"Starting Essay Lifecycle Service API on {config.bind[0]}")

    # Run the application
    asyncio.run(hypercorn.asyncio.serve(app, config))

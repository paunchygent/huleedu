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
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from pydantic import BaseModel, ValidationError
from quart import Quart, Response, g, jsonify, request
from quart_dishka import QuartDishka, inject

from config import settings
from di import EssayLifecycleServiceProvider
from protocols import EssayStateStore

logger = create_service_logger("essay_api")

# Prometheus metrics (will be registered with DI-provided registry)
REQUEST_COUNT: Counter | None = None
REQUEST_DURATION: Histogram | None = None
ESSAY_OPERATIONS: Counter | None = None


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

    # Initialize metrics with DI registry
    @app.before_serving
    async def initialize_metrics() -> None:
        """Initialize Prometheus metrics with DI registry."""
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            _initialize_metrics(registry)

    logger.info("Quart application created with DI container")

    return app


def _initialize_metrics(registry: CollectorRegistry) -> None:
    """Initialize Prometheus metrics with the provided registry."""
    global REQUEST_COUNT, REQUEST_DURATION, ESSAY_OPERATIONS

    REQUEST_COUNT = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status_code'],
        registry=registry
    )

    REQUEST_DURATION = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration in seconds',
        ['method', 'endpoint'],
        registry=registry
    )

    ESSAY_OPERATIONS = Counter(
        'essay_operations_total',
        'Total essay operations',
        ['operation', 'status'],
        registry=registry
    )


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


@app.route("/metrics")
@inject
async def metrics(registry: FromDishka[CollectorRegistry]) -> Response:
    """Prometheus metrics endpoint."""
    try:
        metrics_data = generate_latest(registry)
        response = Response(metrics_data, content_type=CONTENT_TYPE_LATEST)
        return response
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response("Error generating metrics", status=500)


@app.before_request
async def before_request() -> None:
    """Record request start time for duration metrics."""
    import time
    g.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after each request."""
    try:
        import time
        start_time = getattr(g, 'start_time', None)
        if start_time is not None and REQUEST_COUNT is not None and REQUEST_DURATION is not None:
            duration = time.time() - start_time

            # Get endpoint name (remove query parameters)
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    except Exception as e:
        logger.error(f"Error recording request metrics: {e}")

    return response


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
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(operation='get_status', status='not_found').inc()
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

    if ESSAY_OPERATIONS:
        ESSAY_OPERATIONS.labels(operation='get_status', status='success').inc()
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
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(operation='get_timeline', status='not_found').inc()
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

    if ESSAY_OPERATIONS:
        ESSAY_OPERATIONS.labels(operation='get_timeline', status='success').inc()
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
        if ESSAY_OPERATIONS:
            ESSAY_OPERATIONS.labels(operation='get_batch_status', status='not_found').inc()
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


def _calculate_processing_progress(current_status: EssayStatus) -> dict[str, bool]:
    """Calculate processing progress - walking skeleton version."""
    return {
        "essay_ready_for_processing": current_status in [
            EssayStatus.READY_FOR_PROCESSING, EssayStatus.AWAITING_SPELLCHECK,
            EssayStatus.SPELLCHECKING_IN_PROGRESS, EssayStatus.SPELLCHECKED_SUCCESS
        ],
        "pipeline_assigned": current_status in [
            EssayStatus.AWAITING_SPELLCHECK, EssayStatus.SPELLCHECKING_IN_PROGRESS,
            EssayStatus.SPELLCHECKED_SUCCESS
        ],
        "spellcheck_completed": current_status == EssayStatus.SPELLCHECKED_SUCCESS,
        # Walking skeleton: only spellcheck pipeline progress tracked by ELS
    }


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

"""
HTTP API for the Essay Lifecycle Service.

This module provides REST endpoints for querying essay state and managing
essay processing workflows.
"""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
)
from pydantic import ValidationError
from quart import Quart, Response, g, jsonify, request
from quart_dishka import QuartDishka

from config import settings
from di import EssayLifecycleServiceProvider

# Import Blueprints
from .api.batch_routes import batch_bp
from .api.batch_routes import set_essay_operations_metric as set_batch_essay_operations
from .api.essay_routes import essay_bp
from .api.essay_routes import set_essay_operations_metric as set_essay_essay_operations
from .api.health_routes import health_bp

logger = create_service_logger("essay_api")

# Prometheus metrics (will be registered with DI-provided registry)
REQUEST_COUNT: Counter | None = None
REQUEST_DURATION: Histogram | None = None
ESSAY_OPERATIONS: Counter | None = None


class ErrorResponse:
    """Standard error response model."""

    def __init__(self, error: str, detail: str | None = None, correlation_id: str | None = None):
        self.error = error
        self.detail = detail
        self.correlation_id = correlation_id

    def model_dump(self) -> dict:
        """Convert to dictionary for JSON response."""
        result = {"error": self.error}
        if self.detail:
            result["detail"] = self.detail
        if self.correlation_id:
            result["correlation_id"] = self.correlation_id
        return result


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

    # Share metrics with Blueprint modules
    set_essay_essay_operations(ESSAY_OPERATIONS)
    set_batch_essay_operations(ESSAY_OPERATIONS)


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


# Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(essay_bp)
app.register_blueprint(batch_bp)


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

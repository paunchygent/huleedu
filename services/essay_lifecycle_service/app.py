"""
HTTP API for the Essay Lifecycle Service.

This module provides REST endpoints for querying essay state and managing
essay processing workflows.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from pydantic import ValidationError
from quart import Quart, Response, g, jsonify, request

# Import Blueprints
# Import local modules using absolute imports for containerized deployment
import startup_setup
from api.batch_routes import batch_bp
from api.essay_routes import essay_bp
from api.health_routes import health_bp
from config import settings

# Configure structured logging for the service
configure_service_logging(
    service_name=settings.SERVICE_NAME,
    log_level=settings.LOG_LEVEL,
)
logger = create_service_logger("els.app")

app = Quart(__name__)


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


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    try:
        await startup_setup.initialize_services(app, settings)
        logger.info("Essay Lifecycle Service startup completed successfully")
    except Exception as e:
        logger.critical(f"Failed to start Essay Lifecycle Service: {e}", exc_info=True)
        raise


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    try:
        await startup_setup.shutdown_services()
        logger.info("Essay Lifecycle Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


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

        start_time = getattr(g, "start_time", None)
        if start_time is not None and hasattr(app, "extensions") and "metrics" in app.extensions:
            metrics = app.extensions["metrics"]
            duration = time.time() - start_time

            # Get endpoint name (remove query parameters)
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics
            metrics["request_count"].labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()
            metrics["request_duration"].labels(method=method, endpoint=endpoint).observe(duration)

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
    from hypercorn import Config

    # Create hypercorn config with our settings (explicit like BOS)
    config = Config()
    config.bind = [f"{settings.HTTP_HOST}:{settings.HTTP_PORT}"]
    config.workers = getattr(settings, "WEB_CONCURRENCY", 1)
    config.worker_class = "asyncio"
    config.loglevel = settings.LOG_LEVEL.lower()
    config.graceful_timeout = getattr(settings, "GRACEFUL_TIMEOUT", 30)
    config.keep_alive_timeout = getattr(settings, "KEEP_ALIVE_TIMEOUT", 5)

    logger.info(f"Starting Essay Lifecycle Service API on {config.bind[0]}")

    # Run the application
    asyncio.run(hypercorn.asyncio.serve(app, config))

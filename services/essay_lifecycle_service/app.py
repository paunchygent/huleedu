"""
HTTP API for the Essay Lifecycle Service.

This module provides REST endpoints for querying essay state and managing
essay processing workflows.
"""

from __future__ import annotations

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from pydantic import ValidationError
from quart import Quart, Response, jsonify

# Import Blueprints
# Import local modules using absolute imports for containerized deployment
from services.essay_lifecycle_service import startup_setup
from services.essay_lifecycle_service.api.batch_routes import batch_bp
from services.essay_lifecycle_service.api.essay_routes import essay_bp
from services.essay_lifecycle_service.api.health_routes import health_bp
from services.essay_lifecycle_service.config import settings

# Configure structured logging for the service
configure_service_logging(
    service_name=settings.SERVICE_NAME,
    log_level=settings.LOG_LEVEL,
)
logger = create_service_logger("els.app")

app = Quart(__name__)

# Initialize tracing early, before blueprint registration
tracer = init_tracing("essay_lifecycle_api")
app.extensions = getattr(app, "extensions", {})
app.extensions["tracer"] = tracer
setup_tracing_middleware(app, tracer)


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
        setup_standard_service_metrics_middleware(app, "els")
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

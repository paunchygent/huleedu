"""
HTTP API for the Essay Lifecycle Service.

This module provides REST endpoints for querying essay state and managing
essay processing workflows.
"""

from __future__ import annotations

from huleedu_service_libs import init_tracing
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.quart import create_error_response
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.quart_app import HuleEduApp
from pydantic import ValidationError
from quart import Response

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

app = HuleEduApp(__name__)

# Initialize tracing early, before blueprint registration
tracer = init_tracing("essay_lifecycle_api")
app.extensions = getattr(app, "extensions", {})
app.extensions["tracer"] = tracer
setup_tracing_middleware(app, tracer)


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


@app.errorhandler(HuleEduError)
async def handle_huleedu_error(error: HuleEduError) -> Response | tuple[Response, int]:
    """Handle HuleEduError exceptions with proper status mapping."""
    # Use the Quart error handler from huleedu_service_libs
    return create_error_response(error.error_detail)


@app.errorhandler(ValidationError)
async def handle_validation_error(error: ValidationError) -> Response | tuple[Response, int]:
    """Handle Pydantic validation errors."""
    from uuid import uuid4

    from huleedu_service_libs.error_handling import raise_validation_error

    logger.warning(f"Validation error: {error}")
    raise_validation_error(
        service="essay_lifecycle_service",
        operation="request_validation",
        field="request_body",
        message=str(error),
        correlation_id=uuid4(),
        validation_errors=str(error),
    )


@app.errorhandler(Exception)
async def handle_general_error(error: Exception) -> Response | tuple[Response, int]:
    """Handle general exceptions."""
    from uuid import uuid4

    from huleedu_service_libs.error_handling import raise_processing_error

    logger.error(f"Unexpected error: {error}", exc_info=True)
    raise_processing_error(
        service="essay_lifecycle_service",
        operation="request_processing",
        message="An unexpected error occurred during request processing",
        correlation_id=uuid4(),
        error_type=error.__class__.__name__,
        error_details=str(error),
    )


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

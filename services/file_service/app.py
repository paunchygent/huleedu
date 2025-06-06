"""
HuleEdu File Service Application.

This module implements the File Service HTTP API using Quart framework.
The service handles file uploads, text extraction, and event publishing.
"""

from __future__ import annotations

import time

from api.file_routes import file_bp
from api.health_routes import health_bp
from config import settings
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from quart import Quart, Response, g, request
from startup_setup import initialize_services, shutdown_services

# Configure structured logging for the service
configure_service_logging("file-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("file_service.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    await initialize_services(app, settings)
    logger.info("File Service startup completed successfully")


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    await shutdown_services()


@app.before_request
async def before_request() -> None:
    """Record request start time for duration metrics."""
    g.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after each request."""
    try:
        start_time = getattr(g, "start_time", None)
        if start_time is not None:
            duration = time.time() - start_time

            # Get endpoint name and method
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics using app context pattern
            metrics = app.extensions.get("metrics", {})
            if "request_count" in metrics:
                metrics["request_count"].labels(
                    method=method, endpoint=endpoint, status=status_code
                ).inc()
            if "request_duration" in metrics:
                metrics["request_duration"].labels(method=method, endpoint=endpoint).observe(
                    duration
                )

    except Exception as e:
        logger.error(f"Error recording request metrics: {e}")

    return response


# Register Blueprints
app.register_blueprint(file_bp)
app.register_blueprint(health_bp)

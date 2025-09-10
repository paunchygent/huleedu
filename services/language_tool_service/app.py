"""
HuleEdu Language Tool Service Application.

This module implements the Language Tool Service HTTP API using Quart framework.
The service provides grammar categorization functionality via HTTP endpoints.
"""

from __future__ import annotations

import time

from huleedu_service_libs.error_handling.quart import register_error_handlers
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_metrics_middleware
from huleedu_service_libs.middleware.frameworks.quart_correlation_middleware import (
    setup_correlation_middleware,
)
from quart import Quart

from services.language_tool_service.api.grammar_routes import grammar_bp
from services.language_tool_service.api.health_routes import health_bp
from services.language_tool_service.config import settings
from services.language_tool_service.startup_setup import initialize_services, shutdown_services

# Configure structured logging for the service
configure_service_logging("language-tool-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("language_tool_service.app")

app = Quart(__name__)

# Track service startup time for uptime calculation
SERVICE_START_TIME = time.time()


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    setup_correlation_middleware(app)  # Early setup per Rule 043.2
    register_error_handlers(app)  # Register structured error handlers per Rule 048
    await initialize_services(app, settings)

    # Store start time in app extensions for access in health checks
    app.extensions = getattr(app, "extensions", {})
    app.extensions["service_start_time"] = SERVICE_START_TIME

    # Setup HTTP metrics middleware per Rule 071.2
    # Uses "status" label to match existing metrics definition
    setup_metrics_middleware(
        app=app,
        request_count_metric_name="request_count",
        request_duration_metric_name="request_duration",
        status_label_name="status",  # Match label name used in metrics.py
        logger_name="language_tool_service.metrics",
    )

    logger.info("Language Tool Service startup completed successfully")


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    await shutdown_services()


# Register Blueprints
app.register_blueprint(health_bp)
app.register_blueprint(grammar_bp)

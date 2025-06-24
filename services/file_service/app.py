"""
HuleEdu File Service Application.

This module implements the File Service HTTP API using Quart framework.
The service handles file uploads, text extraction, and event publishing.
"""

from __future__ import annotations

from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.metrics_middleware import setup_file_service_metrics_middleware
from quart import Quart

from services.file_service.api.file_routes import file_bp
from services.file_service.api.health_routes import health_bp
from services.file_service.config import settings
from services.file_service.startup_setup import initialize_services, shutdown_services

# Configure structured logging for the service
configure_service_logging("file-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("file_service.app")

app = Quart(__name__)


@app.before_serving
async def startup() -> None:
    """Initialize services and middleware."""
    await initialize_services(app, settings)
    setup_file_service_metrics_middleware(app)
    logger.info("File Service startup completed successfully")


@app.after_serving
async def shutdown() -> None:
    """Gracefully shutdown all services."""
    await shutdown_services()


# Register Blueprints
app.register_blueprint(file_bp)
app.register_blueprint(health_bp)

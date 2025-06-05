"""Lean Quart application setup for CJ Assessment Service health API.

This module provides a minimal HTTP API for health checks and metrics,
following the mandatory Blueprint architecture pattern. The app runs
concurrently with the Kafka worker via run_service.py.

Key principles:
- Under 150 lines (architectural mandate)
- Blueprint registration only
- Shared DI container with worker
- No direct route definitions
"""

from __future__ import annotations

import asyncio
from typing import Optional

from dishka import make_async_container
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from quart import Quart
from quart_dishka import QuartDishka

from services.cj_assessment_service.api.health_routes import health_bp
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.di import CJAssessmentServiceProvider

logger = create_service_logger("cj_assessment_service.app")


def create_app(settings: Optional[Settings] = None) -> Quart:
    """Create and configure the Quart application.

    Args:
        settings: Optional settings override for testing

    Returns:
        Configured Quart application
    """
    if settings is None:
        settings = Settings()

    # Configure logging
    configure_service_logging(
        "cj_assessment_service", log_level=settings.LOG_LEVEL
    )

    # Create Quart app
    app = Quart(__name__)

    # Configure app settings
    app.config.update({
        "TESTING": False,
        "DEBUG": settings.LOG_LEVEL == "DEBUG",
    })

    # Initialize dependency injection container
    container = make_async_container(CJAssessmentServiceProvider())
    QuartDishka(app=app, container=container)

    # Register mandatory health Blueprint
    app.register_blueprint(health_bp)

    @app.before_serving
    async def startup() -> None:
        """Application startup tasks."""
        logger.info("CJ Assessment Service health API starting up")
        logger.info("Health endpoint: /healthz")
        logger.info("Metrics endpoint: /metrics")

    @app.after_serving
    async def cleanup() -> None:
        """Application cleanup tasks."""
        logger.info("CJ Assessment Service health API shutting down")

    @app.errorhandler(Exception)
    async def handle_exception(e: Exception) -> tuple[dict[str, str], int]:
        """Global exception handler for API errors."""
        logger.error(f"Unhandled exception in health API: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "service": "cj_assessment_service"
        }, 500

    return app


async def run_health_api(settings: Settings, port: Optional[int] = None) -> None:
    """Run the health API server.

    Args:
        settings: Application settings
        port: Optional port override
    """
    api_port = port if port is not None else getattr(settings, 'METRICS_PORT', 9090)

    logger.info(
        f"Starting CJ Assessment Service health API on port {api_port}"
    )

    # Create app
    app = create_app(settings)

    # Run the server
    try:
        await app.run_task(
            host="0.0.0.0",
            port=api_port,
            debug=settings.LOG_LEVEL == "DEBUG"
        )
    except Exception as e:
        logger.error(f"Health API server error: {e}", exc_info=True)
        raise


# For development/testing
if __name__ == "__main__":
    async def main() -> None:
        settings = Settings()
        await run_health_api(settings)

    asyncio.run(main())

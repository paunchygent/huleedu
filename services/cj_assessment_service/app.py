"""Integrated Quart application for CJ Assessment Service.

This module provides the single entrypoint for the service, managing both
the HTTP API (health/metrics) and the Kafka consumer using Quart's lifecycle hooks.

Key principles:
- Single DI container shared between API and worker
- Kafka consumer managed via @app.before_serving/@app.after_serving
- Follows Rule 042 HTTP Service Pattern
- No separate orchestration layer needed
"""

from __future__ import annotations

import asyncio
from typing import Optional

from dishka import AsyncContainer, make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from quart import Quart
from quart_dishka import QuartDishka

from services.cj_assessment_service.api.health_routes import health_bp
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.di import CJAssessmentServiceProvider
from services.cj_assessment_service.kafka_consumer import CJAssessmentKafkaConsumer
from services.cj_assessment_service.startup_setup import initialize_services, shutdown_services

logger = create_service_logger("cj_assessment_service.app")


class CJAssessmentApp(Quart):
    """Custom Quart app with typed service-specific attributes."""

    container: AsyncContainer
    consumer_task: Optional[asyncio.Task[None]]
    kafka_consumer: Optional[CJAssessmentKafkaConsumer]


def create_app(settings: Settings | None = None) -> CJAssessmentApp:
    """Create and configure the Quart application.

    Args:
        settings: Optional settings override for testing

    Returns:
        Configured Quart application with integrated Kafka consumer
    """
    if settings is None:
        settings = Settings()

    # Configure logging
    configure_service_logging("cj_assessment_service", log_level=settings.LOG_LEVEL)

    # Create Quart app
    app = CJAssessmentApp(__name__)

    # Configure app settings
    app.config.update(
        {
            "TESTING": False,
            "DEBUG": settings.LOG_LEVEL == "DEBUG",
        },
    )

    # Initialize dependency injection container
    container = make_async_container(CJAssessmentServiceProvider())
    QuartDishka(app=app, container=container)

    # Store container reference and initialize consumer attributes
    app.container = container
    app.consumer_task = None
    app.kafka_consumer = None

    # Initialize tracing early, before blueprint registration
    tracer = init_tracing("cj_assessment_service")
    app.extensions = getattr(app, "extensions", {})
    app.extensions["tracer"] = tracer
    setup_tracing_middleware(app, tracer)

    # Register mandatory health Blueprint
    app.register_blueprint(health_bp)

    @app.before_serving
    async def startup() -> None:
        """Application startup tasks including Kafka consumer."""
        try:
            # Initialize services
            await initialize_services(app, settings, container)

            # Setup metrics middleware (per Rule 020.4.4)
            setup_standard_service_metrics_middleware(app, "cj_assessment")

            # Get Kafka consumer from DI container and start it
            async with app.container() as request_container:
                app.kafka_consumer = await request_container.get(CJAssessmentKafkaConsumer)

            # Start consumer as background task
            app.consumer_task = asyncio.create_task(app.kafka_consumer.start_consumer())

            logger.info("CJ Assessment Service started successfully")
            logger.info("Health endpoint: /healthz")
            logger.info("Metrics endpoint: /metrics")
            logger.info("Kafka consumer: running")

        except Exception as e:
            logger.critical(f"Failed to start CJ Assessment Service: {e}", exc_info=True)
            raise

    @app.after_serving
    async def cleanup() -> None:
        """Application cleanup tasks including Kafka consumer shutdown."""
        try:
            # Stop Kafka consumer
            if app.kafka_consumer:
                logger.info("Stopping Kafka consumer...")
                await app.kafka_consumer.stop_consumer()

            # Cancel consumer task
            if app.consumer_task and not app.consumer_task.done():
                app.consumer_task.cancel()
                try:
                    await app.consumer_task
                except asyncio.CancelledError:
                    logger.info("Consumer task cancelled successfully")

            # Additional cleanup
            await shutdown_services()

            logger.info("CJ Assessment Service shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    @app.errorhandler(Exception)
    async def handle_exception(e: Exception) -> tuple[dict[str, str], int]:
        """Global exception handler for API errors."""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "service": "cj_assessment_service",
        }, 500

    return app


# For direct execution
if __name__ == "__main__":
    import hypercorn.asyncio
    from hypercorn.config import Config

    settings = Settings()
    app = create_app(settings)

    # Configure Hypercorn
    config = Config()
    config.bind = [f"0.0.0.0:{settings.METRICS_PORT}"]
    config.loglevel = settings.LOG_LEVEL.lower()

    # Run with Hypercorn
    asyncio.run(hypercorn.asyncio.serve(app, config))

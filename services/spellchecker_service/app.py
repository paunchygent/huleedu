"""Integrated Quart application for Spell Checker Service.

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

from dishka import make_async_container
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.metrics_middleware import setup_standard_service_metrics_middleware
from huleedu_service_libs.outbox import EventRelayWorker
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka
from sqlalchemy.ext.asyncio import create_async_engine

from services.spellchecker_service.api.health_routes import health_bp
from services.spellchecker_service.config import Settings
from services.spellchecker_service.di import SpellCheckerServiceProvider
from services.spellchecker_service.kafka_consumer import SpellCheckerKafkaConsumer
from services.spellchecker_service.startup_setup import initialize_services, shutdown_services

logger = create_service_logger("spellchecker_service.app")


def create_app(settings: Settings | None = None) -> HuleEduApp:
    """Create and configure the Quart application.

    Args:
        settings: Optional settings override for testing

    Returns:
        Configured Quart application with integrated Kafka consumer
    """
    if settings is None:
        settings = Settings()

    # Configure logging
    configure_service_logging("spellchecker_service", log_level=settings.LOG_LEVEL)

    # Create HuleEduApp with guaranteed infrastructure
    app = HuleEduApp(__name__)

    # Configure app settings
    app.config.update(
        {
            "TESTING": False,
            "DEBUG": settings.LOG_LEVEL == "DEBUG",
        },
    )

    # Initialize guaranteed infrastructure immediately
    app.database_engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_size=getattr(settings, "DATABASE_POOL_SIZE", 5),
        max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 10),
        pool_pre_ping=getattr(settings, "DATABASE_POOL_PRE_PING", True),
        pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 1800),
    )
    app.container = make_async_container(SpellCheckerServiceProvider(engine=app.database_engine))
    app.extensions = {}

    # Optional service-specific attributes (preserve existing patterns)
    app.consumer_task = None
    app.kafka_consumer = None
    app.relay_worker = None
    app.relay_worker_task = None

    # Setup dependency injection
    QuartDishka(app=app, container=app.container)

    # Register mandatory health Blueprint
    app.register_blueprint(health_bp)

    @app.before_serving
    async def startup() -> None:
        """Application startup tasks including Kafka consumer."""
        try:
            # Initialize services and metrics
            await initialize_services(app, settings, app.container)

            # Setup metrics middleware (per Rule 020.4.4)
            setup_standard_service_metrics_middleware(app, "spell_checker")

            # Get Kafka consumer and relay worker from DI container and start them
            async with app.container() as request_container:
                app.kafka_consumer = await request_container.get(SpellCheckerKafkaConsumer)
                app.relay_worker = await request_container.get(EventRelayWorker)

            # Start consumer as background task
            assert app.kafka_consumer is not None, "Kafka consumer must be initialized"
            app.consumer_task = asyncio.create_task(app.kafka_consumer.start_consumer())
            
            # Start relay worker as background task
            assert app.relay_worker is not None, "Relay worker must be initialized"
            await app.relay_worker.start()
            logger.info("EventRelayWorker started for outbox pattern")

            logger.info("Spell Checker Service started successfully")
            logger.info("Health endpoint: /healthz")
            logger.info("Metrics endpoint: /metrics")
            logger.info("Kafka consumer: running")
            logger.info("Outbox relay worker: running")

        except Exception as e:
            logger.critical(f"Failed to start Spell Checker Service: {e}", exc_info=True)
            raise

    @app.after_serving
    async def cleanup() -> None:
        """Application cleanup tasks including Kafka consumer shutdown."""
        try:
            # Stop relay worker first
            if app.relay_worker:
                logger.info("Stopping EventRelayWorker...")
                await app.relay_worker.stop()
            
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

            logger.info("Spell Checker Service shutdown complete")

        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)

    @app.errorhandler(Exception)
    async def handle_exception(e: Exception) -> tuple[dict[str, str], int]:
        """Global exception handler for API errors."""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        return {
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "service": "spellchecker_service",
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
    config.bind = [f"0.0.0.0:{settings.HTTP_PORT}"]
    config.loglevel = settings.LOG_LEVEL.lower()

    # Run with Hypercorn
    asyncio.run(hypercorn.asyncio.serve(app, config))

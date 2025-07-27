"""Startup and shutdown logic for File Service."""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider, OutboxSettingsProvider
from quart import Quart
from quart_dishka import QuartDishka

from services.file_service.config import Settings
from services.file_service.di import CoreInfrastructureProvider, ServiceImplementationsProvider

logger = create_service_logger("file_service.startup")


async def initialize_services(app: Quart, _settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and metrics."""
    try:
        # Initialize DI container with all providers
        # OutboxProvider automatically provides environment-based settings
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
            OutboxProvider(),  # Provides environment-aware outbox settings
        )
        QuartDishka(app=app, container=container)

        # Expose metrics dictionary through app.extensions for middleware
        from services.file_service.metrics import METRICS  # local import to avoid circular deps

        app.extensions = getattr(app, "extensions", {})
        app.extensions["metrics"] = METRICS

        # Initialize distributed tracing
        tracer = init_tracing("file_service")
        app.extensions["tracer"] = tracer
        setup_tracing_middleware(app, tracer)
        logger.info("Distributed tracing initialized")

        # Start EventRelayWorker for outbox pattern
        async with container() as request_container:
            relay_worker = await request_container.get(EventRelayWorker)
            await relay_worker.start()
            app.extensions["relay_worker"] = relay_worker
            logger.info("EventRelayWorker started for outbox pattern")

        logger.info(
            "File Service DI container, quart-dishka integration, "
            "metrics, tracing, and outbox worker initialized successfully.",
        )
    except Exception as e:
        logger.critical(f"Failed to initialize File Service: {e}", exc_info=True)
        raise


async def shutdown_services(app: Quart | None = None) -> None:
    """Gracefully shutdown all services."""
    try:
        # Stop EventRelayWorker if it exists
        if app and hasattr(app, "extensions") and "relay_worker" in app.extensions:
            relay_worker = app.extensions["relay_worker"]
            await relay_worker.stop()
            logger.info("EventRelayWorker stopped")

        # Close any other async resources if needed
        logger.info("File Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)

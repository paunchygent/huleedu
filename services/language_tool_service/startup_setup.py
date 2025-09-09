"""Startup and shutdown logic for Language Tool Service."""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from quart import Quart
from quart_dishka import QuartDishka

from services.language_tool_service.config import Settings
from services.language_tool_service.di import (
    CoreInfrastructureProvider,
    ServiceImplementationsProvider,
)

logger = create_service_logger("language_tool_service.startup")


async def initialize_services(app: Quart, _settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and metrics."""
    try:
        # Initialize DI container with all providers
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceImplementationsProvider(),
        )
        QuartDishka(app=app, container=container)

        # Expose metrics dictionary through app.extensions for middleware
        from services.language_tool_service.metrics import (
            METRICS,
        )  # local import to avoid circular deps

        app.extensions = getattr(app, "extensions", {})
        app.extensions["metrics"] = METRICS

        # Initialize distributed tracing
        tracer = init_tracing("language_tool_service")
        app.extensions["tracer"] = tracer
        setup_tracing_middleware(app, tracer)
        logger.info("Distributed tracing initialized")

        logger.info(
            "Language Tool Service DI container, quart-dishka integration, "
            "metrics, and tracing initialized successfully.",
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Language Tool Service: {e}", exc_info=True)
        raise


async def shutdown_services(app: Quart | None = None) -> None:
    """Gracefully shutdown all services."""
    try:
        # Close any async resources if needed
        logger.info("Language Tool Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)

"""Startup and shutdown setup for Spell Checker Service health API.

This module handles the initialization of metrics and other app-level services
for the Quart-based health API component of the combined service.
"""

from __future__ import annotations

from typing import Any, cast

from dishka import AsyncContainer
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from opentelemetry.trace import Tracer
from quart import Quart


class SpellCheckerQuart(Quart):
    """Custom Quart application class with type hints for custom attributes."""

    tracer: Tracer
    extensions: dict[str, Any]


from services.spell_checker_service.config import Settings
from services.spell_checker_service.metrics import get_http_metrics

logger = create_service_logger("spell_checker_service.startup_setup")


async def initialize_services(app: Quart, settings: Settings, container: AsyncContainer) -> None:
    """Initialize application services and metrics.

    Args:
        app: Quart application instance
        settings: Application settings
        container: DI container for service dependencies
    """
    app = cast(SpellCheckerQuart, app)
    """Initialize application services and metrics.

    Args:
        app: Quart application instance
        settings: Application settings
        container: DI container for service dependencies
    """
    logger.info("Initializing Spell Checker Service health API components")

    # Initialize tracing
    app.tracer = init_tracing("spell_checker_service")
    setup_tracing_middleware(app, app.tracer)
    logger.info("OpenTelemetry tracing initialized")

    # Get shared metrics (thread-safe singleton pattern)
    metrics = get_http_metrics()

    # Store metrics in app context (proper Quart pattern)
    app.extensions = getattr(app, "extensions", {})
    app.extensions["metrics"] = metrics

    logger.info("HTTP metrics initialized and stored in app extensions")
    logger.info(f"Available HTTP metrics: {list(metrics.keys())}")

    # TODO: Add additional service initialization here
    # - Database connections (if needed)
    # - External service health checks
    # - Cache initialization

    logger.info("Spell Checker Service health API initialization complete")


async def shutdown_services() -> None:
    """Cleanup application services on shutdown.

    Handles graceful shutdown of any resources that need explicit cleanup.
    """
    logger.info("Shutting down Spell Checker Service health API components")

    # TODO: Add cleanup logic here
    # - Close database connections
    # - Cleanup cache resources
    # - Flush pending metrics

    logger.info("Spell Checker Service health API shutdown complete")

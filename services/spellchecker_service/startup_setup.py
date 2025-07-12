"""Startup and shutdown setup for Spell Checker Service health API.

This module handles the initialization of metrics and other app-level services
for the Quart-based health API component of the combined service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import AsyncContainer
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

from services.spellchecker_service.config import Settings
from services.spellchecker_service.metrics import get_metrics

logger = create_service_logger("spellchecker_service.startup_setup")


async def initialize_services(
    app: "HuleEduApp", settings: Settings, container: AsyncContainer
) -> None:
    """Initialize application services and metrics.

    Args:
        app: Quart application instance
        settings: Application settings
        container: DI container for service dependencies
    """
    """Initialize application services and metrics.

    Args:
        app: Quart application instance
        settings: Application settings
        container: DI container for service dependencies
    """
    logger.info("Initializing Spell Checker Service health API components")

    # Initialize tracing
    app.tracer = init_tracing("spellchecker_service")
    setup_tracing_middleware(app, app.tracer)
    logger.info("OpenTelemetry tracing initialized")

    # Get database metrics from DI container
    try:
        from huleedu_service_libs.database import DatabaseMetrics

        async with container() as request_container:
            database_metrics = await request_container.get(DatabaseMetrics)
        logger.info("Database metrics retrieved from DI container")
    except Exception as e:
        logger.warning(f"Failed to get database metrics from DI container: {e}")
        database_metrics = None

    # Get shared metrics with database metrics integration (thread-safe singleton pattern)
    metrics = get_metrics(database_metrics)

    # Store metrics in app context (extensions dict is guaranteed to exist with HuleEduApp)
    app.extensions["metrics"] = metrics

    logger.info("All metrics initialized and stored in app extensions")
    logger.info(f"Available metrics: {list(metrics.keys())}")

    # Log database metrics integration status
    if database_metrics:
        logger.info("Database metrics successfully integrated")
        db_metrics = database_metrics.get_metrics()
        logger.info(f"Database metrics available: {list(db_metrics.keys())}")
    else:
        logger.warning("Database metrics not available - running without database monitoring")

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

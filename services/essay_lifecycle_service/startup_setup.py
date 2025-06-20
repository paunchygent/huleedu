"""Startup and shutdown logic for Essay Lifecycle Service API."""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart
from quart_dishka import QuartDishka

from api.batch_routes import (
    set_essay_operations_metric as set_batch_essay_operations,
)
from api.essay_routes import (
    set_essay_operations_metric as set_essay_essay_operations,
)
from services.essay_lifecycle_service.config import Settings
from services.essay_lifecycle_service.di import (
    BatchCoordinationProvider,
    CommandHandlerProvider,
    CoreInfrastructureProvider,
    ServiceClientsProvider,
)
from services.essay_lifecycle_service.metrics import get_http_metrics

logger = create_service_logger("els.startup")

# Global references for service management (unavoidable for Quart lifecycle)
# ELS doesn't need background tasks like BOS, but keeping structure consistent


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and metrics."""

    try:
        # Initialize DI container with all provider classes
        container = make_async_container(
            CoreInfrastructureProvider(),
            ServiceClientsProvider(),
            CommandHandlerProvider(),
            BatchCoordinationProvider(),
        )
        QuartDishka(app=app, container=container)

        # Initialize metrics using shared module and store in app context
        metrics = get_http_metrics()

        # Store metrics in app context (proper Quart pattern)
        app.extensions = getattr(app, "extensions", {})
        app.extensions["metrics"] = metrics

        # Share essay operations metric with routes modules (legacy support)
        set_essay_essay_operations(metrics["essay_operations"])
        set_batch_essay_operations(metrics["essay_operations"])

        logger.info(
            "Essay Lifecycle Service DI container, quart-dishka integration, "
            "and metrics initialized successfully."
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Essay Lifecycle Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown services."""

    try:
        # ELS API doesn't have background tasks to shutdown like BOS
        # But keeping structure consistent for future needs
        logger.info("Essay Lifecycle Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)




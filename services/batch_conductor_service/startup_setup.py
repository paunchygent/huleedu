"""Startup and shutdown logic for Batch Conductor Service."""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from quart import Quart

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.di import (
    CoreInfrastructureProvider,
    EventDrivenServicesProvider,
    PipelineServicesProvider,
)
from services.batch_conductor_service.metrics import get_http_metrics

logger = create_service_logger("bcs.startup")


def create_container() -> AsyncContainer:
    """Create the Dishka AsyncContainer with all service providers."""
    return make_async_container(
        CoreInfrastructureProvider(),
        EventDrivenServicesProvider(),
        PipelineServicesProvider(),
    )


async def initialize_metrics(app: Quart, container: AsyncContainer) -> None:
    """Initialize shared metrics."""
    try:
        # Use shared metrics instead of creating new ones
        metrics = get_http_metrics()

        # Store metrics in app context following Quart extension pattern
        app.extensions = getattr(app, "extensions", {})
        app.extensions["metrics"] = metrics

        logger.info("Batch Conductor Service shared metrics initialized successfully.")

    except Exception as e:
        logger.critical("Failed to initialize shared metrics: %s", e, exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown services."""
    try:
        logger.info("Batch Conductor Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# _create_metrics function removed - now using shared metrics module

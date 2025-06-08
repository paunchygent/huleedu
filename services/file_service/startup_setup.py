"""Startup and shutdown logic for File Service."""

from __future__ import annotations

from config import Settings
from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart
from quart_dishka import QuartDishka

from services.file_service.di import CoreInfrastructureProvider, ServiceImplementationsProvider

logger = create_service_logger("file_service.startup")


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, and metrics."""
    try:
        # Initialize DI container with both providers
        container = make_async_container(
            CoreInfrastructureProvider(), ServiceImplementationsProvider()
        )
        QuartDishka(app=app, container=container)

        # Initialize metrics with DI registry and store in app context
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

        logger.info(
            "File Service DI container, quart-dishka integration, "
            "and metrics initialized successfully."
        )
    except Exception as e:
        logger.critical(f"Failed to initialize File Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown all services."""
    try:
        # Close any async resources if needed
        logger.info("File Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)


def _create_metrics(registry: CollectorRegistry) -> dict:
    """Create Prometheus metrics instances."""
    return {
        "request_count": Counter(
            "file_service_requests_total",
            "Total number of HTTP requests",
            ["method", "endpoint", "status"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "file_service_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
    }

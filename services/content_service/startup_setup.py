"""Startup and shutdown logic for Content Service."""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart

from services.content_service.config import Settings
from services.content_service.di import ContentServiceProvider

# Global reference for DI container, managed by app.py now
_app_container_ref: AsyncContainer | None = None


def create_di_container() -> AsyncContainer:
    """Creates and returns the DI AsyncContainer."""
    global _app_container_ref
    logger = create_service_logger("content.startup")
    # Initialize DI container
    container = make_async_container(ContentServiceProvider())
    _app_container_ref = container  # Keep a reference for shutdown
    logger.info("DI AsyncContainer created.")
    return container


async def initialize_tracing(app: Quart) -> None:
    """Initialize OpenTelemetry tracing with Jaeger."""
    logger = create_service_logger("content.startup")
    try:
        tracer = init_tracing("content_service")
        setup_tracing_middleware(app, tracer)
        logger.info("Content Service tracing initialized successfully")
    except Exception as e:
        logger.critical("Failed to initialize tracing: %s", e, exc_info=True)
        raise


async def initialize_services(app: Quart, settings: Settings, container: AsyncContainer) -> None:
    """Initialize metrics using the provided DI container."""
    logger = create_service_logger("content.startup")

    try:
        # Initialize metrics with DI registry and store in app context
        # The container is now passed in, and QuartDishka is initialized in app.py
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

            logger.info("Content Service metrics initialized successfully.")
    except Exception as e:
        logger.critical(f"Failed to initialize Content Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the Content Service's DI container."""
    global _app_container_ref  # Use the reference stored during creation
    logger = create_service_logger("content.startup")

    try:
        if _app_container_ref:
            await _app_container_ref.close()
            logger.info("Content Service DI container closed")

        logger.info("Content Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during Content Service shutdown: {e}", exc_info=True)


def _create_metrics(registry: CollectorRegistry) -> dict:
    """Create Prometheus metrics instances for HTTP middleware."""
    return {
        "http_requests_total": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "http_request_duration_seconds": Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
    }

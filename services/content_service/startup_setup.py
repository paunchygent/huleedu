"""Startup and shutdown logic for Content Service."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from config import Settings
from dishka import AsyncContainer, make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart
from quart_dishka import QuartDishka

from services.content_service.di import ContentServiceProvider

logger = create_service_logger("content.startup")

# Global reference for DI container management (unavoidable for Quart lifecycle)
_container: Optional[AsyncContainer] = None


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, content store, and metrics."""
    global _container

    try:
        # Initialize content store directory
        store_root = Path(settings.CONTENT_STORE_ROOT_PATH)
        store_root.mkdir(parents=True, exist_ok=True)
        logger.info(f"Content store initialized at: {store_root.resolve()}")

        # Initialize DI container
        _container = make_async_container(ContentServiceProvider())
        QuartDishka(app=app, container=_container)

        # Initialize metrics with DI registry and store in app context
        async with _container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

        logger.info(
            "Content Service DI container, quart-dishka integration, "
            "and content store initialized successfully."
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Content Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the Content Service."""
    global _container

    try:
        if _container:
            await _container.close()
            logger.info("Content Service DI container closed")

        logger.info("Content Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during Content Service shutdown: {e}", exc_info=True)


def _create_metrics(registry: CollectorRegistry) -> dict:
    """Create Prometheus metrics instances."""
    return {
        "request_count": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
        "content_operations": Counter(
            "content_operations_total",
            "Total content operations",
            ["operation", "status"],
            registry=registry,
        ),
    }

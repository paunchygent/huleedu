"""Startup and shutdown logic for Batch Conductor Service."""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from prometheus_client import CollectorRegistry, Counter, Histogram
from quart import Quart

from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.di import (
    CoreInfrastructureProvider,
    EventDrivenServicesProvider,
    PipelineServicesProvider,
)

logger = create_service_logger("bcs.startup")


def create_container() -> AsyncContainer:
    """Create the Dishka AsyncContainer with all service providers."""
    return make_async_container(
        CoreInfrastructureProvider(),
        EventDrivenServicesProvider(),
        PipelineServicesProvider(),
    )


async def initialize_metrics(app: Quart, container: AsyncContainer) -> None:
    """Create Prometheus metrics and attach them to the Quart app."""
    try:
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context following Quart extension pattern
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

        logger.info("Batch Conductor Service metrics initialized successfully.")
    except Exception as e:
        logger.critical("Failed to initialize metrics: %s", e, exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown services."""
    try:
        logger.info("Batch Conductor Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


def _create_metrics(registry: CollectorRegistry) -> dict[str, Counter | Histogram]:
    """Create Prometheus metrics instances."""
    return {
        "request_count": Counter(
            "bcs_http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "bcs_http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
        "pipeline_resolutions": Counter(
            "bcs_pipeline_resolutions_total",
            "Total pipeline resolutions",
            ["requested_pipeline", "status"],
            registry=registry,
        ),
        "els_requests": Counter(
            "bcs_els_requests_total",
            "Total ELS HTTP requests",
            ["operation", "status"],
            registry=registry,
        ),
    }

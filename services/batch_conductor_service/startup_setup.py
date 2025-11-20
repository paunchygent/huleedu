"""Startup and shutdown logic for Batch Conductor Service."""

from __future__ import annotations

from dishka import AsyncContainer, make_async_container
from quart import Quart

from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.quart_app import HuleEduApp
from services.batch_conductor_service.di import (
    CoreInfrastructureProvider,
    EventDrivenServicesProvider,
    PipelineServicesProvider,
)
from services.batch_conductor_service.metrics import get_http_metrics


def create_container() -> AsyncContainer:
    """Create the Dishka AsyncContainer with all service providers."""
    return make_async_container(
        CoreInfrastructureProvider(),
        EventDrivenServicesProvider(),
        PipelineServicesProvider(),
    )


async def initialize_database_schema(app: HuleEduApp) -> None:
    """Initialize database schema using guaranteed infrastructure."""
    logger = create_service_logger("bcs.startup")
    try:
        async with app.database_engine.begin() as conn:
            from services.batch_conductor_service.models_db import Base

            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database schema initialized successfully")

    except Exception as e:
        logger.critical("Failed to initialize database schema: %s", e, exc_info=True)
        raise


async def initialize_tracing(app: Quart) -> None:
    """Initialize OpenTelemetry tracing with Jaeger."""
    logger = create_service_logger("bcs.startup")
    try:
        tracer = init_tracing("batch_conductor_service")
        setup_tracing_middleware(app, tracer)
        logger.info("Batch Conductor Service tracing initialized successfully")
    except Exception as e:
        logger.critical("Failed to initialize tracing: %s", e, exc_info=True)
        raise


async def initialize_metrics(app: Quart, container: AsyncContainer) -> None:
    """Initialize shared metrics."""
    logger = create_service_logger("bcs.startup")
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
    logger = create_service_logger("bcs.startup")
    try:
        logger.info("Batch Conductor Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


# _create_metrics function removed - now using shared metrics module

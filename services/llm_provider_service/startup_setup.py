"""Startup and shutdown procedures for LLM Provider Service."""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.observability.tracing import init_tracing
from quart import Quart
from quart_dishka import QuartDishka

from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.error_handlers import register_lps_error_handlers
from services.llm_provider_service.implementations.connection_pool_manager_impl import (
    ConnectionPoolManagerImpl,
)
from services.llm_provider_service.implementations.queue_processor_impl import QueueProcessorImpl
from services.llm_provider_service.metrics import get_metrics


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize all services and middleware."""
    # Configure centralized structured logging before any logging operations
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    logger = create_service_logger("llm_provider_service.startup")

    logger.info(f"Starting {settings.SERVICE_NAME} initialization...")

    # Register LPS error handlers with metrics integration
    register_lps_error_handlers(app)
    logger.info("LPS error handlers registered")

    # Initialize OpenTelemetry tracing
    tracer = init_tracing(settings.SERVICE_NAME)
    setup_tracing_middleware(app, tracer)
    logger.info("OpenTelemetry tracing initialized")

    # Initialize metrics
    _ = get_metrics()
    logger.info("Metrics initialized")

    # Create and setup DI container
    container = make_async_container(LLMProviderServiceProvider())
    QuartDishka(app=app, container=container)
    logger.info("Dependency injection container initialized")

    # Store container reference for cleanup
    app.extensions["dishka_container"] = container

    # Start queue processor
    async with container() as request_container:
        queue_processor = await request_container.get(QueueProcessorImpl)
        await queue_processor.start()
        app.extensions["queue_processor"] = queue_processor
        logger.info("Queue processor started")

    logger.info(f"{settings.SERVICE_NAME} initialization complete")


async def shutdown_services(app: Quart) -> None:
    """Gracefully shutdown all services."""
    logger = create_service_logger("llm_provider_service.startup")
    logger.info("Starting graceful shutdown...")

    # Stop queue processor
    if "queue_processor" in app.extensions:
        queue_processor = app.extensions["queue_processor"]
        await queue_processor.stop()
        logger.info("Queue processor stopped")

    # Clean up connection pools
    if "dishka_container" in app.extensions:
        container = app.extensions["dishka_container"]
        try:
            async with container() as request_container:
                pool_manager = await request_container.get(ConnectionPoolManagerImpl)
                await pool_manager.cleanup()
                logger.info("Connection pool manager cleaned up")
        except Exception as e:
            logger.warning(f"Error cleaning up connection pool manager: {e}")

        # Close DI container
        await container.close()
        logger.info("DI container closed")

    logger.info("Graceful shutdown complete")

"""Startup and shutdown procedures for LLM Provider Service."""

from __future__ import annotations

from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from quart import Quart
from quart_dishka import QuartDishka

from services.llm_provider_service.config import Settings
from services.llm_provider_service.di import LLMProviderServiceProvider
from services.llm_provider_service.metrics import get_metrics

logger = create_service_logger("llm_provider_service.startup")


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize all services and middleware."""
    logger.info(f"Starting {settings.SERVICE_NAME} initialization...")

    # Initialize metrics
    _ = get_metrics()
    logger.info("Metrics initialized")

    # Create and setup DI container
    container = make_async_container(LLMProviderServiceProvider())
    QuartDishka(app=app, container=container)
    logger.info("Dependency injection container initialized")

    # Store container reference for cleanup
    app.extensions["dishka_container"] = container

    logger.info(f"{settings.SERVICE_NAME} initialization complete")


async def shutdown_services(app: Quart) -> None:
    """Gracefully shutdown all services."""
    logger.info("Starting graceful shutdown...")

    # Close DI container
    if "dishka_container" in app.extensions:
        container = app.extensions["dishka_container"]
        await container.close()
        logger.info("DI container closed")

    logger.info("Graceful shutdown complete")

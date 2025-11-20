"""Startup and shutdown setup for Email Service.

This module provides centralized initialization and cleanup logic
for the Email Service following established patterns.
"""

from __future__ import annotations

from dishka import AsyncContainer
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.quart_app import HuleEduApp

from services.email_service.config import Settings


async def initialize_services(
    app: HuleEduApp, settings: Settings, container: AsyncContainer
) -> None:
    """Initialize database schema using guaranteed infrastructure."""
    logger = create_service_logger("email_service.startup_setup")
    try:
        # Use guaranteed database engine for schema initialization
        async with app.database_engine.begin() as conn:
            from services.email_service.models_db import Base

            await conn.run_sync(Base.metadata.create_all)

        logger.info("Database schema initialized successfully")

        # Initialize metrics with guaranteed infrastructure
        async with container():
            # Metrics will be set up by the standard middleware
            pass

        logger.info("Email Service initialized successfully")
    except Exception as e:
        logger.critical(f"Failed to initialize Email Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Cleanup tasks for graceful shutdown."""
    logger = create_service_logger("email_service.startup_setup")
    try:
        logger.info("Email Service shutdown tasks completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

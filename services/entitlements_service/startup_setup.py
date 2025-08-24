"""Startup and shutdown procedures for Entitlements Service.

This module handles initialization and cleanup of service components
including database connections, Redis clients, and policy loading.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dishka import AsyncContainer
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.metrics import (
    EntitlementsMetrics,
    setup_entitlements_service_database_monitoring,
)
from services.entitlements_service.protocols import PolicyLoaderProtocol

if TYPE_CHECKING:
    from huleedu_service_libs.quart_app import HuleEduApp

    from services.entitlements_service.config import Settings

logger = create_service_logger("entitlements_service.startup")


async def initialize_services(
    app: HuleEduApp,
    settings: Settings,
    container: AsyncContainer,
) -> None:
    """Initialize all service components.

    Args:
        app: HuleEduApp instance
        settings: Service configuration
        container: Dependency injection container
    """
    logger.info("Initializing Entitlements Service components...")

    try:
        # Setup database monitoring
        db_metrics = setup_entitlements_service_database_monitoring(
            engine=app.database_engine,
            service_name="entitlements_service",
        )
        app.extensions["db_metrics"] = db_metrics
        logger.info("Database monitoring configured")

        # Setup health checker
        app.extensions["health_checker"] = DatabaseHealthChecker(
            engine=app.database_engine,
            service_name="entitlements_service",
        )
        logger.info("Health checker configured")

        # Initialize business metrics
        metrics = EntitlementsMetrics()
        app.extensions["metrics"] = metrics
        logger.info("Business metrics initialized")

        # Load policies on startup
        async with container() as request_container:
            policy_loader = await request_container.get(PolicyLoaderProtocol)

            # Initial policy load
            try:
                await policy_loader.load_policies()
                logger.info("Policies loaded successfully")
            except FileNotFoundError as e:
                logger.error(f"Policy file not found: {e}")
                logger.warning("Using default policies - ensure policy file exists for production")
            except Exception as e:
                logger.error(f"Failed to load policies: {e}", exc_info=True)
                raise

        # Note: EventRelayWorker will be added in Phase 2 for outbox pattern
        # Note: Kafka consumer will be added in Phase 2 for event consumption

        logger.info("All Entitlements Service components initialized successfully")

    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Shutdown service components gracefully."""
    logger.info("Shutting down Entitlements Service components...")

    try:
        # Note: Add specific cleanup tasks here if needed
        # Most resources are handled automatically by context managers

        logger.info("Entitlements Service components shutdown complete")

    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)
        # Don't raise on shutdown to allow graceful termination

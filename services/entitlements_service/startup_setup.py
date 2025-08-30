"""Startup and shutdown procedures for Entitlements Service.

This module handles initialization and cleanup of service components
including database connections, Redis clients, and policy loading.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from dishka import AsyncContainer
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger

from services.entitlements_service.kafka_consumer import EntitlementsKafkaConsumer
from services.entitlements_service.metrics import (
    get_metrics,
    setup_entitlements_service_database_monitoring,
)
from services.entitlements_service.protocols import CreditManagerProtocol, PolicyLoaderProtocol

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

        # Initialize metrics using singleton pattern with database metrics integration
        database_metrics = app.extensions.get("db_metrics")
        metrics = get_metrics(database_metrics)
        app.extensions["metrics"] = metrics
        logger.info("Metrics initialized with database integration")

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

            # Initialize EventRelayWorker for outbox pattern
            try:
                from huleedu_service_libs.outbox.relay import EventRelayWorker

                app.relay_worker = await request_container.get(EventRelayWorker)

                # Ensure the relay worker was created
                assert app.relay_worker is not None, "EventRelayWorker must be initialized"

                # Start the relay worker
                await app.relay_worker.start()
                logger.info("EventRelayWorker started for outbox pattern processing")
            except Exception as e:
                logger.error(f"Failed to initialize EventRelayWorker: {e}", exc_info=True)
                raise

        # Start Kafka consumer for resource consumption events (Phase 3)
        try:
            async with container() as request_container:
                credit_manager = await request_container.get(CreditManagerProtocol)
                # Redis client (Atomic) is provided by CoreProvider
                from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

                redis_client = await request_container.get(AtomicRedisClientProtocol)

            app.kafka_consumer = EntitlementsKafkaConsumer(
                kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                consumer_group="entitlements-resource-consumer",
                credit_manager=credit_manager,
                redis_client=redis_client,
            )
            app.consumer_task = asyncio.create_task(app.kafka_consumer.start_consumer())
            logger.info("Entitlements Kafka consumer background task started")
        except Exception as e:
            logger.error(f"Failed to start Entitlements Kafka consumer: {e}", exc_info=True)
            raise

        logger.info("All Entitlements Service components initialized successfully")

    except Exception as e:
        logger.critical(f"Failed to initialize services: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Shutdown service components gracefully."""
    logger.info("Shutting down Entitlements Service components...")

    try:
        # Stop Kafka consumer gracefully
        from huleedu_service_libs.logging_utils import create_service_logger as _l

        _logger = _l("entitlements_service.shutdown")
        try:
            # Access global app state is managed in app cleanup; no-op here
            _logger.debug("Shutdown steps executed")
        except Exception:
            pass

        logger.info("Entitlements Service components shutdown complete")

    except Exception as e:
        logger.error(f"Error during service shutdown: {e}", exc_info=True)
        # Don't raise on shutdown to allow graceful termination

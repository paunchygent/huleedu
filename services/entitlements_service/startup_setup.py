"""Startup and shutdown procedures for Entitlements Service.

This module handles initialization and cleanup of service components
including database connections, Redis clients, and policy loading.
"""

from __future__ import annotations

import asyncio
import datetime
from typing import TYPE_CHECKING

from dishka import AsyncContainer
from huleedu_service_libs.database import DatabaseHealthChecker
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.resilience.circuit_breaker import CircuitBreaker

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


async def _start_kafka_consumer_with_monitoring(app: "HuleEduApp") -> None:
    """Start Kafka consumer with automatic restart monitoring and circuit breaker."""

    async def start_consumer_task() -> None:
        try:
            consumer = app.kafka_consumer
            if consumer is None:
                logger.error("Kafka consumer not initialized; cannot start consumption")
                return
            await consumer.start_consumer()
        except Exception as e:
            logger.error(f"Entitlements Kafka consumer task failed: {e}", exc_info=True)
            # Allow monitor to handle restart

    # Initial task
    app.consumer_task = asyncio.create_task(start_consumer_task())

    # Monitor task
    app.consumer_monitor_task = asyncio.create_task(_monitor_kafka_consumer(app))


async def _monitor_kafka_consumer(app: "HuleEduApp") -> None:
    """Monitor Kafka consumer and restart with backoff; guard with circuit breaker."""
    restart_count = 0
    max_restart_attempts = 20
    restart_delay = 10.0
    max_restart_delay = 300.0
    breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=datetime.timedelta(minutes=2),
        success_threshold=1,
        expected_exception=Exception,
        name="entitlements_consumer_restart",
    )

    logger.info("Entitlements Kafka consumer monitor started")

    while not getattr(app, "_consumer_shutdown_requested", False):
        try:
            await asyncio.sleep(5.0)

            if getattr(app, "_consumer_shutdown_requested", False):
                break

            if app.consumer_task and app.consumer_task.done():
                try:
                    app.consumer_task.result()
                    logger.info("Entitlements Kafka consumer task completed normally")
                    # Reset counters
                    restart_count = 0
                    restart_delay = 10.0
                except Exception as e:
                    restart_count += 1
                    logger.error(
                        f"Entitlements Kafka consumer task failed (restart #{restart_count}): {e}",
                        exc_info=True,
                    )

                    if restart_count <= max_restart_attempts:
                        logger.info(f"Restarting consumer in {restart_delay:.1f}s...")
                        await asyncio.sleep(restart_delay)
                        if getattr(app, "_consumer_shutdown_requested", False):
                            break

                        # Attempt restart via circuit breaker
                        async def _do_restart() -> None:
                            async def start_consumer_task() -> None:
                                try:
                                    consumer = app.kafka_consumer
                                    if consumer is None:
                                        logger.error(
                                            "Kafka consumer not initialized; cannot restart"
                                        )
                                        return
                                    await consumer.start_consumer()
                                except Exception as e:
                                    logger.error(
                                        f"Entitlements Kafka consumer task failed: {e}",
                                        exc_info=True,
                                    )

                            app.consumer_task = asyncio.create_task(start_consumer_task())

                        try:
                            await breaker.call(_do_restart)
                            logger.info(
                                f"Entitlements Kafka consumer restarted (attempt #{restart_count})"
                            )
                            restart_delay = min(restart_delay * 1.2, max_restart_delay)
                        except Exception as restart_error:
                            logger.error(
                                f"Circuit breaker blocked restart or restart failed: "
                                f"{restart_error}",
                                exc_info=True,
                            )
                    else:
                        logger.error(
                            f"Consumer failed {max_restart_attempts} times; "
                            "stopping automatic restarts"
                        )
                        break

        except asyncio.CancelledError:
            logger.info("Entitlements Kafka consumer monitor cancelled")
            break
        except Exception as e:
            logger.error(f"Error in consumer monitor: {e}", exc_info=True)
            await asyncio.sleep(10.0)

    logger.info("Entitlements Kafka consumer monitor stopped")


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

        # Start Kafka consumer for resource consumption events (Phase 3) with monitoring
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
            # Initialize monitoring attributes if not present
            app.consumer_task = None
            app.consumer_monitor_task = None
            app._consumer_shutdown_requested = False
            await _start_kafka_consumer_with_monitoring(app)
            logger.info("Entitlements Kafka consumer started with monitoring")
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

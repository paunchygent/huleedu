"""Startup and shutdown logic for Batch Orchestrator Service."""

from __future__ import annotations

import asyncio

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.database import DatabaseMetrics
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from huleedu_service_libs.quart_app import HuleEduApp
from quart_dishka import QuartDishka

from services.batch_orchestrator_service.config import Settings
from services.batch_orchestrator_service.di import (
    CoreInfrastructureProvider,
    EventHandlingProvider,
    ExternalClientsProvider,
    InitiatorMapProvider,
    NotificationServiceProvider,
    PhaseInitiatorsProvider,
    PipelineCoordinationProvider,
    RepositoryAndPublishingProvider,
    StateManagementProvider,
)
from services.batch_orchestrator_service.implementations.batch_repository_postgres_impl import (
    PostgreSQLBatchRepositoryImpl,
)
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer
from services.batch_orchestrator_service.metrics import get_metrics

logger = create_service_logger("bos.startup")

# Global references for service management (unavoidable for Quart lifecycle)
kafka_consumer_instance: BatchKafkaConsumer | None = None
consumer_task: asyncio.Task | None = None
event_relay_worker: EventRelayWorker | None = None


async def initialize_services(app: HuleEduApp, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, metrics, and Kafka consumer."""
    global kafka_consumer_instance, consumer_task, event_relay_worker

    try:
        # Initialize DI container with all provider instances
        # OutboxProvider automatically provides environment-based settings
        container = make_async_container(
            CoreInfrastructureProvider(),
            RepositoryAndPublishingProvider(),
            ExternalClientsProvider(),
            PhaseInitiatorsProvider(),
            NotificationServiceProvider(),
            StateManagementProvider(),
            PipelineCoordinationProvider(),
            EventHandlingProvider(),
            InitiatorMapProvider(),
            OutboxProvider(),  # Provides environment-aware outbox settings
        )

        # Initialize guaranteed HuleEduApp infrastructure immediately
        app.container = container
        QuartDishka(app=app, container=container)

        # Initialize database schema directly (bypasses DI scoping issues)
        db_repository = PostgreSQLBatchRepositoryImpl(settings)
        await db_repository.initialize_db_schema()
        logger.info("Database schema initialized successfully")

        # Initialize guaranteed database engine infrastructure
        app.database_engine = db_repository.db_infrastructure.engine
        logger.info("Database engine initialized for guaranteed access")

        # Get database metrics from DI container
        async with container() as request_container:
            database_metrics = await request_container.get(DatabaseMetrics)

        # Initialize metrics using shared metrics module with database metrics integration
        metrics = get_metrics(database_metrics)

        # Store metrics in app extensions (HuleEduApp guarantees extensions dict)
        app.extensions["metrics"] = metrics

        # Initialize tracing
        tracer = init_tracing("batch_orchestrator_service")
        app.extensions["tracer"] = tracer
        setup_tracing_middleware(app, tracer)
        logger.info("Distributed tracing initialized")

        async with container() as request_container:
            # Get Kafka consumer from DI container (properly configured)
            kafka_consumer_instance = await request_container.get(BatchKafkaConsumer)

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")

            # Start EventRelayWorker for outbox pattern
            event_relay_worker = await request_container.get(EventRelayWorker)
            await event_relay_worker.start()
            app.extensions["relay_worker"] = event_relay_worker
            logger.info("EventRelayWorker started for outbox pattern")

        logger.info(
            "Batch Orchestrator Service DI container, quart-dishka integration, "
            "Kafka consumer, and outbox worker initialized successfully.",
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Batch Orchestrator Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the Kafka consumer, outbox worker, and background tasks."""
    global kafka_consumer_instance, consumer_task, event_relay_worker

    try:
        # Stop EventRelayWorker first
        if event_relay_worker:
            logger.info("Stopping EventRelayWorker...")
            await event_relay_worker.stop()
            logger.info("EventRelayWorker stopped")

        if kafka_consumer_instance:
            logger.info("Stopping Kafka consumer...")
            await kafka_consumer_instance.stop_consumer()

        if consumer_task and not consumer_task.done():
            logger.info("Cancelling consumer background task...")
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                logger.info("Consumer background task cancelled successfully")

        logger.info("Batch Orchestrator Service shutdown completed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)

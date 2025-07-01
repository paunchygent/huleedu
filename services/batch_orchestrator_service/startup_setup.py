"""Startup and shutdown logic for Batch Orchestrator Service."""

from __future__ import annotations

import asyncio

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
from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs import init_tracing
from huleedu_service_libs.middleware.frameworks.quart_middleware import setup_tracing_middleware
from services.batch_orchestrator_service.kafka_consumer import BatchKafkaConsumer
from services.batch_orchestrator_service.metrics import get_http_metrics
from quart import Quart
from quart_dishka import QuartDishka

from services.batch_orchestrator_service.implementations.batch_repository_postgres_impl import (
    PostgreSQLBatchRepositoryImpl,
)

logger = create_service_logger("bos.startup")

# Global references for service management (unavoidable for Quart lifecycle)
kafka_consumer_instance: BatchKafkaConsumer | None = None
consumer_task: asyncio.Task | None = None


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, metrics, and Kafka consumer."""
    global kafka_consumer_instance, consumer_task

    try:
        # Initialize DI container with all provider instances
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
        )
        QuartDishka(app=app, container=container)

        # Initialize database schema directly (bypasses DI scoping issues)
        db_repository = PostgreSQLBatchRepositoryImpl(settings)
        await db_repository.initialize_db_schema()
        logger.info("Database schema initialized successfully")

        # Initialize metrics using shared metrics module
        metrics = get_http_metrics()

        # Store metrics in app context (proper Quart pattern)
        app.extensions = getattr(app, "extensions", {})
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

        logger.info(
            "Batch Orchestrator Service DI container, quart-dishka integration, "
            "and Kafka consumer initialized successfully.",
        )
    except Exception as e:
        logger.critical(f"Failed to initialize Batch Orchestrator Service: {e}", exc_info=True)
        raise


async def shutdown_services() -> None:
    """Gracefully shutdown the Kafka consumer and background tasks."""
    global kafka_consumer_instance, consumer_task

    try:
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

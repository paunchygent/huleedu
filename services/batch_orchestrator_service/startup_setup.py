"""Startup and shutdown logic for Batch Orchestrator Service."""

from __future__ import annotations

import asyncio
from typing import Optional

from api.batch_routes import set_batch_operations_metric
from config import Settings
from di import BatchOrchestratorServiceProvider
from dishka import make_async_container
from huleedu_service_libs.logging_utils import create_service_logger
from kafka_consumer import BatchKafkaConsumer
from prometheus_client import CollectorRegistry, Counter, Histogram
from protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
    PipelinePhaseCoordinatorProtocol,
)
from quart import Quart
from quart_dishka import QuartDishka

logger = create_service_logger("bos.startup")

# Global references for service management (unavoidable for Quart lifecycle)
kafka_consumer_instance: Optional[BatchKafkaConsumer] = None
consumer_task: Optional[asyncio.Task] = None


async def initialize_services(app: Quart, settings: Settings) -> None:
    """Initialize DI container, Quart-Dishka integration, metrics, and Kafka consumer."""
    global kafka_consumer_instance, consumer_task

    try:
        # Initialize DI container
        container = make_async_container(BatchOrchestratorServiceProvider())
        QuartDishka(app=app, container=container)

        # Initialize metrics with DI registry and store in app context
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            metrics = _create_metrics(registry)

            # Store metrics in app context (proper Quart pattern)
            app.extensions = getattr(app, "extensions", {})
            app.extensions["metrics"] = metrics

            # Share batch operations metric with routes module (legacy support)
            set_batch_operations_metric(metrics["batch_operations"])

            # Get dependencies for Kafka consumer
            event_publisher = await request_container.get(BatchEventPublisherProtocol)
            batch_repo = await request_container.get(BatchRepositoryProtocol)
            phase_coordinator = await request_container.get(PipelinePhaseCoordinatorProtocol)

            # Initialize Kafka consumer
            kafka_consumer_instance = BatchKafkaConsumer(
                kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                consumer_group=f"{settings.SERVICE_NAME}-consumer",
                event_publisher=event_publisher,
                batch_repo=batch_repo,
                phase_coordinator=phase_coordinator,
            )

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")

        logger.info(
            "Batch Orchestrator Service DI container, quart-dishka integration, "
            "and Kafka consumer initialized successfully."
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


def _create_metrics(registry: CollectorRegistry) -> dict:
    """Create Prometheus metrics instances."""
    return {
        "request_count": Counter(
            "http_requests_total",
            "Total HTTP requests",
            ["method", "endpoint", "status_code"],
            registry=registry,
        ),
        "request_duration": Histogram(
            "http_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "endpoint"],
            registry=registry,
        ),
        "batch_operations": Counter(
            "batch_operations_total",
            "Total batch operations",
            ["operation", "status"],
            registry=registry,
        ),
    }

"""
HuleEdu Batch Orchestrator Service Application.

This module implements the Batch Orchestrator Service REST API using Quart framework.
The service acts as the primary orchestrator for batch processing workflows.
"""

import asyncio
from typing import Optional

# Import Blueprints
from api.batch_routes import batch_bp, set_batch_operations_metric
from api.health_routes import health_bp
from config import settings
from di import BatchOrchestratorServiceProvider
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from kafka_consumer import BatchKafkaConsumer
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Histogram,
)
from protocols import BatchEventPublisherProtocol, BatchRepositoryProtocol
from quart import Quart, Response, g, request
from quart_dishka import QuartDishka

# Configure structured logging for the service
configure_service_logging("batch-service", log_level=settings.LOG_LEVEL)
logger = create_service_logger("bos.app")

app = Quart(__name__)

# Prometheus metrics (will be registered with DI-provided registry)
REQUEST_COUNT: Optional[Counter] = None
REQUEST_DURATION: Optional[Histogram] = None
BATCH_OPERATIONS: Optional[Counter] = None

# Global reference to Kafka consumer and background task
kafka_consumer_instance: Optional[BatchKafkaConsumer] = None
consumer_task: Optional[asyncio.Task] = None


@app.before_serving
async def startup() -> None:
    """Initialize the DI container, setup quart-dishka integration, and start Kafka consumer."""
    global kafka_consumer_instance, consumer_task

    try:
        container = make_async_container(BatchOrchestratorServiceProvider())
        QuartDishka(app=app, container=container)

        # Initialize metrics with DI registry
        async with container() as request_container:
            registry = await request_container.get(CollectorRegistry)
            _initialize_metrics(registry)

            # Get dependencies for Kafka consumer
            event_publisher = await request_container.get(BatchEventPublisherProtocol)
            batch_repo = await request_container.get(BatchRepositoryProtocol)

            # Initialize Kafka consumer
            kafka_consumer_instance = BatchKafkaConsumer(
                kafka_bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                consumer_group=f"{settings.SERVICE_NAME}-consumer",
                event_publisher=event_publisher,
                batch_repo=batch_repo,
            )

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")

        logger.info(
            "Batch Orchestrator Service DI container, quart-dishka integration, "
            "and Kafka consumer initialized successfully."
        )
    except Exception as e:
        logger.critical(
            f"Failed to initialize Batch Orchestrator Service: {e}", exc_info=True
        )


@app.after_serving
async def shutdown() -> None:
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


def _initialize_metrics(registry: CollectorRegistry) -> None:
    """Initialize Prometheus metrics with the provided registry."""
    global REQUEST_COUNT, REQUEST_DURATION, BATCH_OPERATIONS

    REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status_code"],
        registry=registry,
    )

    REQUEST_DURATION = Histogram(
        "http_request_duration_seconds",
        "HTTP request duration in seconds",
        ["method", "endpoint"],
        registry=registry,
    )

    BATCH_OPERATIONS = Counter(
        "batch_operations_total",
        "Total batch operations",
        ["operation", "status"],
        registry=registry,
    )

    # Share metrics with Blueprint modules
    set_batch_operations_metric(BATCH_OPERATIONS)


@app.before_request
async def before_request() -> None:
    """Record request start time for duration metrics."""
    import time

    g.start_time = time.time()


@app.after_request
async def after_request(response: Response) -> Response:
    """Record metrics after each request."""
    try:
        import time

        start_time = getattr(g, "start_time", None)
        if start_time is not None and REQUEST_COUNT is not None and REQUEST_DURATION is not None:
            duration = time.time() - start_time

            # Get endpoint name (remove query parameters)
            endpoint = request.path
            method = request.method
            status_code = str(response.status_code)

            # Record metrics
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(duration)

    except Exception as e:
        logger.error(f"Error recording request metrics: {e}")

    return response


# Register Blueprints
app.register_blueprint(batch_bp)
app.register_blueprint(health_bp)

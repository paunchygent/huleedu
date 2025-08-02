from __future__ import annotations

import asyncio
from typing import Any

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from huleedu_service_libs.logging_utils import create_service_logger

try:
    from opentelemetry import trace
    from opentelemetry.exporter.jaeger.thrift import JaegerExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False

from services.websocket_service.config import settings
from services.websocket_service.di import WebSocketServiceProvider
from services.websocket_service.protocols import FileEventConsumerProtocol

logger = create_service_logger("websocket.startup")

# Global references for service management
kafka_consumer_instance: FileEventConsumerProtocol | None = None
consumer_task: asyncio.Task | None = None


def create_di_container() -> Any:
    """Create the dependency injection container."""
    logger.info("Creating DI container")
    container = make_async_container(WebSocketServiceProvider())
    return container


def setup_dependency_injection(app: FastAPI, container: Any) -> None:
    """Setup Dishka dependency injection for FastAPI."""
    logger.info("Setting up dependency injection")
    setup_dishka(container, app)


def setup_tracing(app: FastAPI) -> None:
    """Setup distributed tracing with Jaeger."""
    logger.info("Setting up distributed tracing")

    # Create a TracerProvider with service name
    resource = Resource.create({"service.name": settings.SERVICE_NAME})
    tracer_provider = TracerProvider(resource=resource)

    # Configure Jaeger exporter
    jaeger_exporter = JaegerExporter(
        agent_host_name=settings.JAEGER_ENDPOINT.split("://")[1].split(":")[0],
        agent_port=6831,  # Default Jaeger agent port
    )

    # Add span processor
    span_processor = BatchSpanProcessor(jaeger_exporter)
    tracer_provider.add_span_processor(span_processor)

    # Set the global tracer provider
    trace.set_tracer_provider(tracer_provider)

    # Instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)

    logger.info("Distributed tracing setup complete")


async def start_kafka_consumer(container: Any) -> None:
    """Start the Kafka consumer as a background task."""
    global kafka_consumer_instance, consumer_task

    try:
        async with container() as request_container:
            # Get Kafka consumer from DI container
            kafka_consumer_instance = await request_container.get(FileEventConsumerProtocol)

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")
    except Exception as e:
        logger.error(f"Failed to start Kafka consumer: {e}", exc_info=True)
        raise


async def stop_kafka_consumer() -> None:
    """Stop the Kafka consumer and background tasks."""
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

        logger.info("Kafka consumer shutdown completed")
    except Exception as e:
        logger.error(f"Error during Kafka consumer shutdown: {e}", exc_info=True)

from __future__ import annotations

import asyncio
from typing import Any

from dishka import make_async_container
from dishka.integrations.fastapi import setup_dishka
from fastapi import FastAPI
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.middleware.frameworks.fastapi_middleware import (
    setup_tracing_middleware,
)

from services.websocket_service.config import settings
from services.websocket_service.di import WebSocketServiceProvider
from services.websocket_service.protocols import NotificationEventConsumerProtocol

# Global references for service management
kafka_consumer_instance: NotificationEventConsumerProtocol | None = None
consumer_task: asyncio.Task | None = None


def create_di_container() -> Any:
    """Create the dependency injection container."""
    logger = create_service_logger("websocket.startup")
    logger.info("Creating DI container")
    container = make_async_container(WebSocketServiceProvider())
    return container


def setup_dependency_injection(app: FastAPI, container: Any) -> None:
    """Setup Dishka dependency injection for FastAPI."""
    logger = create_service_logger("websocket.startup")
    logger.info("Setting up dependency injection")
    setup_dishka(container, app)


def setup_tracing(app: FastAPI) -> None:
    """Setup distributed tracing with Jaeger using OTLP exporter."""
    logger = create_service_logger("websocket.startup")
    logger.info("Setting up distributed tracing")
    tracer = init_tracing(settings.SERVICE_NAME)
    setup_tracing_middleware(app, tracer)
    logger.info("Distributed tracing setup complete")


async def start_kafka_consumer(container: Any) -> None:
    """Start the Kafka consumer as a background task."""
    global kafka_consumer_instance, consumer_task
    logger = create_service_logger("websocket.startup")

    try:
        async with container() as request_container:
            # Get Kafka consumer from DI container
            kafka_consumer_instance = await request_container.get(NotificationEventConsumerProtocol)

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")
    except Exception as e:
        logger.error(f"Failed to start Kafka consumer: {e}", exc_info=True)
        raise


async def stop_kafka_consumer() -> None:
    """Stop the Kafka consumer and background tasks."""
    global kafka_consumer_instance, consumer_task
    logger = create_service_logger("websocket.startup")

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

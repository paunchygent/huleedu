from __future__ import annotations

import asyncio

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from huleedu_service_libs.middleware.frameworks.quart_middleware import (
    setup_tracing_middleware,
)
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from quart import Quart
from quart_dishka import QuartDishka

from services.identity_service.config import Settings
from services.identity_service.di import (
    CoreProvider,
    DomainHandlerProvider,
    IdentityImplementationsProvider,
)
from services.identity_service.kafka_consumer import IdentityKafkaConsumer
from services.identity_service.models_db import Base

logger = create_service_logger("identity_service.startup")


async def initialize_services(app: Quart, settings: Settings) -> None:
    configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
    logger.info("Identity Service initializing")

    # DI container and quart integration
    container = make_async_container(
        CoreProvider(),
        IdentityImplementationsProvider(),
        DomainHandlerProvider(),
        OutboxProvider(),
    )
    QuartDishka(app=app, container=container)

    # Tracing
    tracer = init_tracing("identity_service")
    app.extensions = getattr(app, "extensions", {})
    app.extensions["tracer"] = tracer
    setup_tracing_middleware(app, tracer)

    # Start outbox relay worker and set database engine
    async with container() as request_container:
        from sqlalchemy.ext.asyncio import AsyncEngine

        # Get database engine for health checks
        database_engine = await request_container.get(AsyncEngine)
        app.database_engine = database_engine  # type: ignore

        # Initialize database schema (safety net for fresh databases)
        async with database_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        relay_worker = await request_container.get(EventRelayWorker)
        await relay_worker.start()
        app.extensions["relay_worker"] = relay_worker
        logger.info("EventRelayWorker started for outbox pattern")

        # Start IdentityKafkaConsumer for internal event processing
        identity_kafka_consumer = await request_container.get(IdentityKafkaConsumer)
        consumer_task = asyncio.create_task(identity_kafka_consumer.start_consumer())
        app.extensions["identity_kafka_consumer"] = identity_kafka_consumer
        app.extensions["identity_kafka_consumer_task"] = consumer_task
        logger.info("IdentityKafkaConsumer started for internal event processing")


async def shutdown_services(app: Quart | None = None) -> None:
    if app and hasattr(app, "extensions"):
        # Stop IdentityKafkaConsumer
        if "identity_kafka_consumer" in app.extensions:
            identity_kafka_consumer = app.extensions["identity_kafka_consumer"]
            await identity_kafka_consumer.stop_consumer()
            logger.info("IdentityKafkaConsumer stopped")

        if "identity_kafka_consumer_task" in app.extensions:
            consumer_task = app.extensions["identity_kafka_consumer_task"]
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            logger.info("IdentityKafkaConsumer task cancelled")

        # Stop relay worker
        if "relay_worker" in app.extensions:
            relay_worker = app.extensions["relay_worker"]
            await relay_worker.stop()
    logger.info("Identity Service shutdown complete")

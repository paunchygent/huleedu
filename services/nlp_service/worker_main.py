"""
NLP Service Kafka Worker Main Entry Point.

This module implements the Kafka consumer worker for the NLP Service,
handling incoming batch NLP analysis requests using DI pattern.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
from sqlalchemy.ext.asyncio import create_async_engine

from services.nlp_service.config import settings
from services.nlp_service.di import NlpServiceProvider
from services.nlp_service.kafka_consumer import NlpKafkaConsumer

logger = create_service_logger("nlp_service.worker_main")

# Global state for graceful shutdown
should_stop = False
kafka_consumer_instance: NlpKafkaConsumer | None = None
consumer_task: asyncio.Task | None = None


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    global should_stop

    def signal_handler(signum: int, frame: object) -> None:
        global should_stop
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        should_stop = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def main() -> None:
    """Main entry point."""
    global kafka_consumer_instance, consumer_task

    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        log_level=settings.LOG_LEVEL,
    )

    # Setup signal handlers
    setup_signal_handlers()

    logger.info("Starting NLP Service Kafka Worker")

    # Initialize tracing (this sets up the global tracer provider)
    init_tracing("nlp_service")
    logger.info("OpenTelemetry tracing initialized")

    # Initialize database engine
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_size=getattr(settings, "DATABASE_POOL_SIZE", 5),
        max_overflow=getattr(settings, "DATABASE_MAX_OVERFLOW", 10),
        pool_pre_ping=getattr(settings, "DATABASE_POOL_PRE_PING", True),
        pool_recycle=getattr(settings, "DATABASE_POOL_RECYCLE", 1800),
    )

    # Initialize dependency injection container with OutboxProvider
    container = make_async_container(
        NlpServiceProvider(engine=engine),
        OutboxProvider(),  # Provides OutboxRepositoryProtocol and EventRelayWorker
    )

    event_relay_worker = None
    try:
        async with container() as request_container:
            # Get Kafka consumer from DI container
            kafka_consumer_instance = await request_container.get(NlpKafkaConsumer)

            # Get event relay worker for outbox pattern
            event_relay_worker = await request_container.get(EventRelayWorker)

            # Start event relay worker for outbox pattern
            await event_relay_worker.start()
            logger.info("Event relay worker started for outbox pattern")

            # Start Kafka consumer as background task
            consumer_task = asyncio.create_task(kafka_consumer_instance.start_consumer())
            logger.info("Kafka consumer background task started")

            # Wait for shutdown signal
            while not should_stop:
                await asyncio.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Graceful shutdown
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

        # Stop event relay worker
        if event_relay_worker:
            try:
                await event_relay_worker.stop()
                logger.info("Event relay worker stopped")
            except Exception as e:
                logger.error(f"Error stopping event relay worker: {e}")

        # Cleanup engine
        await engine.dispose()

    logger.info("NLP Service Worker shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())

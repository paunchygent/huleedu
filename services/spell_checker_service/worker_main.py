"""
Essay Spell Checker Service Kafka Worker Main Entry Point.

This module implements the Kafka consumer worker for the Spell Checker Service,
handling incoming spellcheck requests using DI pattern.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

from services.spell_checker_service.config import settings
from services.spell_checker_service.di import SpellCheckerServiceProvider
from services.spell_checker_service.kafka_consumer import SpellCheckerKafkaConsumer

logger = create_service_logger("spell_checker.worker_main")

# Global state for graceful shutdown
should_stop = False
kafka_consumer_instance: SpellCheckerKafkaConsumer | None = None
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

    logger.info("Starting Spell Checker Service Kafka Worker")

    # Initialize tracing (this sets up the global tracer provider)
    init_tracing("spell_checker_service")
    logger.info("OpenTelemetry tracing initialized")

    # Initialize dependency injection container
    container = make_async_container(SpellCheckerServiceProvider())

    try:
        async with container() as request_container:
            # Get Kafka consumer from DI container (properly configured)
            kafka_consumer_instance = await request_container.get(SpellCheckerKafkaConsumer)

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

    logger.info("Spell Checker Service Worker shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())

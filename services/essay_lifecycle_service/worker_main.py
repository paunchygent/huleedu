"""
Essay Lifecycle Service Kafka Worker Main Entry Point.

This module implements the Kafka consumer worker for the Essay Lifecycle Service,
handling incoming events for batch coordination, command processing, and service results.
"""

from __future__ import annotations

import asyncio
import signal
import sys

from aiokafka import AIOKafkaConsumer
from common_core.enums import ProcessingEvent, topic_name
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

from services.essay_lifecycle_service.batch_command_handlers import process_single_message
from services.essay_lifecycle_service.config import settings
from services.essay_lifecycle_service.di import (
    BatchCoordinationProvider,
    CommandHandlerProvider,
    CoreInfrastructureProvider,
    ServiceClientsProvider,
)
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    ServiceResultHandler,
)

logger = create_service_logger("worker_main")

# Global state for graceful shutdown
should_stop = False


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""
    global should_stop

    def signal_handler(signum: int, frame: object) -> None:
        global should_stop
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        should_stop = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


async def create_kafka_consumer() -> AIOKafkaConsumer:
    """Create and configure Kafka consumer."""
    # Define topics using topic_name() function for consistency
    topics = [
        topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED),
        topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
        topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
        topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED),  # Added for validation coordination
        topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
        topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND),
        topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED),
    ]

    consumer = AIOKafkaConsumer(
        *topics,
        bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
        group_id=settings.CONSUMER_GROUP,
        client_id=settings.CONSUMER_CLIENT_ID,
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        auto_commit_interval_ms=1000,
    )

    await consumer.start()
    logger.info(
        "Kafka consumer started",
        extra={
            "group_id": settings.CONSUMER_GROUP,
            "topics": topics,
        },
    )
    return consumer


async def run_consumer_loop(
    consumer: AIOKafkaConsumer,
    batch_coordination_handler: BatchCoordinationHandler,
    batch_command_handler: BatchCommandHandler,
    service_result_handler: ServiceResultHandler,
) -> None:
    """Main message processing loop."""
    global should_stop

    logger.info("Starting message processing loop")

    try:
        async for msg in consumer:
            if should_stop:
                logger.info("Shutdown requested, stopping message processing")
                break

            try:
                success = await process_single_message(
                    msg=msg,
                    batch_coordination_handler=batch_coordination_handler,
                    batch_command_handler=batch_command_handler,
                    service_result_handler=service_result_handler,
                )

                if success:
                    logger.debug(
                        "Successfully processed message",
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                else:
                    logger.warning(
                        "Failed to process message",
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )

            except Exception as e:
                logger.error(
                    "Error processing message",
                    extra={
                        "error": str(e),
                        "topic": msg.topic,
                        "partition": msg.partition,
                        "offset": msg.offset,
                    },
                )

    except Exception as e:
        logger.error(f"Error in message processing loop: {e}")
        raise


async def main() -> None:
    """Main entry point."""
    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        log_level=settings.LOG_LEVEL,
    )

    # Setup signal handlers
    setup_signal_handlers()

    logger.info("Starting Essay Lifecycle Service Kafka Worker")

    # Initialize dependency injection container with all provider classes
    container = make_async_container(
        CoreInfrastructureProvider(),
        ServiceClientsProvider(),
        CommandHandlerProvider(),
        BatchCoordinationProvider(),
    )

    consumer = None
    try:
        async with container() as request_container:
            # Get dependencies from DI container
            batch_coordination_handler = await request_container.get(BatchCoordinationHandler)
            batch_command_handler = await request_container.get(BatchCommandHandler)
            service_result_handler = await request_container.get(ServiceResultHandler)

            logger.info("Dependencies injected successfully")

            # Create and start Kafka consumer
            consumer = await create_kafka_consumer()

            # Run consumer loop
            await run_consumer_loop(
                consumer=consumer,
                batch_coordination_handler=batch_coordination_handler,
                batch_command_handler=batch_command_handler,
                service_result_handler=service_result_handler,
            )

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        if consumer:
            try:
                await consumer.stop()
                logger.info("Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka consumer: {e}")

    logger.info("Essay Lifecycle Service Worker shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())

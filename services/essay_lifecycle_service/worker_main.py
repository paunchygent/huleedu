"""
Essay Lifecycle Service Kafka Worker Main Entry Point.

This module implements the Kafka consumer worker for the Essay Lifecycle Service,
handling incoming events for batch coordination, command processing, and service results.
"""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiokafka import AIOKafkaConsumer
from common_core.enums import ProcessingEvent, topic_name
from dishka import make_async_container
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger

from services.essay_lifecycle_service.batch_command_handlers import process_single_message
from services.essay_lifecycle_service.config import settings
from services.essay_lifecycle_service.di import EssayLifecycleServiceProvider
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    ServiceResultHandler,
)

logger = create_service_logger("worker_main")


class WorkerState:
    """Global worker state management."""

    def __init__(self) -> None:
        self.should_stop = False
        self.consumer: AIOKafkaConsumer | None = None


worker_state = WorkerState()


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum: int, frame: object) -> None:
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        worker_state.should_stop = True

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


@asynccontextmanager
async def kafka_consumer_context() -> AsyncIterator[AIOKafkaConsumer]:
    """Context manager for Kafka consumer lifecycle."""
    # Define topics using topic_name() function for consistency
    topics = [
        topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED),
        topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
        topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED),
        topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND),
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

    try:
        await consumer.start()
        worker_state.consumer = consumer
        logger.info(
            "Kafka consumer started",
            extra={
                "group_id": settings.CONSUMER_GROUP,
                "topics": list(consumer.subscription()),
            },
        )
        yield consumer
    except Exception as e:
        logger.error(f"Error starting Kafka consumer: {e}")
        raise
    finally:
        try:
            await consumer.stop()
            logger.info("Kafka consumer stopped")
        except Exception as e:
            logger.error(f"Error stopping Kafka consumer: {e}")
        finally:
            worker_state.consumer = None


async def process_messages(
    consumer: AIOKafkaConsumer,
    batch_coordination_handler: BatchCoordinationHandler,
    batch_command_handler: BatchCommandHandler,
    service_result_handler: ServiceResultHandler,
) -> None:
    """Main message processing loop."""
    logger.info("Starting message processing loop")

    try:
        async for msg in consumer:
            if worker_state.should_stop:
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


async def run_worker() -> None:
    """Main worker execution logic."""
    logger.info("Starting Essay Lifecycle Service Kafka Worker")

    # Initialize dependency injection container
    container = make_async_container(EssayLifecycleServiceProvider())
    async with container() as request_container:
        # Get dependencies
        batch_coordination_handler = await request_container.get(BatchCoordinationHandler)
        batch_command_handler = await request_container.get(BatchCommandHandler)
        service_result_handler = await request_container.get(ServiceResultHandler)

        logger.info("Dependencies injected successfully")

        # Start Kafka consumer and process messages
        async with kafka_consumer_context() as consumer:
            await process_messages(
                consumer=consumer,
                batch_coordination_handler=batch_coordination_handler,
                batch_command_handler=batch_command_handler,
                service_result_handler=service_result_handler,
            )


async def main() -> None:
    """Main entry point."""
    # Configure logging
    configure_service_logging(
        service_name=settings.SERVICE_NAME,
        log_level=settings.LOG_LEVEL,
    )

    # Setup signal handlers
    setup_signal_handlers()

    # Run the worker
    try:
        await run_worker()
    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())

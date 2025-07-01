"""
Essay Lifecycle Service Kafka Worker Main Entry Point.

This module implements the Kafka consumer worker for the Essay Lifecycle Service,
handling incoming events for batch coordination, command processing, and service results.
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer, ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.idempotency import idempotent_consumer
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.protocols import AtomicRedisClientProtocol
from opentelemetry.trace import Tracer

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
        enable_auto_commit=False,  # Manual commit for reliable message processing
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
    redis_client: AtomicRedisClientProtocol,
    tracer: Tracer | None = None,
) -> None:
    """Main message processing loop with idempotency support."""
    global should_stop

    logger.info("Starting message processing loop with idempotency")

    # Apply idempotency decorator to message processing
    @idempotent_consumer(redis_client=redis_client, ttl_seconds=86400)
    async def handle_message_idempotently(msg: ConsumerRecord) -> bool:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=tracer,
        )

    try:
        async for msg in consumer:
            if should_stop:
                logger.info("Shutdown requested, stopping message processing")
                break

            try:
                result = await handle_message_idempotently(msg)

                # A result of `True` means success, `None` means duplicate (which is also a success state for commit)
                if result is True or result is None:
                    # Commit offset after successful processing or after skipping a duplicate
                    await consumer.commit()
                    if result:
                        logger.debug(
                            "Successfully processed and committed message",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )
                    else:
                        logger.info(
                            "Duplicate message skipped, offset committed",
                            extra={
                                "topic": msg.topic,
                                "partition": msg.partition,
                                "offset": msg.offset,
                            },
                        )
                else:  # result is False
                    logger.warning(
                        "Failed to process message, not committing offset",
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

    # Initialize tracing (this sets up the global tracer provider)
    tracer = init_tracing("essay_lifecycle_service")
    logger.info("OpenTelemetry tracing initialized")

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
            redis_client = await request_container.get(AtomicRedisClientProtocol)
            tracer = await request_container.get(Tracer)

            logger.info("Dependencies injected successfully")

            # Create and start Kafka consumer
            consumer = await create_kafka_consumer()

            # Run consumer loop
            await run_consumer_loop(
                consumer=consumer,
                batch_coordination_handler=batch_coordination_handler,
                batch_command_handler=batch_command_handler,
                service_result_handler=service_result_handler,
                redis_client=redis_client,
                tracer=tracer,
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

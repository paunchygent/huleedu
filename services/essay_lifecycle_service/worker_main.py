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
    from collections.abc import Awaitable, Callable

    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer, ConsumerRecord, TopicPartition
from common_core.event_enums import ProcessingEvent, topic_name
from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.idempotency_v2 import (
    IdempotencyConfig,
    idempotent_consumer,
)
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.outbox import EventRelayWorker, OutboxProvider
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
    ConsumerRecoveryManager,
    KafkaConsumerHealthMonitor,
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
    health_monitor: KafkaConsumerHealthMonitor,
    recovery_manager: ConsumerRecoveryManager,
    tracer: Tracer | None = None,
) -> None:
    """Main message processing loop with idempotency support."""
    global should_stop

    # Define the base message handler with confirmation callback
    async def _process_message_wrapper(
        msg: ConsumerRecord, *, confirm_idempotency: Callable[[], Awaitable[None]] | None = None
    ) -> bool:
        return await process_single_message(
            msg=msg,
            batch_coordination_handler=batch_coordination_handler,
            batch_command_handler=batch_command_handler,
            service_result_handler=service_result_handler,
            tracer=tracer,
            confirm_idempotency=confirm_idempotency,
        )

    # Create a wrapper that returns bool | None for non-idempotent case
    async def _process_message_non_idempotent(msg: ConsumerRecord) -> bool | None:
        # In non-idempotent mode, we never return None (no duplicates detected)
        result = await _process_message_wrapper(msg)
        return result

    # Apply idempotency based on settings
    handle_message_idempotently: Callable[[ConsumerRecord], Awaitable[bool | None]]

    if settings.DISABLE_IDEMPOTENCY:
        logger.info("Starting message processing loop WITHOUT idempotency (testing mode)")
        handle_message_idempotently = _process_message_non_idempotent
    else:
        logger.info("Starting message processing loop with enhanced idempotency v2")
        # Configure advanced idempotency with service namespacing and event-type specific TTLs
        idempotency_config = IdempotencyConfig(
            service_name=settings.SERVICE_NAME,
            enable_debug_logging=False,  # Production mode - reduced logging
        )

        # Apply transaction-aware idempotency decorator
        decorated_handler = idempotent_consumer(
            redis_client=redis_client, config=idempotency_config
        )(_process_message_wrapper)

        # Explicitly define the handler with the expected signature
        async def handle_message_idempotently(msg: ConsumerRecord) -> bool | None:
            return await decorated_handler(msg)

    try:
        async for msg in consumer:
            if should_stop:
                logger.info("Shutdown requested, stopping message processing")
                break

            # Check consumer health periodically and attempt recovery if needed
            if health_monitor.should_check_health():
                if not health_monitor.is_healthy():
                    logger.warning(
                        "Consumer health check failed, attempting recovery",
                        extra=health_monitor.get_health_metrics(),
                    )
                    
                    # Only attempt recovery if not already in progress
                    if not recovery_manager.is_recovery_in_progress():
                        try:
                            recovery_success = await recovery_manager.initiate_recovery(consumer)
                            if recovery_success:
                                logger.info("Consumer recovery completed successfully")
                            else:
                                logger.error(
                                    "Consumer recovery failed - soft recovery unsuccessful, "
                                    "hard recovery (consumer recreation) may be needed"
                                )
                                # Note: Hard recovery (consumer recreation) would be handled
                                # by service orchestration layer, not within this loop
                        except Exception as recovery_error:
                            logger.error(
                                f"Recovery attempt failed with exception: {recovery_error}",
                                exc_info=True
                            )
                    else:
                        logger.debug("Recovery already in progress, skipping duplicate attempt")

            try:
                result = await handle_message_idempotently(msg)

                # Handle three cases: True (success), None (duplicate), False (failure)
                if result is None:
                    # Duplicate message - commit immediately to prevent redelivery
                    tp = TopicPartition(msg.topic, msg.partition)
                    await consumer.commit({tp: msg.offset + 1})
                    logger.info(
                        "Duplicate message skipped, offset committed immediately",
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                    # Record successful processing for health monitoring
                    await health_monitor.record_message_processed()
                elif result is True:
                    # Success - commit specific offset after processing
                    tp = TopicPartition(msg.topic, msg.partition)
                    await consumer.commit({tp: msg.offset + 1})
                    logger.debug(
                        "Successfully processed and committed message",
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                    # Record successful processing for health monitoring
                    await health_monitor.record_message_processed()
                else:  # result is False
                    logger.error(
                        "Message processing failed - offset not committed",
                        extra={
                            "topic": msg.topic,
                            "partition": msg.partition,
                            "offset": msg.offset,
                        },
                    )
                    # Record processing failure for health monitoring
                    await health_monitor.record_processing_failure()

            except Exception as e:
                logger.error(
                    "Unhandled exception in consumer loop",
                    exc_info=True,
                    extra={
                        "error": str(e),
                        "topic": msg.topic,
                        "partition": msg.partition,
                        "offset": msg.offset,
                    },
                )
                # Record processing failure for health monitoring
                await health_monitor.record_processing_failure()

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
        OutboxProvider(),
    )

    consumer = None
    event_relay_worker = None
    try:
        async with container() as request_container:
            # Get dependencies from DI container
            batch_coordination_handler = await request_container.get(BatchCoordinationHandler)
            batch_command_handler = await request_container.get(BatchCommandHandler)
            service_result_handler = await request_container.get(ServiceResultHandler)
            redis_client = await request_container.get(AtomicRedisClientProtocol)
            tracer = await request_container.get(Tracer)
            event_relay_worker = await request_container.get(EventRelayWorker)
            health_monitor = await request_container.get(KafkaConsumerHealthMonitor)
            recovery_manager = await request_container.get(ConsumerRecoveryManager)

            logger.info("Dependencies injected successfully")

            # Start event relay worker for outbox pattern
            await event_relay_worker.start()
            logger.info("Event relay worker started for outbox pattern")

            # Create and start Kafka consumer
            consumer = await create_kafka_consumer()

            # Run consumer loop
            await run_consumer_loop(
                consumer=consumer,
                batch_coordination_handler=batch_coordination_handler,
                batch_command_handler=batch_command_handler,
                service_result_handler=service_result_handler,
                redis_client=redis_client,
                health_monitor=health_monitor,
                recovery_manager=recovery_manager,
                tracer=tracer,
            )

    except KeyboardInterrupt:
        logger.info("Worker interrupted by user")
    except Exception as e:
        logger.error(f"Worker failed: {e}")
        sys.exit(1)
    finally:
        # Stop event relay worker first
        if event_relay_worker:
            try:
                await event_relay_worker.stop()
                logger.info("Event relay worker stopped")
            except Exception as e:
                logger.error(f"Error stopping event relay worker: {e}")

        if consumer:
            try:
                await consumer.stop()
                logger.info("Kafka consumer stopped")
            except Exception as e:
                logger.error(f"Error stopping Kafka consumer: {e}")

    logger.info("Essay Lifecycle Service Worker shutdown completed")


if __name__ == "__main__":
    asyncio.run(main())

"""Kafka consumer worker main for CJ Assessment Service.

This worker implements graceful shutdown handling:
- Responds to SIGTERM and SIGINT signals
- Allows in-flight messages to complete processing
- Stops accepting new messages immediately on shutdown
- Provides a configurable grace period before forceful termination
- Properly cleans up all resources (Kafka, database, monitoring)
"""

from __future__ import annotations

import asyncio
import signal
import sys
from typing import TYPE_CHECKING, Any, Set

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from opentelemetry.trace import Tracer

from aiokafka import AIOKafkaConsumer
from dishka import make_async_container
from huleedu_service_libs import init_tracing
from huleedu_service_libs.idempotency_v2 import IdempotencyConfig, idempotent_consumer
from huleedu_service_libs.logging_utils import configure_service_logging, create_service_logger
from huleedu_service_libs.protocols import RedisClientProtocol
from sqlalchemy.ext.asyncio import create_async_engine

from services.cj_assessment_service.batch_monitor import BatchMonitor
from services.cj_assessment_service.config import settings
from services.cj_assessment_service.di import CJAssessmentServiceProvider
from services.cj_assessment_service.event_processor import process_single_message
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

# Configure logging
configure_service_logging(settings.SERVICE_NAME, log_level=settings.LOG_LEVEL)
logger = create_service_logger("worker_main")

# Global shutdown flag
shutdown_event = asyncio.Event()


async def run_consumer(
    consumer: AIOKafkaConsumer,
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    event_publisher: CJEventPublisherProtocol,
    llm_interaction: LLMInteractionProtocol,
    redis_client: RedisClientProtocol,
    tracer: Tracer,
) -> None:
    """Run the Kafka consumer task."""
    logger.info("Starting Kafka consumer task")

    # Apply idempotency decorator to message processing with v2 configuration
    config = IdempotencyConfig(
        service_name="cj-assessment-service",
        default_ttl=86400,  # 24 hours for complex AI processing
        enable_debug_logging=True,  # Enable for AI workflow monitoring
    )

    @idempotent_consumer(redis_client=redis_client, config=config)
    async def handle_message_idempotently(
        msg: Any, *, confirm_idempotency: Callable[[], Awaitable[None]]
    ) -> bool:
        result = await process_single_message(
            msg=msg,
            database=database,
            content_client=content_client,
            event_publisher=event_publisher,
            llm_interaction=llm_interaction,
            settings_obj=settings,
            tracer=tracer,
        )
        await confirm_idempotency()  # Confirm after successful processing
        return result

    # Message consumption loop with idempotency support
    try:
        async for msg in consumer:
            if shutdown_event.is_set():
                logger.info("Consumer received shutdown signal, stopping...")
                break

            try:
                result = await handle_message_idempotently(msg)

                if result is not None:
                    # Only commit if not a skipped duplicate
                    if result:
                        await consumer.commit()
                        logger.debug(
                            "Message committed: %s:%s:%s",
                            msg.topic,
                            msg.partition,
                            msg.offset,
                        )
                    else:
                        logger.warning(
                            f"Message processing failed, not committing: "
                            f"{msg.topic}:{msg.partition}:{msg.offset}",
                        )
                else:
                    # Message was a duplicate and skipped
                    logger.info(
                        f"Duplicate message skipped, not committing offset: "
                        f"{msg.topic}:{msg.partition}:{msg.offset}",
                    )

            except Exception as e:
                logger.error(f"Error processing message: {e}", exc_info=True)

    except asyncio.CancelledError:
        logger.info("Consumer task cancelled")
        raise
    finally:
        await consumer.stop()
        logger.info("Kafka consumer stopped")


async def run_monitor(batch_monitor: BatchMonitor) -> None:
    """Run the batch monitoring task."""
    logger.info("Starting batch monitor task")

    try:
        # Create a task for the monitor loop so we can cancel it on shutdown
        monitor_future = asyncio.create_task(batch_monitor.check_stuck_batches())

        # Wait for either the monitor to complete or shutdown signal
        shutdown_task = asyncio.create_task(shutdown_event.wait())

        done: Set[asyncio.Task[Any]]
        done, _ = await asyncio.wait(
            [monitor_future, shutdown_task],
            return_when=asyncio.FIRST_COMPLETED,
        )

        # If shutdown was triggered, cancel the monitor
        if shutdown_task in done:
            logger.info("Monitor received shutdown signal")
            monitor_future.cancel()
            try:
                await monitor_future
            except asyncio.CancelledError:
                pass

    except asyncio.CancelledError:
        logger.info("Monitor task cancelled")
        raise
    except Exception as e:
        logger.error(
            "Batch monitor task failed", extra={"error": str(e), "error_type": type(e).__name__}
        )
        raise
    finally:
        await batch_monitor.stop()
        logger.info("Batch monitor stopped")


async def main() -> None:
    """Main entry point for CJ Assessment Service worker."""
    logger.info("CJ Assessment Service worker starting...")

    # Initialize tracing (this sets up the global tracer provider)
    tracer = init_tracing("cj_assessment_service")
    logger.info("OpenTelemetry tracing initialized")

    # Initialize database engine for DI container
    engine = create_async_engine(
        settings.database_url,
        echo=False,
        future=True,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
        pool_recycle=settings.DATABASE_POOL_RECYCLE,
    )

    # Initialize Dishka container with engine
    container = make_async_container(CJAssessmentServiceProvider(engine=engine))

    try:
        async with container() as request_container:
            # Initialize database schema
            database = await request_container.get(CJRepositoryProtocol)
            await database.initialize_db_schema()
            logger.info("Database schema initialized")

            # Set up Kafka consumer
            consumer = AIOKafkaConsumer(
                settings.CJ_ASSESSMENT_REQUEST_TOPIC,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                group_id=settings.CONSUMER_GROUP_ID_CJ,
                auto_offset_reset="latest",
                enable_auto_commit=False,
            )

            await consumer.start()
            logger.info(f"Kafka consumer started for topic: {settings.CJ_ASSESSMENT_REQUEST_TOPIC}")

            # Get dependencies from container
            content_client = await request_container.get(ContentClientProtocol)
            event_publisher = await request_container.get(CJEventPublisherProtocol)
            llm_interaction = await request_container.get(LLMInteractionProtocol)
            redis_client = await request_container.get(RedisClientProtocol)
            tracer = await request_container.get(Tracer)

            # Initialize batch monitor
            batch_monitor = BatchMonitor(
                repository=database,
                event_publisher=event_publisher,
                content_client=content_client,
                settings=settings,
            )
            logger.info("Batch monitor initialized")

            logger.info(
                "CJ Assessment Service worker ready with idempotency and monitoring support"
            )

            # Create tasks for consumer and monitor
            consumer_task = asyncio.create_task(
                run_consumer(
                    consumer=consumer,
                    database=database,
                    content_client=content_client,
                    event_publisher=event_publisher,
                    llm_interaction=llm_interaction,
                    redis_client=redis_client,
                    tracer=tracer,
                ),
                name="consumer_task",
            )

            monitor_task = asyncio.create_task(run_monitor(batch_monitor), name="monitor_task")

            # Run both tasks concurrently
            tasks = [consumer_task, monitor_task]
            logger.info("Running consumer and monitor tasks concurrently")

            # Create shutdown monitoring task
            shutdown_task = asyncio.create_task(shutdown_event.wait(), name="shutdown_task")
            all_tasks = tasks + [shutdown_task]

            try:
                # Wait for shutdown signal or task failure
                done: Set[asyncio.Task[Any]]
                pending: Set[asyncio.Task[Any]]
                done, pending = await asyncio.wait(all_tasks, return_when=asyncio.FIRST_COMPLETED)

                # Check what completed first
                if shutdown_task in done:
                    logger.info("Shutdown signal received, initiating graceful shutdown...")

                    # Signal tasks to stop
                    shutdown_event.set()

                    # Give tasks a grace period to finish
                    grace_period = getattr(settings, "SHUTDOWN_GRACE_PERIOD_SECONDS", 30)
                    logger.info(f"Allowing {grace_period} seconds for graceful shutdown...")

                    try:
                        await asyncio.wait_for(
                            asyncio.gather(
                                *[t for t in tasks if not t.done()], return_exceptions=True
                            ),
                            timeout=grace_period,
                        )
                        logger.info("All tasks completed gracefully")
                    except asyncio.TimeoutError:
                        logger.warning("Grace period expired, forcing shutdown...")
                        # Cancel remaining tasks
                        for task in tasks:
                            if not task.done():
                                task.cancel()
                        await asyncio.gather(*tasks, return_exceptions=True)
                else:
                    # A task failed
                    for task in done:
                        if task != shutdown_task and task.exception():
                            logger.error(
                                f"Task {task.get_name()} failed with exception",
                                exc_info=task.exception(),
                            )

                    # Signal shutdown
                    shutdown_event.set()

                    # Cancel remaining tasks
                    logger.info("Cancelling remaining tasks due to failure...")
                    for task in pending:
                        if task != shutdown_task:
                            task.cancel()

                    # Wait for cancellation to complete
                    await asyncio.gather(
                        *[t for t in pending if t != shutdown_task], return_exceptions=True
                    )

            except Exception as e:
                logger.error(f"Error in main task coordination: {e}", exc_info=True)
                # Signal shutdown
                shutdown_event.set()
                # Cancel all tasks
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

    except Exception as e:
        logger.error(f"Worker initialization failed: {e}", exc_info=True)
        raise
    finally:
        # Clean up resources
        logger.info("Cleaning up resources...")

        # Close the container
        await container.close()

        # Dispose of the database engine
        await engine.dispose()
        logger.info("Database connections closed")

        logger.info("CJ Assessment Service worker shutdown complete")


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals."""
    _ = frame  # Unused but required by signal handler signature
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_event.set()


if __name__ == "__main__":
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"CJ Assessment Service worker failed: {e}", exc_info=True)
        sys.exit(1)

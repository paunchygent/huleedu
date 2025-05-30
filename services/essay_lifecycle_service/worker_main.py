"""
Main entry point for the Essay Lifecycle Service Kafka worker.

This module handles the Kafka consumer lifecycle, dependency injection setup,
and message processing orchestration.
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

from batch_command_handlers import process_single_message
from config import settings
from di import EssayLifecycleServiceProvider
from protocols import (
    BatchEssayTracker,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    StateTransitionValidator,
)

logger = create_service_logger("worker_main")


class WorkerState:
    """Holds worker state for graceful shutdown."""

    def __init__(self) -> None:
        self.should_stop = False
        self.consumer: AIOKafkaConsumer | None = None


worker_state = WorkerState()


def setup_signal_handlers() -> None:
    """Setup signal handlers for graceful shutdown."""

    def signal_handler(signum: int, frame: object) -> None:
        logger.info(f"Received signal {signum}, initiating graceful shutdown")
        worker_state.should_stop = True

        # Stop the consumer if it's running
        if worker_state.consumer:
            asyncio.create_task(worker_state.consumer.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


@asynccontextmanager
async def kafka_consumer_context() -> AsyncIterator[AIOKafkaConsumer]:
    """Context manager for Kafka consumer lifecycle."""
    # Define topics using topic_name() function for consistency
    topics = [
        topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED),
        topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
        topic_name(ProcessingEvent.ESSAY_CONTENT_READY),
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
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
    batch_essay_tracker: BatchEssayTracker,
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
                    state_store=state_store,
                    event_publisher=event_publisher,
                    transition_validator=transition_validator,
                    metrics_collector=metrics_collector,
                    batch_tracker=batch_essay_tracker,
                )

                if success:
                    metrics_collector.increment_counter(
                        "operations", {"operation": "message_processed", "status": "success"}
                    )
                else:
                    metrics_collector.increment_counter(
                        "operations", {"operation": "message_processed", "status": "failed"}
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
                metrics_collector.increment_counter(
                    "operations", {"operation": "message_processed", "status": "error"}
                )

    except Exception as e:
        logger.error(f"Error in message processing loop: {e}")
        raise


async def run_worker() -> None:
    """Main worker function with dependency injection."""
    logger.info("Starting Essay Lifecycle Service worker")

    # Setup DI container
    container = make_async_container(EssayLifecycleServiceProvider())

    try:
        async with container() as request_container:
            # Get dependencies
            state_store = await request_container.get(EssayStateStore)
            event_publisher = await request_container.get(EventPublisher)
            transition_validator = await request_container.get(StateTransitionValidator)
            metrics_collector = await request_container.get(MetricsCollector)
            batch_essay_tracker = await request_container.get(BatchEssayTracker)

            logger.info("Dependencies injected successfully")

            # Start Kafka consumer and process messages
            async with kafka_consumer_context() as consumer:
                await process_messages(
                    consumer=consumer,
                    state_store=state_store,
                    event_publisher=event_publisher,
                    transition_validator=transition_validator,
                    metrics_collector=metrics_collector,
                    batch_essay_tracker=batch_essay_tracker,
                )

    except Exception as e:
        logger.error(f"Error in worker: {e}")
        raise
    finally:
        logger.info("Essay Lifecycle Service worker stopped")


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

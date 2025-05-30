from __future__ import annotations

import asyncio
import signal
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator  # Changed from Any to AsyncIterator for kafka_clients

import aiohttp
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from aiokafka.errors import KafkaConnectionError
from config import settings  # Assuming this is still the way to get settings
from di import SpellCheckerServiceProvider
from dishka import make_async_container
from event_router import (
    # Placeholder config values used in event_router, ideally pass them from here
    CONTENT_SERVICE_URL_CONFIG,
    KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED,
    KAFKA_OUTPUT_TOPIC_CONFIG,
    SOURCE_SERVICE_NAME_CONFIG,
    DefaultContentClient,
    DefaultResultStore,
    DefaultSpellcheckEventPublisher,
    process_single_message,
)
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
)
from prometheus_client import CollectorRegistry, Histogram, start_http_server

from common_core.enums import ProcessingEvent, topic_name

# Configure structured logging for the service (moved from original worker.py)
configure_service_logging(
    service_name="spell-checker-service",
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
)
logger = create_service_logger("spell_checker_service.worker_main")

# Configuration constants from settings
KAFKA_BOOTSTRAP_SERVERS = settings.KAFKA_BOOTSTRAP_SERVERS
CONSUMER_GROUP_ID = settings.CONSUMER_GROUP
PRODUCER_CLIENT_ID = settings.PRODUCER_CLIENT_ID
CONSUMER_CLIENT_ID = settings.CONSUMER_CLIENT_ID
METRICS_PORT = settings.METRICS_PORT  # Now properly configured in Settings class

INPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
# OUTPUT_TOPIC is KAFKA_OUTPUT_TOPIC_CONFIG from event_router which is
# topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)

# Prometheus metrics (will be initialized with DI registry)
KAFKA_QUEUE_LATENCY: Histogram | None = None


@asynccontextmanager
async def kafka_clients(
    input_topic: str,
    consumer_group_id: str,
    producer_client_id: str,  # Renamed for clarity
    consumer_client_id: str,  # Renamed for clarity
    bootstrap_servers: str,
    kafka_event_type_spellcheck_completed: str,  # Added
    source_service_name: str,  # Added
    kafka_output_topic: str,  # Added
) -> AsyncIterator[tuple[AIOKafkaConsumer, AIOKafkaProducer, DefaultSpellcheckEventPublisher]]:
    """Context manager for Kafka clients.

    Returns a tuple of (consumer, producer, event_publisher) and handles proper lifecycle.
    """
    consumer = AIOKafkaConsumer(
        input_topic,
        bootstrap_servers=bootstrap_servers,
        group_id=consumer_group_id,
        client_id=consumer_client_id,
        enable_auto_commit=False,
        auto_offset_reset="earliest",
        max_poll_records=settings.KAFKA_MAX_POLL_RECORDS,  # from settings
        max_poll_interval_ms=settings.KAFKA_MAX_POLL_INTERVAL_MS,  # from settings
        session_timeout_ms=settings.KAFKA_SESSION_TIMEOUT_MS,  # from settings
        heartbeat_interval_ms=settings.KAFKA_HEARTBEAT_INTERVAL_MS,  # from settings
    )
    producer = AIOKafkaProducer(bootstrap_servers=bootstrap_servers, client_id=producer_client_id)

    # Instantiate the event publisher here as it depends on config-like values
    event_publisher = DefaultSpellcheckEventPublisher(
        kafka_event_type=kafka_event_type_spellcheck_completed,
        source_service_name=source_service_name,
        kafka_output_topic=kafka_output_topic,
    )

    await consumer.start()
    await producer.start()
    logger.info(
        f"Kafka consumer and producer started. Consumer group: {consumer_group_id}, "
        f"Input topic: {input_topic}"
    )
    try:
        yield consumer, producer, event_publisher
    finally:
        logger.info("Stopping Kafka consumer and producer...")
        await consumer.stop()
        await producer.stop()
        logger.info("Kafka consumer and producer stopped.")


async def _start_metrics_server(registry: CollectorRegistry, port: int) -> None:
    """Start the Prometheus metrics HTTP server in a background thread."""
    global KAFKA_QUEUE_LATENCY

    # Initialize queue latency metric
    KAFKA_QUEUE_LATENCY = Histogram(
        'kafka_message_queue_latency_seconds',
        'Latency between event timestamp and processing start',
        ['topic', 'consumer_group'],
        registry=registry
    )

    # Start metrics server in a thread
    def _start_server() -> None:
        start_http_server(port, registry=registry)

    await asyncio.to_thread(_start_server)
    logger.info(f"Prometheus metrics server started on port {port}")


async def spell_checker_worker_main() -> None:
    # Initialize DI container and metrics server
    container = make_async_container(SpellCheckerServiceProvider())

    # Start metrics server
    async with container() as request_container:
        registry = await request_container.get(CollectorRegistry)
        # Start metrics server in background
        asyncio.create_task(_start_metrics_server(registry, METRICS_PORT))

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def _signal_handler(*_: Any) -> None:
        logger.info("Termination signal received. Initiating graceful shutdown...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    # Instantiate content client and result store (these are stateless or configured once)
    # Their config (CONTENT_SERVICE_URL_CONFIG) comes from event_router for now, pass it.
    content_client = DefaultContentClient(content_service_url=CONTENT_SERVICE_URL_CONFIG)
    result_store = DefaultResultStore(content_service_url=CONTENT_SERVICE_URL_CONFIG)

    # Note: DefaultSpellLogic is instantiated per message in event_router.process_single_message
    # because it needs message-specific context (original_text_storage_id, essay_id,
    # initial_system_metadata)

    retry_count = 0
    max_retries = 3

    while not stop_event.is_set():
        try:
            async with kafka_clients(
                INPUT_TOPIC,
                CONSUMER_GROUP_ID,
                PRODUCER_CLIENT_ID,
                CONSUMER_CLIENT_ID,
                KAFKA_BOOTSTRAP_SERVERS,
                KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED,  # from event_router
                SOURCE_SERVICE_NAME_CONFIG,  # from event_router
                KAFKA_OUTPUT_TOPIC_CONFIG,  # from event_router
            ) as (consumer, producer, event_publisher_instance):
                retry_count = 0  # Reset retries on successful connection
                logger.info("Kafka clients initialized. Starting message consumption loop...")
                async with (
                    aiohttp.ClientSession() as http_session
                ):  # Manage ClientSession lifecycle
                    while not stop_event.is_set():
                        try:
                            # Process in batches
                            result = await consumer.getmany(timeout_ms=1000, max_records=10)
                            if not result:
                                await asyncio.sleep(0.1)  # Short sleep if no messages
                                continue

                            for tp, messages in result.items():
                                logger.debug(
                                    f"Received {len(messages)} messages from {tp.topic} "
                                    f"partition {tp.partition}"
                                )
                                for msg_count, msg in enumerate(messages):
                                    if stop_event.is_set():
                                        break
                                    logger.info(
                                        f"Processing message {msg_count + 1}/{len(messages)} "
                                        f"from {tp}"
                                    )

                                    # process_single_message now takes fewer direct DI components
                                    # as DefaultSpellLogic is created inside it with more
                                    # specific context
                                    should_commit = await process_single_message(
                                        msg,
                                        producer,
                                        http_session,
                                        content_client,  # Instantiated once
                                        result_store,  # Instantiated once
                                        # Instantiated by kafka_clients context mgr
                                        event_publisher_instance,
                                        consumer_group_id=CONSUMER_GROUP_ID,
                                        kafka_queue_latency_metric=KAFKA_QUEUE_LATENCY,
                                    )
                                    if should_commit:
                                        # Store offset for this specific message
                                        # Create a TopicPartition instance for the current message
                                        tp_instance = TopicPartition(msg.topic, msg.partition)
                                        offsets = {tp_instance: msg.offset + 1}
                                        await consumer.commit(offsets)
                                        logger.debug(
                                            f"Committed offset {msg.offset + 1} for {tp_instance}"
                                        )
                                if stop_event.is_set():
                                    break
                        except KafkaConnectionError as kce:
                            logger.error(
                                f"Kafka connection error during consumption: {kce}", exc_info=True
                            )
                            stop_event.set()  # Stop on critical Kafka error
                        except Exception as e:
                            logger.error(f"Error in main consumption loop: {e}", exc_info=True)
                            await asyncio.sleep(5)  # Wait before retrying the loop section
        except KafkaConnectionError as kce_outer:
            retry_count += 1
            logger.error(
                f"Kafka connection error setting up clients "
                f"(attempt {retry_count}/{max_retries}): {kce_outer}",
                exc_info=True,
            )
            if retry_count >= max_retries or stop_event.is_set():
                logger.error("Max retries reached or shutdown signaled. Exiting worker.")
                break
            await asyncio.sleep(2**retry_count)  # Exponential backoff
        except Exception as e_outer:
            logger.critical(
                f"Unhandled critical error in spell_checker_worker_main: {e_outer}", exc_info=True
            )
            stop_event.set()  # Critical error, stop the worker
            break  # Exit while loop

    logger.info("Spell checker worker main loop has finished.")


if __name__ == "__main__":
    try:
        asyncio.run(spell_checker_worker_main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Exiting.")
    except Exception as e:
        logger.critical(f"Critical error starting worker: {e}", exc_info=True)

"""
HuleEdu Spell Checker Service Worker.

This module implements the core spell checking worker that consumes spell check
requests from Kafka, processes them using dependency injection for testability,
and publishes results back to Kafka. The worker includes proper error handling,
resource management, and observability features.
"""

import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional, Tuple
from uuid import uuid4

import aiohttp
from aiohttp import ClientTimeout
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, ConsumerRecord, TopicPartition
from aiokafka.errors import KafkaConnectionError
from config import settings
from huleedu_service_libs.logging_utils import (
    configure_service_logging,
    create_service_logger,
    log_event_processing,
)
from pydantic import ValidationError

from common_core.enums import (
    ContentType,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
    topic_name,
)

# Make sure common_core is in PYTHONPATH or installed (PDM editable handles this)
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckRequestedDataV1,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)

# Configure structured logging for the service
configure_service_logging(
    service_name="spell-checker-service",
    environment=settings.ENVIRONMENT,
    log_level=settings.LOG_LEVEL,
)

# Create service loggers
logger = create_service_logger("worker")

# Configuration constants
KAFKA_BOOTSTRAP_SERVERS = settings.KAFKA_BOOTSTRAP_SERVERS
CONTENT_SERVICE_URL = settings.CONTENT_SERVICE_URL
CONSUMER_GROUP_ID = settings.CONSUMER_GROUP
PRODUCER_CLIENT_ID = settings.PRODUCER_CLIENT_ID
CONSUMER_CLIENT_ID = settings.CONSUMER_CLIENT_ID
INPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
OUTPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)
SOURCE_SERVICE_NAME = "spell-checker-service"

# Type aliases for dependency injection
FetchContentFunc = Callable[[aiohttp.ClientSession, str, str], Awaitable[Optional[str]]]
StoreContentFunc = Callable[[aiohttp.ClientSession, str, str], Awaitable[Optional[str]]]
PerformSpellCheckFunc = Callable[[str, str], Awaitable[Tuple[str, int]]]


async def default_perform_spell_check(text: str, essay_id: str) -> Tuple[str, int]:
    """
    Default spell check implementation (placeholder).

    This is a simple placeholder implementation that can be replaced
    with actual spell checking logic in production.

    Args:
        text: The text to spell check
        essay_id: The essay ID for logging purposes

    Returns:
        Tuple of (corrected_text, corrections_count)
    """
    logger.info(f"Performing DUMMY spell check for essay {essay_id} (text length: {len(text)})")
    await asyncio.sleep(0.1)  # Simulate work

    # Simple dummy corrections - replace with actual spell check logic
    corrected_text = text.replace("teh", "the").replace("recieve", "receive")
    corrections_count = text.count("teh") + text.count("recieve")

    logger.info(f"Dummy spell check for {essay_id} made {corrections_count} corrections.")
    return corrected_text, corrections_count


async def default_fetch_content(
    session: aiohttp.ClientSession, storage_id: str, essay_id: str
) -> Optional[str]:
    """
    Default implementation for fetching content from the content service.

    Args:
        session: HTTP session for making requests
        storage_id: Storage ID to fetch content for
        essay_id: Essay ID for logging purposes

    Returns:
        Content text if successful, None if failed
    """
    url = f"{CONTENT_SERVICE_URL}/{storage_id}"
    logger.debug(f"Essay {essay_id}: Fetching content from URL: {url}")
    try:
        timeout = ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            content = await response.text()
            logger.debug(
                f"Essay {essay_id}: Fetched content from {storage_id} "
                f"(first 100 chars: {content[:100]})"
            )
            return content
    except Exception as e:
        logger.error(
            f"Essay {essay_id}: Error fetching content {storage_id} from {url}: {e}",
            exc_info=True,
        )
    return None


async def default_store_content(
    session: aiohttp.ClientSession, text_content: str, essay_id: str
) -> Optional[str]:
    """
    Default implementation for storing content to the content service.

    Args:
        session: HTTP session for making requests
        text_content: Content to store
        essay_id: Essay ID for logging purposes

    Returns:
        Storage ID if successful, None if failed
    """
    logger.debug(
        f"Essay {essay_id}: Storing content (length: {len(text_content)}) to Content Service"
    )
    try:
        timeout = ClientTimeout(total=10)
        async with session.post(
            CONTENT_SERVICE_URL, data=text_content.encode("utf-8"), timeout=timeout
        ) as response:
            response.raise_for_status()
            data: dict[str, str] = await response.json()
            storage_id = data.get("storage_id")
            logger.info(f"Essay {essay_id}: Stored corrected text, new_storage_id: {storage_id}")
            return storage_id
    except Exception as e:
        logger.error(f"Essay {essay_id}: Error storing content: {e}", exc_info=True)
    return None


async def process_single_message(
    msg: ConsumerRecord,
    producer: AIOKafkaProducer,
    http_session: aiohttp.ClientSession,
    fetch_content_func: FetchContentFunc,
    store_content_func: StoreContentFunc,
    perform_spell_check_func: PerformSpellCheckFunc,
) -> bool:
    """
    Process a single Kafka message for spell checking.

    This function is the core processing logic that can be easily tested
    with dependency injection.

    Args:
        msg: Kafka message to process
        producer: Kafka producer for publishing results
        http_session: HTTP session for content operations
        fetch_content_func: Function to fetch content
        store_content_func: Function to store content
        perform_spell_check_func: Function to perform spell checking

    Returns:
        True if message should be committed, False otherwise
    """
    logger.info(
        f"Processing msg from '{msg.topic}' p{msg.partition} o{msg.offset} "
        f"key='{msg.key.decode() if msg.key else None}'"
    )
    processing_started_at = datetime.now(timezone.utc)

    try:
        envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate(
            json.loads(msg.value.decode("utf-8"))
        )
        request_data: SpellcheckRequestedDataV1 = envelope.data
        essay_id = request_data.entity_ref.entity_id
        original_text_storage_id = request_data.text_storage_id

        # Log event processing with full context
        log_event_processing(
            logger,
            "Processing spellcheck request",
            envelope,
            essay_id=essay_id,
            original_storage_id=original_text_storage_id,
            processing_stage="started",
        )

        # Fetch original text
        original_text = await fetch_content_func(http_session, original_text_storage_id, essay_id)
        if original_text is None:
            logger.error(f"Essay {essay_id}: Could not fetch original text. Skipping.")
            return True  # Commit to avoid reprocessing

        # Perform spell check
        corrected_text, corrections_count = await perform_spell_check_func(original_text, essay_id)

        # Store corrected text
        corrected_text_storage_id = await store_content_func(http_session, corrected_text, essay_id)
        if corrected_text_storage_id is None:
            logger.error(
                f"Essay {essay_id}: Could not store corrected text. Skipping result event."
            )
            return True  # Commit to avoid reprocessing

        # Build storage metadata
        storage_meta = StorageReferenceMetadata()
        storage_meta.add_reference(ContentType.ORIGINAL_ESSAY, original_text_storage_id)
        storage_meta.add_reference(ContentType.CORRECTED_TEXT, corrected_text_storage_id)

        # Build result metadata
        result_system_meta = SystemProcessingMetadata(
            entity=request_data.entity_ref,
            timestamp=datetime.now(timezone.utc),
            processing_stage=ProcessingStage.COMPLETED,
            event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            started_at=processing_started_at,
        )

        # Build result payload
        result_payload = SpellcheckResultDataV1(
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            entity_ref=request_data.entity_ref,
            status=EssayStatus.SPELLCHECKED_SUCCESS,
            system_metadata=result_system_meta,
            original_text_storage_id=original_text_storage_id,
            storage_metadata=storage_meta,
            corrections_made=corrections_count,
        )

        # Build result envelope
        result_envelope = EventEnvelope[SpellcheckResultDataV1](
            event_id=uuid4(),
            event_type=OUTPUT_TOPIC,
            source_service=SOURCE_SERVICE_NAME,
            correlation_id=envelope.correlation_id,
            data=result_payload,
        )

        # Publish result
        await producer.send_and_wait(
            OUTPUT_TOPIC,
            json.dumps(result_envelope.model_dump(mode="json")).encode("utf-8"),
            key=essay_id.encode("utf-8"),
        )

        logger.info(
            f"Essay {essay_id}: Published spellcheck result. Event ID: {result_envelope.event_id}"
        )
        return True

    except ValidationError as ve:
        logger.error(
            f"Pydantic validation error for msg at offset {msg.offset}: "
            f"{ve.errors(include_url=False)}",
            exc_info=False,
        )
        return True  # Commit invalid message to avoid reprocessing
    except Exception as e:
        logger.error(
            f"Unhandled error processing msg at offset {msg.offset}: {e}",
            exc_info=True,
        )
        return True  # Commit on error to avoid reprocessing


@asynccontextmanager
async def kafka_clients(
    input_topic: str,
    consumer_group_id: str,
    client_id_prefix: str,
    bootstrap_servers: str,
) -> Any:
    """
    Async context manager for Kafka client lifecycle management.

    This ensures proper startup and cleanup of Kafka clients,
    making the code more robust and testable.

    Args:
        input_topic: Topic to consume from
        consumer_group_id: Consumer group ID
        client_id_prefix: Prefix for client IDs
        bootstrap_servers: Kafka bootstrap servers

    Yields:
        Tuple of (consumer, producer)
    """
    consumer = AIOKafkaConsumer(
        input_topic,
        bootstrap_servers=bootstrap_servers,
        group_id=consumer_group_id,
        client_id=f"{client_id_prefix}-consumer",
        value_deserializer=None,  # Deserialize manually in process_single_message
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        client_id=f"{client_id_prefix}-producer",
        value_serializer=None,  # Serialize manually before sending
        acks="all",
        enable_idempotence=True,
    )

    try:
        logger.info(f"Starting Kafka consumer for group {consumer_group_id} and producer...")
        await consumer.start()
        await producer.start()
        logger.info("Kafka clients started.")
        yield consumer, producer
    except KafkaConnectionError as kce:
        logger.critical(f"Failed to connect Kafka clients: {kce}", exc_info=True)
        raise  # Reraise to prevent app from running in a broken state
    finally:
        logger.info("Stopping Kafka clients...")
        # Check if clients are actually running before stopping
        if hasattr(producer, "_sender") and producer._sender and producer._sender._running:
            await producer.stop()
        if hasattr(consumer, "_running") and consumer._running:
            await consumer.stop()
        logger.info("Kafka clients stopped.")


async def spell_checker_worker_main() -> None:
    """
    Main worker function for the spell checker service.

    This function orchestrates the entire spell checking workflow
    using dependency injection and proper resource management.
    """
    try:
        async with kafka_clients(
            INPUT_TOPIC, CONSUMER_GROUP_ID, PRODUCER_CLIENT_ID, KAFKA_BOOTSTRAP_SERVERS
        ) as (consumer, producer):
            async with aiohttp.ClientSession() as http_session:
                logger.info(
                    f"Spell Checker Worker started. Consuming from '{INPUT_TOPIC}', "
                    f"group '{CONSUMER_GROUP_ID}'."
                )

                async for msg in consumer:
                    tp = TopicPartition(msg.topic, msg.partition)
                    offset_to_commit = msg.offset + 1

                    # Process message with injected dependencies
                    should_commit = await process_single_message(
                        msg,
                        producer,
                        http_session,
                        default_fetch_content,
                        default_store_content,
                        default_perform_spell_check,
                    )

                    if should_commit:
                        await consumer.commit({tp: offset_to_commit})
                        logger.debug(f"Committed offset {offset_to_commit} for {tp}")

    except KafkaConnectionError:
        logger.critical(
            "Exiting spell_checker_worker_main due to Kafka connection issues during startup."
        )
    except asyncio.CancelledError:
        logger.info("Spell Checker Worker main task was cancelled.")
    except Exception as e:
        logger.critical(f"Spell Checker Worker critical error in main loop: {e}", exc_info=True)
    finally:
        logger.info("Spell Checker Worker main function finished.")


if __name__ == "__main__":
    try:
        asyncio.run(spell_checker_worker_main())
    except KeyboardInterrupt:
        logger.info("Spell Checker Worker interrupted by user.")

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional  # Added Any
from uuid import uuid4

import aiohttp
from aiohttp import ClientTimeout
from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from dotenv import load_dotenv
from pydantic import ValidationError

load_dotenv()

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

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
CONTENT_SERVICE_URL = os.getenv("CONTENT_SERVICE_URL", "http://content_service:8000/v1/content")
CONSUMER_GROUP_ID = os.getenv("SPELLCHECKER_CONSUMER_GROUP", "spellchecker-service-group-v1.1")
PRODUCER_CLIENT_ID = "spellchecker-service-producer"
CONSUMER_CLIENT_ID = "spellchecker-service-consumer"
# Topic names using centralized helper function
INPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
OUTPUT_TOPIC = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED)
SOURCE_SERVICE_NAME = "spell-checker-service"


async def perform_spell_check(text: str, essay_id: str) -> tuple[str, int]:
    logger.info(f"Performing DUMMY spell check for essay {essay_id} (text length: {len(text)})")
    await asyncio.sleep(0.1)  # Simulate work
    # This is a placeholder. Replace with your actual spell check logic.
    # Example: from your_spellchecker_lib import check_text
    # corrected_text, corrections_count = await check_text(text)
    corrected_text = text.replace("teh", "the").replace("recieve", "receive")  # Simple dummy
    corrections_count = text.count("teh") + text.count("recieve")
    logger.info(f"Dummy spell check for {essay_id} made {corrections_count} corrections.")
    return corrected_text, corrections_count


async def fetch_content_from_service(
    session: aiohttp.ClientSession, storage_id: str, essay_id: str
) -> Optional[str]:
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


async def store_content_to_service(
    session: aiohttp.ClientSession, text_content: str, essay_id: str
) -> Optional[str]:
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


async def spell_checker_worker_main() -> None:
    consumer = AIOKafkaConsumer(
        INPUT_TOPIC,  # Subscribes to the specific topic name string
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        group_id=CONSUMER_GROUP_ID,
        client_id=CONSUMER_CLIENT_ID,
        value_deserializer=lambda b: json.loads(b.decode("utf-8")),
        auto_offset_reset="earliest",
        enable_auto_commit=False,  # Manual commit control
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        client_id=PRODUCER_CLIENT_ID,
        value_serializer=lambda d: json.dumps(d).encode("utf-8"),
        acks="all",
        enable_idempotence=True,
    )

    # Track running state locally instead of using private attributes
    consumer_running = False
    producer_running = False

    logger.info(
        f"Spell Checker Worker starting. Kafka: {KAFKA_BOOTSTRAP_SERVERS}, "
        f"Content Service: {CONTENT_SERVICE_URL}"
    )
    await consumer.start()
    consumer_running = True
    await producer.start()
    producer_running = True
    logger.info(
        f"Spell Checker Worker started. Consuming from '{INPUT_TOPIC}', "
        f"group '{CONSUMER_GROUP_ID}'."
    )

    try:
        async with aiohttp.ClientSession() as http_session:
            async for msg in consumer:
                tp = TopicPartition(msg.topic, msg.partition)
                offset_to_commit = msg.offset + 1
                logger.info(
                    f"Received msg from '{msg.topic}' p{msg.partition} o{msg.offset} "
                    f"key='{msg.key}'"
                )

                # Capture when processing actually starts
                processing_started_at = datetime.now(timezone.utc)

                try:
                    envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate(msg.value)
                    request_data: SpellcheckRequestedDataV1 = envelope.data
                    essay_id = request_data.entity_ref.entity_id
                    original_text_storage_id = request_data.text_storage_id

                    logger.info(
                        f"Processing spellcheck for essay_id: {essay_id}, "
                        f"original_storage_id: {original_text_storage_id}"
                    )

                    original_text = await fetch_content_from_service(
                        http_session, original_text_storage_id, essay_id
                    )
                    if original_text is None:
                        logger.error(f"Essay {essay_id}: Could not fetch original text. Skipping.")
                        await consumer.commit({tp: offset_to_commit})
                        continue

                    corrected_text, corrections_count = await perform_spell_check(
                        original_text, essay_id
                    )

                    corrected_text_storage_id = await store_content_to_service(
                        http_session, corrected_text, essay_id
                    )
                    if corrected_text_storage_id is None:
                        logger.error(
                            f"Essay {essay_id}: Could not store corrected text. "
                            f"Skipping result event."
                        )
                        await consumer.commit({tp: offset_to_commit})
                        continue

                    storage_meta = StorageReferenceMetadata()
                    storage_meta.add_reference(ContentType.ORIGINAL_ESSAY, original_text_storage_id)
                    storage_meta.add_reference(
                        ContentType.CORRECTED_TEXT, corrected_text_storage_id
                    )

                    # system_metadata for the result event with actual processing start time
                    result_system_meta = SystemProcessingMetadata(
                        entity=request_data.entity_ref,  # Same entity
                        timestamp=datetime.now(timezone.utc),
                        processing_stage=ProcessingStage.COMPLETED,
                        event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                        started_at=processing_started_at,  # Use actual processing start time
                    )

                    result_payload = SpellcheckResultDataV1(
                        event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                        entity_ref=request_data.entity_ref,
                        status=EssayStatus.SPELLCHECKED_SUCCESS,
                        system_metadata=result_system_meta,
                        original_text_storage_id=original_text_storage_id,
                        storage_metadata=storage_meta,
                        corrections_made=corrections_count,
                    )

                    result_envelope = EventEnvelope[SpellcheckResultDataV1](
                        event_id=uuid4(),  # New event ID for this result
                        event_type=OUTPUT_TOPIC,  # Use the string name of the topic
                        source_service=SOURCE_SERVICE_NAME,
                        correlation_id=envelope.correlation_id,  # Propagate
                        data=result_payload,
                    )

                    await producer.send_and_wait(
                        OUTPUT_TOPIC,
                        json.dumps(result_envelope.model_dump(mode="json")).encode("utf-8"),
                        key=essay_id.encode("utf-8"),
                    )
                    logger.info(
                        f"Essay {essay_id}: Published spellcheck result. "
                        f"Event ID: {result_envelope.event_id}"
                    )
                    await consumer.commit({tp: offset_to_commit})

                except ValidationError as ve:
                    logger.error(
                        f"Pydantic validation error for msg at offset {msg.offset}: "
                        f"{ve.errors(include_url=False)}",
                        exc_info=False,
                    )  # Less verbose
                    await consumer.commit({tp: offset_to_commit})
                except Exception as e:
                    logger.error(
                        f"Unhandled error processing msg at offset {msg.offset}: {e}",
                        exc_info=True,
                    )
                    await consumer.commit({tp: offset_to_commit})
    except asyncio.CancelledError:
        logger.info("Spell Checker Worker task was cancelled.")
    except Exception as e:  # Catch broader exceptions for consumer setup/loop
        logger.critical(f"Spell Checker Worker critical error: {e}", exc_info=True)
    finally:
        logger.info("Spell Checker Worker shutting down Kafka connections...")
        if consumer_running:
            await consumer.stop()
            consumer_running = False
        if producer_running:
            await producer.stop()
            producer_running = False
        logger.info("Spell Checker Worker finished.")


if __name__ == "__main__":
    try:
        asyncio.run(spell_checker_worker_main())
    except KeyboardInterrupt:
        logger.info("Spell Checker Worker interrupted by user.")

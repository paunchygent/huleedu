from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiohttp
from aiokafka import AIOKafkaProducer, ConsumerRecord
from core_logic import (
    default_fetch_content_impl,
    default_perform_spell_check_algorithm,
    default_store_content_impl,
)
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)
from pydantic import ValidationError

from common_core.enums import (
    ContentType,
    EssayStatus,
    ProcessingEvent,
    ProcessingStage,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckRequestedDataV1,
    SpellcheckResultDataV1,
)
from common_core.metadata_models import (
    EntityReference,
    StorageReferenceMetadata,
    SystemProcessingMetadata,
)

# Configuration constants (placeholders, should come from settings/DI)
CONTENT_SERVICE_URL_CONFIG = "http://localhost:8000/content"
# This is the Kafka topic
KAFKA_OUTPUT_TOPIC_CONFIG = "huleedu.essay.spellcheck.completed.v1"
# This is the event_type string for the envelope
KAFKA_EVENT_TYPE_SPELLCHECK_COMPLETED = "huleedu.spellchecker.essay.concluded.v1"
SOURCE_SERVICE_NAME_CONFIG = "spell-checker-service"

logger = create_service_logger("spell_checker_service.event_router")


# --- Protocol Implementations ---


class DefaultContentClient(ContentClientProtocol):
    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def fetch_content(self, storage_id: str, http_session: aiohttp.ClientSession) -> str:
        # The essay_id for default_fetch_content_impl's logging can be passed by the caller
        # if that level of detail in logging is required from the core_logic function.
        # For strict protocol adherence, this method only takes what the protocol defines.
        # We assume process_single_message will have essay_id and pass it
        # to default_fetch_content_impl if desired.
        # Here, we call it without essay_id if the protocol doesn't provide it.
        result = await default_fetch_content_impl(http_session, storage_id, self.content_service_url)
        return str(result)


class DefaultResultStore(ResultStoreProtocol):
    def __init__(self, content_service_url: str):
        self.content_service_url = content_service_url

    async def store_content(
        self,
        original_storage_id: str,
        content_type: ContentType,
        content: str,
        http_session: aiohttp.ClientSession,
    ) -> str:
        # essay_id for default_store_content_impl logging can be passed by caller if needed.
        # original_storage_id and content_type are part of protocol but not used by current impl.
        result = await default_store_content_impl(http_session, content, self.content_service_url)
        return str(result)


class DefaultSpellLogic(SpellLogicProtocol):
    # This class needs access to original_text_storage_id, http_session, and essay_id.
    # These will be provided when an instance is created for a specific message.
    def __init__(
        self,
        result_store: ResultStoreProtocol,
        original_text_storage_id: str,
        http_session: aiohttp.ClientSession,  # To use the result_store
        essay_id: str,  # essay_id is crucial for building the EntityReference
        initial_system_metadata: SystemProcessingMetadata,  # To carry forward and update
    ):
        self.result_store = result_store
        self.original_text_storage_id = original_text_storage_id
        self.http_session = http_session
        self.essay_id = essay_id
        self.initial_system_metadata = initial_system_metadata

    async def perform_spell_check(self, text: str) -> SpellcheckResultDataV1:
        corrected_text, corrections_count = await default_perform_spell_check_algorithm(
            text, self.essay_id
        )

        new_storage_id: Optional[str] = None
        storage_metadata_for_result: Optional[StorageReferenceMetadata] = None
        current_status = EssayStatus.SPELLCHECKED_SUCCESS
        error_detail = None

        if corrected_text:
            try:
                new_storage_id = await self.result_store.store_content(
                    original_storage_id=self.original_text_storage_id,
                    content_type=ContentType.CORRECTED_TEXT,
                    content=corrected_text,
                    http_session=self.http_session,
                )
                if new_storage_id:
                    storage_metadata_for_result = StorageReferenceMetadata(
                        references={ContentType.CORRECTED_TEXT: {"default": new_storage_id}}
                    )
                else:
                    current_status = EssayStatus.SPELLCHECK_FAILED
                    error_detail = "Failed to store corrected text (no storage_id returned)."
            except Exception as e:
                logger.error(
                    f"Essay {self.essay_id}: Failed to store corrected text: {e}", exc_info=True
                )
                current_status = EssayStatus.SPELLCHECK_FAILED
                error_detail = f"Exception storing corrected text: {str(e)[:100]}"
        else:
            current_status = EssayStatus.SPELLCHECK_FAILED
            error_detail = "Spell check algorithm did not return corrected text."
            logger.warning(f"Essay {self.essay_id}: {error_detail}")
            corrections_count = 0  # Ensure corrections_count is not None if no text

        # entity_type is correct for EntityReference
        final_entity_ref = EntityReference(entity_id=self.essay_id, entity_type="essay")

        # Update system_metadata based on this step's outcome
        updated_error_info = self.initial_system_metadata.error_info.copy()
        if error_detail and not updated_error_info.get("spellcheck_error"):
            updated_error_info["spellcheck_error"] = error_detail

        final_system_metadata = self.initial_system_metadata.model_copy(
            update={
                "processing_stage": (
                    ProcessingStage.COMPLETED
                    if current_status == EssayStatus.SPELLCHECKED_SUCCESS
                    else ProcessingStage.FAILED
                ),
                # String value of the enum
                "event": ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                "completed_at": datetime.now(timezone.utc),
                "error_info": updated_error_info,
            }
        )
        # Ensure entity in system_metadata is the correct one for this essay
        final_system_metadata.entity = final_entity_ref

        return SpellcheckResultDataV1(
            original_text_storage_id=self.original_text_storage_id,
            storage_metadata=storage_metadata_for_result,
            corrections_made=corrections_count,
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
            entity_ref=final_entity_ref,
            timestamp=datetime.now(timezone.utc),  # Timestamp of this result data creation
            status=current_status,
            system_metadata=final_system_metadata,
        )


class DefaultSpellcheckEventPublisher(SpellcheckEventPublisherProtocol):
    def __init__(self, kafka_event_type: str, source_service_name: str, kafka_output_topic: str):
        self.kafka_event_type = kafka_event_type
        self.source_service_name = source_service_name
        self.kafka_output_topic = kafka_output_topic

    async def publish_spellcheck_result(
        self,
        producer: AIOKafkaProducer,
        event_data: SpellcheckResultDataV1,
        correlation_id: Optional[UUID],
    ) -> None:
        result_envelope = EventEnvelope[SpellcheckResultDataV1](
            event_type=self.kafka_event_type,
            source_service=self.source_service_name,
            correlation_id=correlation_id,
            data=event_data,
        )

        key_to_encode = event_data.entity_ref.entity_id
        if not isinstance(key_to_encode, str):
            key_to_encode = str(key_to_encode)

        await producer.send_and_wait(
            topic=self.kafka_output_topic,
            value=result_envelope.model_dump_json().encode("utf-8"),
            key=key_to_encode.encode("utf-8"),
        )
        logger.info(
            f"Published spellcheck result for essay {event_data.entity_ref.entity_id} "
            f"to {self.kafka_output_topic}"
        )


# --- Main Processing Logic ---


async def process_single_message(
    msg: ConsumerRecord,
    producer: AIOKafkaProducer,
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    result_store: ResultStoreProtocol,
    event_publisher: SpellcheckEventPublisherProtocol,
) -> bool:
    """Process a single Kafka message.

    Args:
        msg: The Kafka message to process
        producer: Kafka producer for sending result events
        http_session: HTTP session for content service interaction
        content_client: Client for fetching content
        result_store: Client for storing content
        event_publisher: Client for publishing events

    Returns:
        bool: True if the message should be committed, False otherwise
    """
    from worker_main import CONSUMER_GROUP_ID, KAFKA_QUEUE_LATENCY

    processing_started_at = datetime.now(timezone.utc)
    request_envelope: Optional[EventEnvelope[SpellcheckRequestedDataV1]] = None
    # Default if ID not parsed
    essay_id_for_logging: str = f"offset-{msg.offset}-partition-{msg.partition}"

    try:
        raw_message = msg.value.decode("utf-8")
        request_envelope = EventEnvelope[SpellcheckRequestedDataV1].model_validate_json(raw_message)
        request_data = request_envelope.data

        # Record queue latency metric if available
        if KAFKA_QUEUE_LATENCY and hasattr(request_envelope, 'event_timestamp') and request_envelope.event_timestamp:
            queue_latency_seconds = (processing_started_at - request_envelope.event_timestamp).total_seconds()
            if queue_latency_seconds >= 0:  # Avoid negative values from clock skew
                KAFKA_QUEUE_LATENCY.labels(
                    topic=msg.topic,
                    consumer_group=CONSUMER_GROUP_ID
                ).observe(queue_latency_seconds)
                logger.debug(f"Recorded queue latency: {queue_latency_seconds:.3f}s for {msg.topic}")

        # Set a more meaningful ID for logging if available
        if request_data.entity_ref and request_data.entity_ref.entity_id:
            essay_id_for_logging = request_data.entity_ref.entity_id

        # Log about the event we received
        log_event_processing(
            logger=logger,
            message="Received spellcheck request",
            envelope=request_envelope,
            # additional_context for log_event_processing
            current_processing_event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
            current_processing_stage=(
                request_data.system_metadata.processing_stage.value
                if request_data.system_metadata.processing_stage
                else "unknown_stage"
            ),
        )

        # Fetch original text content
        original_text: Optional[str] = None
        try:
            # Pass essay_id to impl for logging, if default_fetch_content_impl
            # is modified to accept it optionally.
            # For now, calling as per DefaultContentClient which matches protocol.
            original_text = await content_client.fetch_content(
                storage_id=request_data.text_storage_id,
                http_session=http_session,
            )
        except Exception as fetch_exc:
            logger.error(
                f"Essay {essay_id_for_logging}: Failed to fetch original content: {fetch_exc}",
                exc_info=True,
            )

            error_sys_meta = request_data.system_metadata.model_copy(
                update={
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "error_info": {
                        "fetch_error": f"Failed to fetch original content: {str(fetch_exc)[:150]}"
                    },
                }
            )
            failure_event_data = SpellcheckResultDataV1(
                original_text_storage_id=request_data.text_storage_id,
                storage_metadata=None,
                corrections_made=None,
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                entity_ref=request_data.entity_ref,
                timestamp=datetime.now(timezone.utc),
                status=EssayStatus.SPELLCHECK_FAILED,
                system_metadata=error_sys_meta,
            )
            await event_publisher.publish_spellcheck_result(
                producer, failure_event_data, request_envelope.correlation_id
            )
            return True

        if not original_text:  # Should be caught by error handler above in most cases
            logger.error(
                f"Essay {essay_id_for_logging}: Fetched original content is None/empty. "
                f"Cannot proceed."
            )
            empty_content_sys_meta = request_data.system_metadata.model_copy(
                update={
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "error_info": {"content_error": "Fetched content is None or empty"},
                }
            )
            empty_content_failure_data = SpellcheckResultDataV1(
                original_text_storage_id=request_data.text_storage_id,
                storage_metadata=None,
                corrections_made=None,
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                entity_ref=request_data.entity_ref,
                timestamp=datetime.now(timezone.utc),
                status=EssayStatus.SPELLCHECK_FAILED,
                system_metadata=empty_content_sys_meta,
            )
            await event_publisher.publish_spellcheck_result(
                producer, empty_content_failure_data, request_envelope.correlation_id
            )
            return True

        # Create a DefaultSpellLogic instance for this particular message/essay
        # This allows passing essay_id and original_text_storage_id to the spell logic
        spell_logic = DefaultSpellLogic(
            result_store=result_store,
            original_text_storage_id=request_data.text_storage_id,
            http_session=http_session,
            essay_id=essay_id_for_logging,
            initial_system_metadata=request_data.system_metadata,
        )

        # Perform the spell check
        result_data = await spell_logic.perform_spell_check(original_text)

        # Publish the result
        await event_publisher.publish_spellcheck_result(
            producer, result_data, request_envelope.correlation_id
        )

        # Log processing times for latency analysis
        processing_ended_at = datetime.now(timezone.utc)
        processing_seconds = (processing_ended_at - processing_started_at).total_seconds()
        logger.info(
            f"Essay {essay_id_for_logging}: Completed processing in "
            f"{processing_seconds:.2f} seconds"
        )
        return True
    except ValidationError as e:
        logger.error(
            f"Essay {essay_id_for_logging}: Invalid message format: {e.errors()}", exc_info=True
        )
        return True
    except Exception as e:
        logger.error(
            f"Essay {essay_id_for_logging}: Unhandled error processing message: {e}", exc_info=True
        )
        if request_envelope and event_publisher:  # Check event_publisher also
            try:
                error_entity_ref = EntityReference(
                    entity_id=essay_id_for_logging, entity_type="essay"
                )
                if request_envelope.data and request_envelope.data.entity_ref:
                    error_entity_ref = request_envelope.data.entity_ref

                error_sys_meta_update = {
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                    "completed_at": datetime.now(timezone.utc),
                    "error_info": {"unhandled_error": f"Unhandled error: {str(e)[:200]}"},
                }
                if request_envelope.data and request_envelope.data.system_metadata:
                    final_error_sys_meta = request_envelope.data.system_metadata.model_copy(
                        update=error_sys_meta_update
                    )
                else:  # Create minimal if no incoming
                    final_error_sys_meta = SystemProcessingMetadata(
                        entity=error_entity_ref,
                        timestamp=processing_started_at,  # Time of initial processing attempt
                        started_at=processing_started_at,
                        processing_stage=ProcessingStage.FAILED,
                        event=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED.value,
                        completed_at=datetime.now(timezone.utc),
                        error_info={"unhandled_error": f"Unhandled error: {str(e)[:200]}"},
                    )

                unhandled_failure_data = SpellcheckResultDataV1(
                    original_text_storage_id=(
                        request_envelope.data.text_storage_id
                        if request_envelope.data
                        else "unknown"
                    ),
                    storage_metadata=None,
                    corrections_made=None,
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED,
                    entity_ref=error_entity_ref,
                    timestamp=datetime.now(timezone.utc),
                    status=EssayStatus.SPELLCHECK_FAILED,
                    system_metadata=final_error_sys_meta,
                )
                # Publish the error event
                await event_publisher.publish_spellcheck_result(
                    producer, unhandled_failure_data, request_envelope.correlation_id
                )
            except Exception as pub_e:
                logger.error(
                    f"Essay {essay_id_for_logging}: CRITICAL - Failed to publish failure event: "
                    f"{pub_e}",
                    exc_info=True,
                )
        return True

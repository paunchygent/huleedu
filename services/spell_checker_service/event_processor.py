"""Clean message processing logic for the Spell Checker Service.

This module contains only the core message processing logic, depending on
injected protocol implementations for all external interactions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import aiohttp
from aiokafka import AIOKafkaProducer, ConsumerRecord
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from protocol_implementations.spell_logic_impl import DefaultSpellLogic
from protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
)
from pydantic import ValidationError

from common_core.enums import EssayStatus, ProcessingEvent, ProcessingStage
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckResultDataV1,
)
from common_core.metadata_models import EntityReference, SystemProcessingMetadata

logger = create_service_logger("spell_checker_service.event_processor")


async def process_single_message(
    msg: ConsumerRecord,
    producer: AIOKafkaProducer,
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    result_store: ResultStoreProtocol,
    event_publisher: SpellcheckEventPublisherProtocol,
    consumer_group_id: str = "spell-checker-group",
    kafka_queue_latency_metric: Optional[Any] = None,
) -> bool:
    """Process a single Kafka message.

    Args:
        msg: The Kafka message to process
        producer: Kafka producer for sending result events
        http_session: HTTP session for content service interaction
        content_client: Client for fetching content
        result_store: Client for storing content
        event_publisher: Client for publishing events
        consumer_group_id: Consumer group ID for metrics
        kafka_queue_latency_metric: Optional Prometheus metric for queue latency

    Returns:
        bool: True if the message should be committed, False otherwise
    """
    processing_started_at = datetime.now(timezone.utc)
    request_envelope: Optional[EventEnvelope[EssayLifecycleSpellcheckRequestV1]] = None
    # Default if ID not parsed
    essay_id_for_logging: str = f"offset-{msg.offset}-partition-{msg.partition}"

    try:
        raw_message = msg.value.decode("utf-8")
        request_envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1].model_validate_json(
            raw_message
        )
        request_data = request_envelope.data

        # Record queue latency metric if available
        if (
            kafka_queue_latency_metric
            and hasattr(request_envelope, "event_timestamp")
            and request_envelope.event_timestamp
        ):
            queue_latency_seconds = (
                processing_started_at - request_envelope.event_timestamp
            ).total_seconds()
            if queue_latency_seconds >= 0:  # Avoid negative values from clock skew
                kafka_queue_latency_metric.labels(
                    topic=msg.topic, consumer_group=consumer_group_id
                ).observe(queue_latency_seconds)
                logger.debug(
                    f"Recorded queue latency: {queue_latency_seconds:.3f}s for {msg.topic}"
                )

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
            http_session=http_session,
            original_text_storage_id=request_data.text_storage_id,
            initial_system_metadata=request_data.system_metadata,
        )

        # Extract language from the new event model
        language = request_data.language if hasattr(request_data, "language") else "en"

        # Perform the spell check
        result_data = await spell_logic.perform_spell_check(
            original_text, essay_id_for_logging, language
        )

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
            f"Essay {essay_id_for_logging}: Unhandled error processing message: {e}",
            exc_info=True,
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

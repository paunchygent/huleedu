"""Clean message processing logic for the Spell Checker Service.

This module contains only the core message processing logic, depending on
injected protocol implementations for all external interactions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import ConsumerRecord
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from huleedu_service_libs.observability import (
    trace_operation,
    use_trace_context,
)
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from pydantic import ValidationError

from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckResultDataV1,
)
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.status_enums import EssayStatus, ProcessingStage
from services.spell_checker_service.metrics import get_business_metrics
from services.spell_checker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)

logger = create_service_logger("spell_checker_service.event_processor")


async def process_single_message(
    msg: ConsumerRecord,
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    result_store: ResultStoreProtocol,
    event_publisher: SpellcheckEventPublisherProtocol,
    spell_logic: SpellLogicProtocol,
    kafka_bus: KafkaPublisherProtocol,
    tracer: "Tracer | None" = None,
    consumer_group_id: str = "spell-checker-group",
) -> bool:
    """Process a single Kafka message with proper trace context propagation."""
    # First, parse the message to get the envelope
    try:
        raw_message = msg.value.decode("utf-8")
        request_envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1].model_validate_json(
            raw_message,
        )
    except Exception as e:
        logger.error(f"Failed to parse message: {e}", exc_info=True)
        return False

    # If we have trace context in metadata and a tracer, use the parent context
    if request_envelope.metadata and tracer:
        with use_trace_context(request_envelope.metadata):
            # Create a child span for this Kafka message processing
            with trace_operation(
                tracer,
                "kafka.consume.spellcheck_request",
                {
                    "messaging.system": "kafka",
                    "messaging.destination": msg.topic,
                    "messaging.operation": "consume",
                    "kafka.partition": msg.partition,
                    "kafka.offset": msg.offset,
                    "correlation_id": str(request_envelope.correlation_id),
                    "event_id": str(request_envelope.event_id),
                },
            ):
                return await _process_single_message_impl(
                    msg,
                    request_envelope,
                    http_session,
                    content_client,
                    result_store,
                    event_publisher,
                    spell_logic,
                    kafka_bus,
                    tracer,
                    consumer_group_id,
                )
    else:
        # No parent context, process without it
        return await _process_single_message_impl(
            msg,
            request_envelope,
            http_session,
            content_client,
            result_store,
            event_publisher,
            spell_logic,
            kafka_bus,
            tracer,
            consumer_group_id,
        )


async def _process_single_message_impl(
    msg: ConsumerRecord,
    request_envelope: EventEnvelope[EssayLifecycleSpellcheckRequestV1],
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    result_store: ResultStoreProtocol,
    event_publisher: SpellcheckEventPublisherProtocol,
    spell_logic: SpellLogicProtocol,
    kafka_bus: KafkaPublisherProtocol,
    tracer: "Tracer | None" = None,
    consumer_group_id: str = "spell-checker-group",
) -> bool:
    """Implementation of message processing logic.

    Args:
        msg: The Kafka message to process
        request_envelope: Already parsed event envelope
        http_session: HTTP session for content service interaction
        content_client: Client for fetching content
        result_store: Store for saving processed results
        event_publisher: Publisher for result events
        spell_logic: Spell checking logic implementation
        kafka_bus: Kafka bus for publishing events
        tracer: Optional tracer for distributed tracing
        consumer_group_id: Consumer group ID for metrics

    Returns:
        bool: True if processing succeeded, False otherwise
    """
    processing_started_at = datetime.now(UTC)

    # Get business metrics from shared module
    business_metrics = get_business_metrics()
    corrections_metric = business_metrics.get("spellcheck_corrections_made")
    kafka_queue_latency_metric = business_metrics.get("kafka_queue_latency_seconds")

    # Default if ID not parsed
    essay_id_for_logging: str = f"offset-{msg.offset}-partition-{msg.partition}"

    try:
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
                kafka_queue_latency_metric.observe(queue_latency_seconds)
                logger.debug(
                    f"Recorded queue latency: {queue_latency_seconds:.3f}s for {msg.topic}",
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

        logger.info(
            f"Step 1: Fetching content for essay {essay_id_for_logging}",
            extra={"correlation_id": str(request_envelope.correlation_id)},
        )

        # Fetch original text content - content_client now manages its own http_session
        original_text: str | None = None
        try:
            original_text = await content_client.fetch_content(
                storage_id=request_data.text_storage_id,
                http_session=http_session,
            )
            logger.info(
                f"Step 2: Content fetched successfully for essay {essay_id_for_logging}",
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )
        except Exception as fetch_exc:
            logger.error(
                f"Essay {essay_id_for_logging}: Failed to fetch original content: {fetch_exc}",
                exc_info=True,
            )

            error_sys_meta = request_data.system_metadata.model_copy(
                update={
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                    "completed_at": datetime.now(UTC),
                    "error_info": {
                        "fetch_error": f"Failed to fetch original content: {str(fetch_exc)[:150]}",
                    },
                },
            )
            failure_event_data = SpellcheckResultDataV1(
                original_text_storage_id=request_data.text_storage_id,
                storage_metadata=None,
                corrections_made=None,
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                entity_ref=request_data.entity_ref,
                timestamp=datetime.now(UTC),
                status=EssayStatus.SPELLCHECK_FAILED,
                system_metadata=error_sys_meta,
            )
            await event_publisher.publish_spellcheck_result(
                kafka_bus,
                failure_event_data,
                request_envelope.correlation_id,
            )
            return True

        if not original_text:  # Should be caught by error handler above in most cases
            logger.error(
                f"Essay {essay_id_for_logging}: Fetched original content is None/empty. "
                f"Cannot proceed.",
            )
            empty_content_sys_meta = request_data.system_metadata.model_copy(
                update={
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                    "completed_at": datetime.now(UTC),
                    "error_info": {"content_error": "Fetched content is None or empty"},
                },
            )
            empty_content_failure_data = SpellcheckResultDataV1(
                original_text_storage_id=request_data.text_storage_id,
                storage_metadata=None,
                corrections_made=None,
                event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                entity_ref=request_data.entity_ref,
                timestamp=datetime.now(UTC),
                status=EssayStatus.SPELLCHECK_FAILED,
                system_metadata=empty_content_sys_meta,
            )
            await event_publisher.publish_spellcheck_result(
                kafka_bus,
                empty_content_failure_data,
                request_envelope.correlation_id,
            )
            return True

        logger.info(
            f"Step 3: Performing spell check for essay {essay_id_for_logging}",
            extra={"correlation_id": str(request_envelope.correlation_id)},
        )

        # Extract language from the new event model
        language = request_data.language if hasattr(request_data, "language") else "en"

        # Perform the spell check using injected spell logic protocol
        if tracer:
            with trace_operation(
                tracer,
                "perform_spell_check",
                {
                    "essay_id": essay_id_for_logging,
                    "language": language,
                    "correlation_id": str(request_envelope.correlation_id),
                },
            ):
                result_data = await spell_logic.perform_spell_check(
                    original_text,
                    essay_id_for_logging,
                    request_data.text_storage_id,
                    request_data.system_metadata,
                    language,
                )
        else:
            result_data = await spell_logic.perform_spell_check(
                original_text,
                essay_id_for_logging,
                request_data.text_storage_id,
                request_data.system_metadata,
                language,
            )

        # Record business metric for corrections made
        if corrections_metric and result_data.corrections_made is not None:
            corrections_metric.observe(result_data.corrections_made)
            logger.debug(
                f"Recorded {result_data.corrections_made} corrections "
                f"for essay {essay_id_for_logging}",
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )

        logger.info(
            f"Step 4: Publishing spell check result for essay {essay_id_for_logging}",
            extra={"correlation_id": str(request_envelope.correlation_id)},
        )

        # Publish the result
        await event_publisher.publish_spellcheck_result(
            kafka_bus,
            result_data,
            request_envelope.correlation_id,
        )

        # Log processing times for latency analysis
        processing_ended_at = datetime.now(UTC)
        processing_seconds = (processing_ended_at - processing_started_at).total_seconds()
        logger.info(
            f"Essay {essay_id_for_logging}: Completed processing in "
            f"{processing_seconds:.2f} seconds",
        )
        return True
    except ValidationError as e:
        logger.error(
            f"Essay {essay_id_for_logging}: Invalid message format: {e.errors()}",
            exc_info=True,
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
                    entity_id=essay_id_for_logging,
                    entity_type="essay",
                )
                if request_envelope.data and request_envelope.data.entity_ref:
                    error_entity_ref = request_envelope.data.entity_ref

                error_sys_meta_update = {
                    "processing_stage": ProcessingStage.FAILED,
                    "event": ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                    "completed_at": datetime.now(UTC),
                    "error_info": {"unhandled_error": f"Unhandled error: {str(e)[:200]}"},
                }
                if request_envelope.data and request_envelope.data.system_metadata:
                    final_error_sys_meta = request_envelope.data.system_metadata.model_copy(
                        update=error_sys_meta_update,
                    )
                else:  # Create minimal if no incoming
                    final_error_sys_meta = SystemProcessingMetadata(
                        entity=error_entity_ref,
                        timestamp=processing_started_at,  # Time of initial processing attempt
                        started_at=processing_started_at,
                        processing_stage=ProcessingStage.FAILED,
                        event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                        completed_at=datetime.now(UTC),
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
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
                    entity_ref=error_entity_ref,
                    timestamp=datetime.now(UTC),
                    status=EssayStatus.SPELLCHECK_FAILED,
                    system_metadata=final_error_sys_meta,
                )
                # Publish the error event
                await event_publisher.publish_spellcheck_result(
                    kafka_bus,
                    unhandled_failure_data,
                    request_envelope.correlation_id,
                )
            except Exception as pub_e:
                logger.error(
                    f"Essay {essay_id_for_logging}: CRITICAL - Failed to publish failure event: "
                    f"{pub_e}",
                    exc_info=True,
                )
        return True

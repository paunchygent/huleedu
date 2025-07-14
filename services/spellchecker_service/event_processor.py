"""Clean message processing logic for the Spell Checker Service.

This module contains only the core message processing logic, depending on
injected protocol implementations for all external interactions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import ConsumerRecord
from huleedu_service_libs.error_handling import (
    raise_content_service_error,
    raise_parsing_error,
    raise_validation_error,
)
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.error_handling.huleedu_error import HuleEduError
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from huleedu_service_libs.observability import (
    trace_operation,
    use_trace_context,
)
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from opentelemetry import trace
from pydantic import ValidationError

from common_core.error_enums import ErrorCode
from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
from common_core.event_enums import ProcessingEvent
from common_core.events.envelope import EventEnvelope
from common_core.events.spellcheck_models import (
    SpellcheckResultDataV1,
)
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import EssayStatus, ProcessingStage
from services.spellchecker_service.metrics import get_business_metrics
from services.spellchecker_service.protocols import (
    ContentClientProtocol,
    ResultStoreProtocol,
    SpellcheckEventPublisherProtocol,
    SpellLogicProtocol,
)

logger = create_service_logger("spellchecker_service.event_processor")


def _categorize_processing_error(exception: Exception, correlation_id: UUID) -> ErrorDetail:
    """Categorize processing exceptions into appropriate ErrorCode types."""
    if isinstance(exception, HuleEduError):
        # Already structured - return the underlying error detail
        return exception.error_detail

    # Categorize based on exception type and message content
    error_message = str(exception)
    exception_type = type(exception).__name__

    if "timeout" in error_message.lower() or "timeout" in exception_type.lower():
        error_code = ErrorCode.TIMEOUT
    elif "connection" in error_message.lower() or "connection" in exception_type.lower():
        error_code = ErrorCode.CONNECTION_ERROR
    elif "validation" in error_message.lower() or "ValidationError" in exception_type:
        error_code = ErrorCode.VALIDATION_ERROR
    elif "parse" in error_message.lower() or "json" in error_message.lower():
        error_code = ErrorCode.PARSING_ERROR
    else:
        error_code = ErrorCode.PROCESSING_ERROR

    return create_error_detail_with_context(
        error_code=error_code,
        message=f"Categorized error: {error_message}",
        service="spellchecker_service",
        operation="categorize_processing_error",
        correlation_id=correlation_id,
        details={
            "original_exception_type": exception_type,
            "original_message": error_message,
        },
        capture_stack=False,
    )


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
    # First, parse the message to get the envelope with structured error handling
    try:
        raw_message = msg.value.decode("utf-8")
        request_envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1].model_validate_json(
            raw_message,
        )
    except Exception as e:
        # Use structured error handling for parsing failures
        correlation_id = uuid4()  # Generate correlation_id for parsing errors
        logger.error(
            f"Failed to parse Kafka message: {e}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id), "topic": msg.topic, "offset": msg.offset},
        )
        raise_parsing_error(
            service="spellchecker_service",
            operation="parse_kafka_message",
            parse_target="EventEnvelope[EssayLifecycleSpellcheckRequestV1]",
            message=f"Failed to parse Kafka message: {str(e)}",
            correlation_id=correlation_id,
            topic=msg.topic,
            offset=msg.offset,
            raw_message_length=len(raw_message),
        )

    # Extract correlation_id early - this is critical for error tracking
    # correlation_id is guaranteed to be present due to EventEnvelope default_factory
    correlation_id = request_envelope.correlation_id

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
                    "correlation_id": str(correlation_id),
                    "event_id": str(request_envelope.event_id),
                },
            ) as span:
                try:
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
                        span,
                    )
                except HuleEduError as he:
                    # Record structured error to the current span
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(he)))
                        span.set_attributes(
                            {
                                "error.type": he.error_detail.error_code.value,
                                "error.message": he.error_detail.message,
                                "error.correlation_id": str(he.error_detail.correlation_id),
                            }
                        )
                    raise
                except Exception as e:
                    # Categorize and convert to structured error
                    error_detail = _categorize_processing_error(e, correlation_id)
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                        span.set_attributes(
                            {
                                "error.type": error_detail.error_code.value,
                                "error.message": error_detail.message,
                                "error.correlation_id": str(error_detail.correlation_id),
                            }
                        )
                    raise HuleEduError(error_detail)
    else:
        # No parent context, process without it but still handle errors
        try:
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
                None,  # No span for no parent context branch
            )
        except HuleEduError:
            # Already structured - re-raise
            raise
        except Exception as e:
            # Categorize and convert to structured error
            error_detail = _categorize_processing_error(e, correlation_id)
            raise HuleEduError(error_detail)


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
    span: "trace.Span | None" = None,
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

        # Fetch original text content with structured error handling
        original_text: str | None = None
        try:
            original_text = await content_client.fetch_content(
                storage_id=request_data.text_storage_id,
                http_session=http_session,
                correlation_id=request_envelope.correlation_id,
            )
            logger.info(
                f"Step 2: Content fetched successfully for essay {essay_id_for_logging}",
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )
        except HuleEduError as he:
            # Already structured error from content client - re-raise as is
            logger.error(
                f"Essay {essay_id_for_logging}: Structured error fetching content: "
                f"{he.error_detail.message}",
                exc_info=True,
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )
            raise
        except Exception as fetch_exc:
            # Convert unstructured error to content service error
            logger.error(
                f"Essay {essay_id_for_logging}: Failed to fetch original content: {fetch_exc}",
                exc_info=True,
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )
            # Use structured error handling for content fetch failures
            raise_content_service_error(
                service="spellchecker_service",
                operation="fetch_original_content",
                message=f"Failed to fetch content: {str(fetch_exc)}",
                correlation_id=request_envelope.correlation_id,
                storage_id=request_data.text_storage_id,
                original_exception=str(fetch_exc),
            )

        if not original_text:  # Should be caught by error handler above in most cases
            logger.error(
                f"Essay {essay_id_for_logging}: Fetched original content is None/empty. "
                f"Cannot proceed.",
                extra={"correlation_id": str(request_envelope.correlation_id)},
            )
            # Use structured error handling for empty content validation
            raise_validation_error(
                service="spellchecker_service",
                operation="validate_content",
                field="original_text",
                message="Fetched content is None or empty",
                correlation_id=request_envelope.correlation_id,
                value=original_text,
                storage_id=request_data.text_storage_id,
                validation_type="content_not_empty",
            )

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
                    request_envelope.correlation_id,
                    language,
                )
        else:
            result_data = await spell_logic.perform_spell_check(
                original_text,
                essay_id_for_logging,
                request_data.text_storage_id,
                request_data.system_metadata,
                request_envelope.correlation_id,
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
        # Use structured error handling for validation errors
        logger.error(
            f"Essay {essay_id_for_logging}: Invalid message format: {e.errors()}",
            exc_info=True,
            extra={"correlation_id": str(request_envelope.correlation_id)},
        )

        # Create structured validation error but don't raise (return success to commit offset)
        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.VALIDATION_ERROR,
            message=f"Invalid message format: {str(e)}",
            service="spellchecker_service",
            operation="validate_message_format",
            correlation_id=request_envelope.correlation_id,
            details={
                "validation_errors": e.errors(),
                "essay_id": essay_id_for_logging,
            },
        )

        # Publish structured error event if possible
        await _publish_structured_error_event(
            error_detail,
            request_envelope,
            event_publisher,
            kafka_bus,
            essay_id_for_logging,
            processing_started_at,
        )
        return True

    except HuleEduError as he:
        # Already structured error - log and publish
        logger.error(
            f"Essay {essay_id_for_logging}: Structured error processing message: "
            f"{he.error_detail.message}",
            exc_info=True,
            extra={"correlation_id": str(he.error_detail.correlation_id)},
        )

        # Record error on span for observability
        if span:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(he)))
            span.set_attributes(
                {
                    "error.type": he.error_detail.error_code.value,
                    "error.message": he.error_detail.message,
                    "error.correlation_id": str(he.error_detail.correlation_id),
                }
            )

        # Publish structured error event
        await _publish_structured_error_event(
            he.error_detail,
            request_envelope,
            event_publisher,
            kafka_bus,
            essay_id_for_logging,
            processing_started_at,
        )
        return True

    except Exception as e:
        # Convert unstructured error to structured error
        logger.error(
            f"Essay {essay_id_for_logging}: Unhandled error processing message: {e}",
            exc_info=True,
            extra={
                "correlation_id": str(request_envelope.correlation_id)
                if request_envelope
                else "unknown"
            },
        )

        # Categorize the error
        correlation_id_for_error = request_envelope.correlation_id if request_envelope else uuid4()
        error_detail = _categorize_processing_error(e, correlation_id_for_error)

        # Record error on span for observability
        if span:
            span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
            span.set_attributes(
                {
                    "error.type": error_detail.error_code.value,
                    "error.message": error_detail.message,
                    "error.correlation_id": str(error_detail.correlation_id),
                }
            )

        # Publish structured error event
        if request_envelope and event_publisher:
            await _publish_structured_error_event(
                error_detail,
                request_envelope,
                event_publisher,
                kafka_bus,
                essay_id_for_logging,
                processing_started_at,
            )
        return True


async def _publish_structured_error_event(
    error_detail: ErrorDetail,
    request_envelope: EventEnvelope[EssayLifecycleSpellcheckRequestV1],
    event_publisher: SpellcheckEventPublisherProtocol,
    kafka_bus: KafkaPublisherProtocol,
    essay_id_for_logging: str,
    processing_started_at: datetime,
) -> None:
    """Publish a structured error event with proper error information."""
    try:
        # Preserve entity reference from incoming request to maintain parent_id (batch_id)
        if request_envelope.data and request_envelope.data.entity_ref:
            error_entity_ref = request_envelope.data.entity_ref.model_copy(
                update={"entity_id": essay_id_for_logging}
            )
        else:
            error_entity_ref = EntityReference(
                entity_id=essay_id_for_logging,
                entity_type="essay",
            )

        # Create structured error info from ErrorDetail
        structured_error_info = {
            "error_code": error_detail.error_code.value,
            "error_message": error_detail.message,
            "correlation_id": str(error_detail.correlation_id),
            "timestamp": error_detail.timestamp.isoformat(),
            "service": error_detail.service,
            "details": error_detail.details,
        }

        error_sys_meta_update = {
            "processing_stage": ProcessingStage.FAILED,
            "event": ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
            "completed_at": datetime.now(UTC),
            "error_info": structured_error_info,
        }

        if request_envelope.data and request_envelope.data.system_metadata:
            final_error_sys_meta = request_envelope.data.system_metadata.model_copy(
                update=error_sys_meta_update,
            )
        else:  # Create minimal if no incoming
            final_error_sys_meta = SystemProcessingMetadata(
                entity=error_entity_ref,
                timestamp=processing_started_at,
                started_at=processing_started_at,
                processing_stage=ProcessingStage.FAILED,
                event=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED.value,
                completed_at=datetime.now(UTC),
                error_info=structured_error_info,
            )

        structured_failure_data = SpellcheckResultDataV1(
            original_text_storage_id=(
                request_envelope.data.text_storage_id if request_envelope.data else "unknown"
            ),
            storage_metadata=None,
            corrections_made=None,
            event_name=ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED,
            entity_ref=error_entity_ref,
            timestamp=datetime.now(UTC),
            status=EssayStatus.SPELLCHECK_FAILED,
            system_metadata=final_error_sys_meta,
        )

        # Publish the structured error event
        await event_publisher.publish_spellcheck_result(
            kafka_bus,
            structured_failure_data,
            request_envelope.correlation_id,
        )

    except Exception as pub_e:
        logger.error(
            f"Essay {essay_id_for_logging}: CRITICAL - Failed to publish structured failure event: "
            f"{pub_e}",
            exc_info=True,
            extra={"correlation_id": str(error_detail.correlation_id)},
        )

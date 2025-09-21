"""
Event routing and processing logic for the Essay Lifecycle Service.

This module handles incoming Kafka events and orchestrates essay state transitions
using the injected dependencies.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from opentelemetry.trace import Tracer

from aiokafka import ConsumerRecord
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import (
    trace_operation,
    use_trace_context,
)

from services.essay_lifecycle_service.metrics import get_business_metrics
from services.essay_lifecycle_service.protocols import (
    BatchCommandHandler,
    BatchCoordinationHandler,
    ServiceResultHandler,
)

logger = create_service_logger("batch_command_handlers")


async def process_single_message(
    msg: ConsumerRecord,
    batch_coordination_handler: BatchCoordinationHandler,
    batch_command_handler: BatchCommandHandler,
    service_result_handler: ServiceResultHandler,
    tracer: Tracer | None = None,
    confirm_idempotency: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """
    Process a single Kafka message and update essay state accordingly.

    Args:
        msg: Kafka consumer record
        batch_coordination_handler: Handler for batch coordination events
        batch_command_handler: Handler for batch processing commands
        service_result_handler: Handler for specialized service results
        tracer: Optional OpenTelemetry tracer for distributed tracing
        confirm_idempotency: Optional idempotency confirmation callback

    Returns:
        True if message was processed successfully, False otherwise
    """
    time.time()

    try:
        # Deserialize message
        envelope = _deserialize_message(msg)
        if envelope is None:
            return False

        # If we have trace context in metadata and a tracer, use the parent context
        if envelope.metadata and tracer:
            with use_trace_context(envelope.metadata):
                # Create a child span for this Kafka message processing
                with trace_operation(
                    tracer,
                    f"kafka.consume.{envelope.event_type}",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "kafka.partition": msg.partition,
                        "kafka.offset": msg.offset,
                        "correlation_id": str(envelope.correlation_id),
                        "event_id": str(envelope.event_id),
                        "event_type": envelope.event_type,
                        "source_service": envelope.source_service,
                    },
                ):
                    return await _process_message_impl(
                        msg,
                        envelope,
                        batch_coordination_handler,
                        batch_command_handler,
                        service_result_handler,
                        confirm_idempotency,
                    )
        else:
            # No parent context or tracer, process without tracing
            return await _process_message_impl(
                msg,
                envelope,
                batch_coordination_handler,
                batch_command_handler,
                service_result_handler,
                confirm_idempotency,
            )

    except Exception as e:
        logger.error(
            "Unexpected error processing message",
            extra={"error": str(e), "topic": msg.topic, "offset": msg.offset},
        )
        return False


async def _process_message_impl(
    msg: ConsumerRecord,
    envelope: EventEnvelope[Any],
    batch_coordination_handler: BatchCoordinationHandler,
    batch_command_handler: BatchCommandHandler,
    service_result_handler: ServiceResultHandler,
    confirm_idempotency: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """Process the message after tracing context has been set up."""
    # Record Kafka queue latency
    business_metrics = get_business_metrics()
    kafka_latency_metric = business_metrics.get("kafka_queue_latency")
    if kafka_latency_metric and envelope.event_timestamp:
        queue_latency = time.time() - envelope.event_timestamp.timestamp()
        kafka_latency_metric.labels(topic=msg.topic, service="essay_lifecycle_service").observe(
            queue_latency
        )

    correlation_id = envelope.correlation_id
    logger.info(
        "Processing event",
        extra={
            "event_type": envelope.event_type,
            "correlation_id": str(correlation_id),
            "source_service": envelope.source_service,
        },
    )

    # Route to appropriate handler
    success = await _route_event(
        envelope=envelope,
        batch_coordination_handler=batch_coordination_handler,
        batch_command_handler=batch_command_handler,
        service_result_handler=service_result_handler,
        confirm_idempotency=confirm_idempotency,
    )

    if success:
        logger.info("Event processed successfully", extra={"correlation_id": str(correlation_id)})
    else:
        logger.error("Event processing failed", extra={"correlation_id": str(correlation_id)})

    return success


def _deserialize_message(msg: ConsumerRecord) -> EventEnvelope[Any] | None:
    """Deserialize Kafka message to EventEnvelope."""
    try:
        raw_message = msg.value.decode("utf-8")
        return EventEnvelope[Any].model_validate_json(raw_message)
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(
            "Failed to deserialize message",
            extra={"error": str(e), "topic": msg.topic, "offset": msg.offset},
        )
        return None


async def _route_event(
    envelope: EventEnvelope[Any],
    batch_coordination_handler: BatchCoordinationHandler,
    batch_command_handler: BatchCommandHandler,
    service_result_handler: ServiceResultHandler,
    confirm_idempotency: Callable[[], Awaitable[None]] | None = None,
) -> bool:
    """Route events to appropriate handlers based on event type."""
    from huleedu_service_libs.observability import use_trace_context

    event_type = envelope.event_type
    correlation_id = envelope.correlation_id

    # Get business metrics for coordination tracking
    business_metrics = get_business_metrics()
    coordination_events_metric = business_metrics.get("batch_coordination_events")

    try:
        # Handle batch coordination events
        if event_type == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED):
            from common_core.events.batch_coordination_events import BatchEssaysRegistered

            batch_event_data = BatchEssaysRegistered.model_validate(envelope.data)

            # Record batch coordination event
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="batch_registered", batch_id=str(batch_event_data.entity_id)
                ).inc()

            batch_result: bool = await batch_coordination_handler.handle_batch_essays_registered(
                event_data=batch_event_data, correlation_id=correlation_id
            )
            return batch_result

        elif event_type == topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED):
            from common_core.events.file_events import EssayContentProvisionedV1

            content_event_data = EssayContentProvisionedV1.model_validate(envelope.data)

            # Record coordination event
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="content_provisioned", batch_id=str(content_event_data.entity_id)
                ).inc()

            content_result: bool = (
                await batch_coordination_handler.handle_essay_content_provisioned(
                    event_data=content_event_data, correlation_id=correlation_id
                )
            )
            return content_result

        elif event_type == topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED):
            from common_core.events.file_events import EssayValidationFailedV1

            validation_event_data = EssayValidationFailedV1.model_validate(envelope.data)

            # Record validation failure
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="validation_failed", batch_id=str(validation_event_data.entity_id)
                ).inc()

            validation_result: bool = (
                await batch_coordination_handler.handle_essay_validation_failed(
                    event_data=validation_event_data, correlation_id=correlation_id
                )
            )
            return validation_result

        # Handle BOS command events
        elif event_type == topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND):
            from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1

            command_data = BatchServiceSpellcheckInitiateCommandDataV1.model_validate(envelope.data)

            # Record command processing
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="spellcheck_command", batch_id=str(command_data.entity_id)
                ).inc()

            # Maintain trace context when calling the handler
            if envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await batch_command_handler.process_initiate_spellcheck_command(
                        command_data=command_data, correlation_id=correlation_id
                    )
            else:
                await batch_command_handler.process_initiate_spellcheck_command(
                    command_data=command_data, correlation_id=correlation_id
                )
            return True

        elif event_type == topic_name(ProcessingEvent.BATCH_CJ_ASSESSMENT_INITIATE_COMMAND):
            from common_core.batch_service_models import (
                BatchServiceCJAssessmentInitiateCommandDataV1,
            )

            cj_command_data = BatchServiceCJAssessmentInitiateCommandDataV1.model_validate(
                envelope.data
            )

            # Record CJ command processing
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="cj_command", batch_id=str(cj_command_data.entity_id)
                ).inc()

            # Maintain trace context when calling the handler
            if envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await batch_command_handler.process_initiate_cj_assessment_command(
                        command_data=cj_command_data,
                        correlation_id=correlation_id,
                        envelope_metadata=envelope.metadata,
                    )
            else:
                await batch_command_handler.process_initiate_cj_assessment_command(
                    command_data=cj_command_data,
                    correlation_id=correlation_id,
                    envelope_metadata=None,
                )
            return True

        elif event_type == topic_name(ProcessingEvent.BATCH_NLP_INITIATE_COMMAND):
            from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1

            nlp_command_data = BatchServiceNLPInitiateCommandDataV1.model_validate(envelope.data)

            # Record NLP command processing
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="nlp_command", batch_id=str(nlp_command_data.entity_id)
                ).inc()

            # Maintain trace context when calling the handler
            if envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await batch_command_handler.process_initiate_nlp_command(
                        command_data=nlp_command_data, correlation_id=correlation_id
                    )
            else:
                await batch_command_handler.process_initiate_nlp_command(
                    command_data=nlp_command_data, correlation_id=correlation_id
                )
            return True

        # Handle specialized service result events
        elif event_type == topic_name(ProcessingEvent.SPELLCHECK_RESULTS):
            from common_core.events.spellcheck_models import SpellcheckResultV1

            rich_result = SpellcheckResultV1.model_validate(envelope.data)

            return await service_result_handler.handle_spellcheck_rich_result(
                rich_result,
                correlation_id=correlation_id,
            )

        elif event_type == topic_name(ProcessingEvent.SPELLCHECK_PHASE_COMPLETED):
            from common_core.events.spellcheck_models import SpellcheckPhaseCompletedV1
            from common_core.status_enums import EssayStatus, ProcessingStatus

            thin_event = SpellcheckPhaseCompletedV1.model_validate(envelope.data)

            # Record spellcheck completion
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="spellcheck_completed",
                    batch_id=thin_event.batch_id,
                ).inc()

            # Convert thin event to format expected by handler
            # The handler only needs essay_id, status, and storage_id for state transitions
            essay_status = (
                EssayStatus.SPELLCHECKED_SUCCESS
                if thin_event.status == ProcessingStatus.COMPLETED
                else EssayStatus.SPELLCHECK_FAILED
            )

            spellcheck_result: bool = (
                await service_result_handler.handle_spellcheck_phase_completed(
                    essay_id=thin_event.entity_id,
                    batch_id=thin_event.batch_id,
                    status=essay_status,
                    corrected_text_storage_id=thin_event.corrected_text_storage_id,
                    error_code=thin_event.error_code,
                    correlation_id=correlation_id,
                    confirm_idempotency=confirm_idempotency,
                )
            )
            return spellcheck_result

        elif event_type == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
            from common_core.events.cj_assessment_events import CJAssessmentCompletedV1

            cj_result_data = CJAssessmentCompletedV1.model_validate(envelope.data)

            # Record CJ assessment completion
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="cj_completed", batch_id=str(cj_result_data.entity_id)
                ).inc()

            cj_result: bool = await service_result_handler.handle_cj_assessment_completed(
                result_data=cj_result_data,
                correlation_id=correlation_id,
                confirm_idempotency=confirm_idempotency,
            )
            return cj_result

        elif event_type == topic_name(ProcessingEvent.BATCH_NLP_ANALYSIS_COMPLETED):
            from common_core.events.nlp_events import BatchNlpAnalysisCompletedV1

            nlp_result_data = BatchNlpAnalysisCompletedV1.model_validate(envelope.data)

            # Record NLP analysis completion
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="nlp_completed", batch_id=str(nlp_result_data.batch_id)
                ).inc()

            # Handle the thin completion event - state transitions only
            nlp_result: bool = await service_result_handler.handle_nlp_analysis_completed(
                result_data=nlp_result_data,
                correlation_id=correlation_id,
                confirm_idempotency=confirm_idempotency,
            )
            return nlp_result

        # Handle Phase 1 student matching events
        elif event_type == topic_name(ProcessingEvent.BATCH_STUDENT_MATCHING_INITIATE_COMMAND):
            from common_core.batch_service_models import (
                BatchServiceStudentMatchingInitiateCommandDataV1,
            )

            student_matching_command_data = (
                BatchServiceStudentMatchingInitiateCommandDataV1.model_validate(envelope.data)
            )

            # Record student matching command
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="student_matching_command",
                    batch_id=str(student_matching_command_data.entity_id),
                ).inc()

            # Get student matching command handler from batch command handler
            # Maintain trace context when calling the handler
            if envelope.metadata:
                with use_trace_context(envelope.metadata):
                    await batch_command_handler.process_student_matching_command(
                        command_data=student_matching_command_data, correlation_id=correlation_id
                    )
            else:
                await batch_command_handler.process_student_matching_command(
                    command_data=student_matching_command_data, correlation_id=correlation_id
                )
            return True

        elif event_type == topic_name(ProcessingEvent.STUDENT_ASSOCIATIONS_CONFIRMED):
            from common_core.events.validation_events import StudentAssociationsConfirmedV1

            associations_data = StudentAssociationsConfirmedV1.model_validate(envelope.data)

            # Record student associations confirmed
            if coordination_events_metric:
                coordination_events_metric.labels(
                    event_type="associations_confirmed", batch_id=str(associations_data.batch_id)
                ).inc()

            # Handle through BatchCoordinationHandler for proper protocol compliance
            associations_result: bool = (
                await batch_coordination_handler.handle_student_associations_confirmed(
                    event_data=associations_data, correlation_id=correlation_id
                )
            )
            return associations_result

        else:
            logger.warning(
                "Unknown event type",
                extra={
                    "event_type": event_type,
                    "correlation_id": str(correlation_id),
                    "source_service": envelope.source_service,
                },
            )
            return False

    except Exception as e:
        logger.error(
            "Error routing event",
            extra={
                "error": str(e),
                "event_type": event_type,
                "correlation_id": str(correlation_id),
            },
        )
        return False


# All handler implementations moved to separate files:
# - batch_coordination_handler_impl.py
# - service_result_handler_impl.py
# - batch_command_handler_impl.py (existing)

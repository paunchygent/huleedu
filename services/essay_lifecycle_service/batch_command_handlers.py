"""
Event routing and processing logic for the Essay Lifecycle Service.

This module handles incoming Kafka events and orchestrates essay state transitions
using the injected dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from aiokafka import ConsumerRecord
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger

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
) -> bool:
    """
    Process a single Kafka message and update essay state accordingly.

    Args:
        msg: Kafka consumer record
        state_store: Essay state persistence layer
        event_publisher: Event publishing interface
        transition_validator: State transition validation logic
        metrics_collector: Metrics collection interface
        batch_tracker: Batch coordination and readiness tracking

    Returns:
        True if message was processed successfully, False otherwise
    """
    try:
        # Deserialize message
        envelope = _deserialize_message(msg)
        if envelope is None:
            return False

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
        )

        if success:
            logger.info(
                "Event processed successfully", extra={"correlation_id": str(correlation_id)}
            )
        else:
            logger.error("Event processing failed", extra={"correlation_id": str(correlation_id)})

        return success

    except Exception as e:
        logger.error(
            "Unexpected error processing message",
            extra={"error": str(e), "topic": msg.topic, "offset": msg.offset},
        )
        return False


def _deserialize_message(msg: ConsumerRecord) -> EventEnvelope[Any] | None:
    """Deserialize Kafka message to EventEnvelope."""
    try:
        data = json.loads(msg.value.decode("utf-8"))
        return EventEnvelope[Any].model_validate(data)
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
) -> bool:
    """Route events to appropriate handlers based on event type."""
    event_type = envelope.event_type
    correlation_id = envelope.correlation_id

    try:
        # Handle batch coordination events
        if event_type == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED):
            from common_core.events.batch_coordination_events import BatchEssaysRegistered

            batch_event_data = BatchEssaysRegistered.model_validate(envelope.data)
            batch_result: bool = await batch_coordination_handler.handle_batch_essays_registered(
                event_data=batch_event_data, correlation_id=correlation_id
            )
            return batch_result

        elif event_type == topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED):
            from common_core.events.file_events import EssayContentProvisionedV1

            content_event_data = EssayContentProvisionedV1.model_validate(envelope.data)
            content_result: bool = (
                await batch_coordination_handler.handle_essay_content_provisioned(
                    event_data=content_event_data, correlation_id=correlation_id
                )
            )
            return content_result

        elif event_type == topic_name(ProcessingEvent.ESSAY_VALIDATION_FAILED):
            from common_core.events.file_events import EssayValidationFailedV1

            validation_event_data = EssayValidationFailedV1.model_validate(envelope.data)
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
            await batch_command_handler.process_initiate_cj_assessment_command(
                command_data=cj_command_data, correlation_id=correlation_id
            )
            return True

        # Handle specialized service result events
        elif event_type == topic_name(ProcessingEvent.ESSAY_SPELLCHECK_COMPLETED):
            from common_core.events.spellcheck_models import SpellcheckResultDataV1

            result_data = SpellcheckResultDataV1.model_validate(envelope.data)
            spellcheck_result: bool = await service_result_handler.handle_spellcheck_result(
                result_data=result_data, correlation_id=correlation_id
            )
            return spellcheck_result

        elif event_type == topic_name(ProcessingEvent.CJ_ASSESSMENT_COMPLETED):
            from common_core.events.cj_assessment_events import CJAssessmentCompletedV1

            cj_result_data = CJAssessmentCompletedV1.model_validate(envelope.data)
            cj_result: bool = await service_result_handler.handle_cj_assessment_completed(
                result_data=cj_result_data, correlation_id=correlation_id
            )
            return cj_result

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

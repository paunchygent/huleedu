"""
Event routing and processing logic for the Essay Lifecycle Service.

This module handles incoming Kafka events and orchestrates essay state transitions
using the injected dependencies.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from aiokafka import ConsumerRecord
from common_core.batch_service_models import BatchServiceSpellcheckInitiateCommandDataV1
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentProvisionedV1
from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
    BatchCommandHandler,
    BatchEssayTracker,
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    StateTransitionValidator,
)

logger = create_service_logger("batch_command_handlers")


async def process_single_message(
    msg: ConsumerRecord,
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
    batch_tracker: BatchEssayTracker,
    batch_command_handler: BatchCommandHandler,
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
            state_store=state_store,
            event_publisher=event_publisher,
            transition_validator=transition_validator,
            metrics_collector=metrics_collector,
            batch_tracker=batch_tracker,
            batch_command_handler=batch_command_handler,
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
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
    batch_tracker: BatchEssayTracker,
    batch_command_handler: BatchCommandHandler,
) -> bool:
    """
    Route events to appropriate handlers based on event type.

    Args:
        envelope: Event envelope containing event data
        state_store: Essay state persistence layer
        event_publisher: Event publishing interface
        transition_validator: State transition validation logic
        metrics_collector: Metrics collection interface
        batch_tracker: Batch coordination and readiness tracking

    Returns:
        True if event was handled successfully, False otherwise
    """
    event_type = envelope.event_type
    correlation_id = envelope.correlation_id

    try:
        # Handle batch coordination events
        if event_type == topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED):
            return await _handle_batch_essays_registered(
                envelope=envelope,
                batch_tracker=batch_tracker,
                correlation_id=correlation_id,
            )



        elif event_type == topic_name(ProcessingEvent.ESSAY_CONTENT_PROVISIONED):
            return await _handle_essay_content_provisioned(
                envelope=envelope,
                batch_tracker=batch_tracker,
                event_publisher=event_publisher,
                state_store=state_store,
                correlation_id=correlation_id,
            )

        # Handle BOS command events
        elif event_type == topic_name(ProcessingEvent.BATCH_SPELLCHECK_INITIATE_COMMAND):
            return await _handle_batch_spellcheck_initiate_command(
                envelope=envelope,
                batch_command_handler=batch_command_handler,
                correlation_id=correlation_id,
            )

        # Handle legacy event types for backward compatibility
        elif event_type == topic_name(ProcessingEvent.ESSAY_SPELLCHECK_RESULT_RECEIVED):
            logger.info(
                "Received spellcheck result event",
                extra={"correlation_id": str(correlation_id)},
            )
            # TODO: Implement spellcheck result processing
            return True

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


async def _handle_batch_essays_registered(
    envelope: EventEnvelope[Any],
    batch_tracker: BatchEssayTracker,
    correlation_id: UUID | None,
) -> bool:
    """Handle BatchEssaysRegistered event."""
    try:
        # Deserialize event data
        event_data = BatchEssaysRegistered.model_validate(envelope.data)

        logger.info(
            "Processing BatchEssaysRegistered event",
            extra={
                "batch_id": event_data.batch_id,
                "expected_count": event_data.expected_essay_count,
                "correlation_id": str(correlation_id),
            },
        )

        # Register batch with tracker
        await batch_tracker.register_batch(event_data)

        return True

    except Exception as e:
        logger.error(
            "Error handling BatchEssaysRegistered event",
            extra={"error": str(e), "correlation_id": str(correlation_id)},
        )
        return False



async def _handle_essay_content_provisioned(
    envelope: EventEnvelope[Any],
    batch_tracker: BatchEssayTracker,
    event_publisher: EventPublisher,
    state_store: EssayStateStore,
    correlation_id: UUID | None,
) -> bool:
    """Handle EssayContentProvisionedV1 event for slot assignment."""
    try:
        # Deserialize event data
        event_data = EssayContentProvisionedV1.model_validate(envelope.data)

        logger.info(
            "Processing EssayContentProvisionedV1 event",
            extra={
                "batch_id": event_data.batch_id,
                "text_storage_id": event_data.text_storage_id,
                "original_file_name": event_data.original_file_name,
                "correlation_id": str(correlation_id),
            },
        )

        # **Step 1: Idempotency Check**
        # Check if this content has already been assigned a slot for this batch
        existing_essay = await state_store.get_essay_by_text_storage_id_and_batch_id(
            event_data.batch_id, event_data.text_storage_id
        )

        if existing_essay is not None:
            logger.warning(
                "Content already assigned to slot, acknowledging idempotently",
                extra={
                    "batch_id": event_data.batch_id,
                    "text_storage_id": event_data.text_storage_id,
                    "assigned_essay_id": existing_essay.essay_id,
                    "correlation_id": str(correlation_id),
                },
            )
            return True

        # **Step 2: Slot Assignment**
        # Try to assign an available slot to this content
        assigned_essay_id = batch_tracker.assign_slot_to_content(
            event_data.batch_id,
            event_data.text_storage_id,
            event_data.original_file_name
        )

        if assigned_essay_id is None:
            # No slots available - publish ExcessContentProvisionedV1 event
            logger.warning(
                "No available slots for content, publishing excess content event",
                extra={
                    "batch_id": event_data.batch_id,
                    "text_storage_id": event_data.text_storage_id,
                    "original_file_name": event_data.original_file_name,
                    "correlation_id": str(correlation_id),
                },
            )

            # Create ExcessContentProvisionedV1 event
            from datetime import UTC, datetime

            from common_core.events.batch_coordination_events import ExcessContentProvisionedV1

            excess_event = ExcessContentProvisionedV1(
                batch_id=event_data.batch_id,
                original_file_name=event_data.original_file_name,
                text_storage_id=event_data.text_storage_id,
                reason="NO_AVAILABLE_SLOT",
                correlation_id=correlation_id,
                timestamp=datetime.now(UTC),
            )

            await event_publisher.publish_excess_content_provisioned(
                event_data=excess_event,
                correlation_id=correlation_id,
            )

            return True

        # **Step 3: Persist Slot Assignment**
        # Create or update essay state with slot assignment
        from common_core.enums import EssayStatus

        await state_store.create_or_update_essay_state_for_slot_assignment(
            internal_essay_id=assigned_essay_id,
            batch_id=event_data.batch_id,
            text_storage_id=event_data.text_storage_id,
            original_file_name=event_data.original_file_name,
            file_size=event_data.file_size_bytes,
            content_hash=event_data.content_md5_hash,
            initial_status=EssayStatus.READY_FOR_PROCESSING,
        )

        logger.info(
            "Successfully assigned content to slot",
            extra={
                "assigned_essay_id": assigned_essay_id,
                "batch_id": event_data.batch_id,
                "text_storage_id": event_data.text_storage_id,
                "correlation_id": str(correlation_id),
            },
        )

        # **Step 4: Check Batch Completion**
        # Mark slot as fulfilled and check if batch is complete
        batch_ready_event = batch_tracker.mark_slot_fulfilled(
            event_data.batch_id,
            assigned_essay_id,
            event_data.text_storage_id
        )

        # **Step 5: Publish BatchEssaysReady if complete**
        if batch_ready_event is not None:
            logger.info(
                "Batch is complete, publishing BatchEssaysReady event",
                extra={
                    "batch_id": batch_ready_event.batch_id,
                    "ready_count": len(batch_ready_event.ready_essays),
                    "correlation_id": str(correlation_id),
                },
            )

            await event_publisher.publish_batch_essays_ready(
                event_data=batch_ready_event,
                correlation_id=correlation_id,
            )

        return True

    except Exception as e:
        logger.error(
            "Error handling EssayContentProvisionedV1 event",
            extra={"error": str(e), "correlation_id": str(correlation_id)},
        )
        return False


async def _handle_batch_spellcheck_initiate_command(
    envelope: EventEnvelope[Any],
    batch_command_handler: BatchCommandHandler,
    correlation_id: UUID | None,
) -> bool:
    """Handle BatchServiceSpellcheckInitiateCommandDataV1 command from BOS."""
    try:
        # Deserialize event data
        command_data = BatchServiceSpellcheckInitiateCommandDataV1.model_validate(envelope.data)

        logger.info(
            "Processing BOS spellcheck initiate command",
            extra={
                "batch_id": command_data.entity_ref.entity_id,
                "essays_count": len(command_data.essays_to_process),
                "language": command_data.language,
                "correlation_id": str(correlation_id),
            },
        )

        # Process command using injected BatchCommandHandler
        await batch_command_handler.process_initiate_spellcheck_command(
            command_data=command_data,
            correlation_id=correlation_id,
        )

        logger.info(
            "BOS command processed successfully",
            extra={
                "batch_id": command_data.entity_ref.entity_id,
                "correlation_id": str(correlation_id),
            },
        )

        return True

    except Exception as e:
        logger.error(
            "Error handling BatchServiceSpellcheckInitiateCommandDataV1 command",
            extra={"error": str(e), "correlation_id": str(correlation_id)},
        )
        return False

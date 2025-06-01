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
from common_core.enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.envelope import EventEnvelope
from common_core.events.file_events import EssayContentReady
from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
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

        elif event_type == topic_name(ProcessingEvent.ESSAY_CONTENT_READY):
            return await _handle_essay_content_ready(
                envelope=envelope,
                batch_tracker=batch_tracker,
                event_publisher=event_publisher,
                state_store=state_store,
                transition_validator=transition_validator,
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


async def _handle_essay_content_ready(
    envelope: EventEnvelope[Any],
    batch_tracker: BatchEssayTracker,
    event_publisher: EventPublisher,
    state_store: EssayStateStore,
    transition_validator: StateTransitionValidator,
    correlation_id: UUID | None,
) -> bool:
    """Handle EssayContentReady event."""
    try:
        # Deserialize event data
        event_data = EssayContentReady.model_validate(envelope.data)

        logger.info(
            "Processing EssayContentReady event",
            extra={
                "essay_id": event_data.essay_id,
                "batch_id": event_data.batch_id,
                "student_name": event_data.student_name,
                "student_email": event_data.student_email,
                "correlation_id": str(correlation_id),
            },
        )

        # Mark essay as ready and check if batch is complete
        batch_ready_event = await batch_tracker.mark_essay_ready(event_data)

        # TODO: Implement idempotent essay state update to READY_FOR_PROCESSING
        # This should:
        # 1. Fetch current essay state from state_store
        # 2. Use transition_validator to validate state change
        # 3. Only update if transition is valid
        # For now, we log this operation
        logger.info(
            "TODO: Update essay state to READY_FOR_PROCESSING",
            extra={
                "essay_id": event_data.essay_id,
                "correlation_id": str(correlation_id),
            },
        )

        # If batch is complete, publish BatchEssaysReady event
        if batch_ready_event:
            logger.info(
                "Batch is complete, publishing BatchEssaysReady event",
                extra={
                    "batch_id": batch_ready_event.batch_id,
                    "ready_count": batch_ready_event.total_count,
                    "correlation_id": str(correlation_id),
                },
            )
            # TODO: Publish BatchEssaysReady event using event_publisher
            # For now, we just log this operation
            logger.info(
                "TODO: Publish BatchEssaysReady event",
                extra={
                    "batch_id": batch_ready_event.batch_id,
                    "correlation_id": str(correlation_id),
                },
            )

        return True

    except Exception as e:
        logger.error(
            "Error handling EssayContentReady event",
            extra={"error": str(e), "correlation_id": str(correlation_id)},
        )
        return False

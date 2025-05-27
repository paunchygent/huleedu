"""
Event routing and processing logic for the Essay Lifecycle Service.

This module handles incoming Kafka events and orchestrates essay state transitions
using the injected dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from aiokafka import ConsumerRecord
from common_core.enums import EssayStatus
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference
from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
    EssayStateStore,
    EventPublisher,
    MetricsCollector,
    StateTransitionValidator,
)

logger = create_service_logger("event_router")


async def process_single_message(
    msg: ConsumerRecord,
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
) -> bool:
    """
    Process a single Kafka message and update essay state accordingly.

    Args:
        msg: Kafka consumer record
        state_store: Essay state persistence layer
        event_publisher: Event publishing interface
        transition_validator: State transition validation logic
        metrics_collector: Metrics collection interface

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
) -> bool:
    """Route event to appropriate handler based on event type."""
    event_type = envelope.event_type

    if event_type.startswith("essay.upload.completed"):
        return await _handle_essay_upload_completed(
            envelope, state_store, event_publisher, metrics_collector
        )
    elif event_type.startswith("essay.spellcheck.completed"):
        return await _handle_spellcheck_completed(
            envelope, state_store, event_publisher, transition_validator, metrics_collector
        )
    elif event_type.startswith("essay.nlp.completed"):
        return await _handle_nlp_completed(
            envelope, state_store, event_publisher, transition_validator, metrics_collector
        )
    elif event_type.startswith("essay.ai_feedback.completed"):
        return await _handle_ai_feedback_completed(
            envelope, state_store, event_publisher, transition_validator, metrics_collector
        )
    else:
        logger.warning(
            "Unknown event type",
            extra={"event_type": event_type, "correlation_id": str(envelope.correlation_id)},
        )
        return False


async def _handle_essay_upload_completed(
    envelope: EventEnvelope[Any],
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    metrics_collector: MetricsCollector,
) -> bool:
    """Handle essay upload completion - create initial essay record."""
    try:
        data = envelope.data
        entity_ref = EntityReference.model_validate(data["entity_ref"])

        # Create essay record
        essay_state = await state_store.create_essay_record(entity_ref)

        # Record metrics
        metrics_collector.record_state_transition("none", essay_state.current_status.value)

        # Publish status update
        await event_publisher.publish_status_update(
            entity_ref, essay_state.current_status, envelope.correlation_id
        )

        # Initiate spellcheck processing
        await event_publisher.publish_processing_request(
            "essay.spellcheck.requested.v1",
            entity_ref,
            {"text_storage_id": data.get("text_storage_id", "")},
            envelope.correlation_id,
        )

        return True

    except Exception as e:
        logger.error(
            "Error handling essay upload completed",
            extra={"error": str(e), "correlation_id": str(envelope.correlation_id)},
        )
        return False


async def _handle_spellcheck_completed(
    envelope: EventEnvelope[Any],
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
) -> bool:
    """Handle spellcheck completion."""
    try:
        data = envelope.data
        entity_ref = EntityReference.model_validate(data["entity_ref"])

        # Determine new status based on result
        if data.get("success", False):
            new_status = EssayStatus.SPELLCHECKED_SUCCESS
        else:
            new_status = EssayStatus.SPELLCHECK_FAILED

        # Get current state and validate transition
        current_state = await state_store.get_essay_state(entity_ref.entity_id)
        if current_state is None:
            logger.error(
                "Essay not found for spellcheck completion",
                extra={"essay_id": entity_ref.entity_id},
            )
            return False

        if not transition_validator.validate_transition(current_state.current_status, new_status):
            logger.error(
                "Invalid state transition for spellcheck",
                extra={
                    "from_status": current_state.current_status.value,
                    "to_status": new_status.value,
                    "essay_id": entity_ref.entity_id,
                },
            )
            return False

        # Update state
        metadata = {
            "spellcheck_corrections": data.get("corrections_count", 0),
            "corrected_text_storage_id": data.get("corrected_text_storage_id"),
        }
        await state_store.update_essay_state(entity_ref.entity_id, new_status, metadata)

        # Record metrics
        metrics_collector.record_state_transition(
            current_state.current_status.value, new_status.value
        )

        # Publish status update
        await event_publisher.publish_status_update(entity_ref, new_status, envelope.correlation_id)

        # Initiate next phase if successful
        if new_status == EssayStatus.SPELLCHECKED_SUCCESS:
            await event_publisher.publish_processing_request(
                "essay.nlp.requested.v1",
                entity_ref,
                {"text_storage_id": data.get("corrected_text_storage_id", "")},
                envelope.correlation_id,
            )

        return True

    except Exception as e:
        logger.error(
            "Error handling spellcheck completed",
            extra={"error": str(e), "correlation_id": str(envelope.correlation_id)},
        )
        return False


async def _handle_nlp_completed(
    envelope: EventEnvelope[Any],
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
) -> bool:
    """Handle NLP processing completion."""
    try:
        data = envelope.data
        entity_ref = EntityReference.model_validate(data["entity_ref"])

        # Determine new status based on result
        if data.get("success", False):
            new_status = EssayStatus.NLP_COMPLETED_SUCCESS
        else:
            new_status = EssayStatus.NLP_FAILED

        # Get current state and validate transition
        current_state = await state_store.get_essay_state(entity_ref.entity_id)
        if current_state is None:
            logger.error(
                "Essay not found for NLP completion", extra={"essay_id": entity_ref.entity_id}
            )
            return False

        if not transition_validator.validate_transition(current_state.current_status, new_status):
            logger.error(
                "Invalid state transition for NLP",
                extra={
                    "from_status": current_state.current_status.value,
                    "to_status": new_status.value,
                    "essay_id": entity_ref.entity_id,
                },
            )
            return False

        # Update state
        metadata = {
            "nlp_analysis_storage_id": data.get("analysis_storage_id"),
            "nlp_metrics": data.get("analysis_metrics", {}),
        }
        await state_store.update_essay_state(entity_ref.entity_id, new_status, metadata)

        # Record metrics
        metrics_collector.record_state_transition(
            current_state.current_status.value, new_status.value
        )

        # Publish status update
        await event_publisher.publish_status_update(entity_ref, new_status, envelope.correlation_id)

        # Initiate AI feedback if successful
        if new_status == EssayStatus.NLP_COMPLETED_SUCCESS:
            await event_publisher.publish_processing_request(
                "essay.ai_feedback.requested.v1",
                entity_ref,
                {
                    "original_text_storage_id": data.get("original_text_storage_id", ""),
                    "nlp_analysis_storage_id": data.get("analysis_storage_id", ""),
                },
                envelope.correlation_id,
            )

        return True

    except Exception as e:
        logger.error(
            "Error handling NLP completed",
            extra={"error": str(e), "correlation_id": str(envelope.correlation_id)},
        )
        return False


async def _handle_ai_feedback_completed(
    envelope: EventEnvelope[Any],
    state_store: EssayStateStore,
    event_publisher: EventPublisher,
    transition_validator: StateTransitionValidator,
    metrics_collector: MetricsCollector,
) -> bool:
    """Handle AI feedback completion."""
    try:
        data = envelope.data
        entity_ref = EntityReference.model_validate(data["entity_ref"])

        # Determine new status based on result
        if data.get("success", False):
            new_status = EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS
        else:
            new_status = EssayStatus.AI_FEEDBACK_FAILED

        # Get current state and validate transition
        current_state = await state_store.get_essay_state(entity_ref.entity_id)
        if current_state is None:
            logger.error(
                "Essay not found for AI feedback completion",
                extra={"essay_id": entity_ref.entity_id},
            )
            return False

        if not transition_validator.validate_transition(current_state.current_status, new_status):
            logger.error(
                "Invalid state transition for AI feedback",
                extra={
                    "from_status": current_state.current_status.value,
                    "to_status": new_status.value,
                    "essay_id": entity_ref.entity_id,
                },
            )
            return False

        # Update state
        metadata = {
            "ai_feedback_storage_id": data.get("feedback_storage_id"),
            "feedback_metrics": data.get("feedback_metrics", {}),
        }
        await state_store.update_essay_state(entity_ref.entity_id, new_status, metadata)

        # Record metrics
        metrics_collector.record_state_transition(
            current_state.current_status.value, new_status.value
        )

        # Check if this completes the essay processing
        if new_status == EssayStatus.AI_FEEDBACK_COMPLETED_SUCCESS:
            # For Phase 1.2, mark as completed
            final_status = EssayStatus.ESSAY_ALL_PROCESSING_COMPLETED
            await state_store.update_essay_state(entity_ref.entity_id, final_status, {})

            # Publish final status update
            await event_publisher.publish_status_update(
                entity_ref, final_status, envelope.correlation_id
            )

            # Record final transition
            metrics_collector.record_state_transition(new_status.value, final_status.value)
        else:
            # Publish status update for failed processing
            await event_publisher.publish_status_update(
                entity_ref, new_status, envelope.correlation_id
            )

        return True

    except Exception as e:
        logger.error(
            "Error handling AI feedback completed",
            extra={"error": str(e), "correlation_id": str(envelope.correlation_id)},
        )
        return False

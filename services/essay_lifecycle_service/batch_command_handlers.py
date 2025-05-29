"""
Event routing and processing logic for the Essay Lifecycle Service.

This module handles incoming Kafka events and orchestrates essay state transitions
using the injected dependencies.
"""

from __future__ import annotations

import json
from typing import Any

from aiokafka import ConsumerRecord
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger

from protocols import (
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
    """
    Route events to appropriate handlers based on event type.

    NOTE: This is a temporary stub implementation. Batch command
    handlers will be implemented in Phase 3 to process commands from Batch Service.

    Args:
        envelope: Event envelope containing event data
        state_store: Essay state persistence layer
        event_publisher: Event publishing interface
        transition_validator: State transition validation logic
        metrics_collector: Metrics collection interface

    Returns:
        True if event was handled successfully, False otherwise
    """
    event_type = envelope.event_type
    correlation_id = envelope.correlation_id

    logger.warning(
        "Event routing not yet implemented for batch-centric architecture",
        extra={
            "event_type": event_type,
            "correlation_id": str(correlation_id),
            "source_service": envelope.source_service,
            "message": "Autonomous event handlers removed. Batch command handlers will be implemented.",
        },
    )

    # TODO: Implement batch command handlers for:
    # - huleedu.batchorchestrator.spellcheck_phase.initiate.v1
    # - huleedu.batchorchestrator.nlp_phase.initiate.v1
    # - huleedu.batchorchestrator.aifeedback_phase.initiate.v1
    # - huleedu.batchorchestrator.cj_assessment_phase.initiate.v1

    # TODO: Implement specialized service result handlers for:
    # - huleedu.spellchecker.essay.concluded.v1
    # - huleedu.nlp.essay.concluded.v1
    # - huleedu.aifeedback.essay.concluded.v1

    # For now, return True to avoid blocking the consumer
    return True

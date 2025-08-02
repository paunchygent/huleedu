"""Event routing logic for the Class Management Service.

This module routes incoming Kafka events to appropriate command handlers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import ConsumerRecord
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import raise_parsing_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import trace_operation, use_trace_context
from opentelemetry import trace

from services.class_management_service.protocols import CommandHandlerProtocol

logger = create_service_logger("class_management_service.event_processor")


async def process_single_message(
    msg: ConsumerRecord,
    command_handlers: dict[str, CommandHandlerProtocol],
    http_session: aiohttp.ClientSession,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process a single Kafka message by routing to appropriate handler.

    Args:
        msg: The Kafka message to process
        command_handlers: Dictionary mapping event types to handlers
        http_session: HTTP session for external service calls
        tracer: Optional tracer for distributed tracing

    Returns:
        True if processing succeeded, False otherwise
    """
    # First, parse the message to get the envelope
    try:
        raw_message = msg.value.decode("utf-8")
        # Use standard EventEnvelope deserialization pattern
        # With the Any type fix, data field will be preserved as dict
        envelope: EventEnvelope = EventEnvelope.model_validate_json(raw_message)
    except Exception as e:
        # Use structured error handling for parsing failures
        correlation_id = uuid4()  # Generate correlation_id for parsing errors
        logger.error(
            f"Failed to parse Kafka message: {e}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id), "topic": msg.topic, "offset": msg.offset},
        )
        raise_parsing_error(
            service="class_management_service",
            operation="parse_kafka_message",
            parse_target="EventEnvelope",
            message=f"Failed to parse Kafka message: {str(e)}",
            correlation_id=correlation_id,
            topic=msg.topic,
            offset=msg.offset,
            raw_message_length=len(raw_message),
        )

    # Extract correlation_id early for error tracking
    correlation_id = envelope.correlation_id
    event_type = envelope.event_type

    logger.info(
        "Processing event",
        extra={
            "event_type": event_type,
            "correlation_id": str(correlation_id),
            "source_service": envelope.source_service,
        },
    )

    # Find the appropriate handler
    handler = None
    for _, cmd_handler in command_handlers.items():
        if await cmd_handler.can_handle(event_type):
            handler = cmd_handler
            break

    if not handler:
        logger.warning(
            "No handler found for event type",
            extra={
                "event_type": event_type,
                "correlation_id": str(correlation_id),
                "available_handlers": list(command_handlers.keys()),
            },
        )
        return False

    # Process with or without trace context
    if envelope.metadata and tracer:
        with use_trace_context(envelope.metadata):
            # Create a child span for this Kafka message processing
            with trace_operation(
                tracer,
                f"kafka.consume.{event_type}",
                {
                    "messaging.system": "kafka",
                    "messaging.destination": msg.topic,
                    "messaging.operation": "consume",
                    "kafka.partition": msg.partition,
                    "kafka.offset": msg.offset,
                    "correlation_id": str(correlation_id),
                    "event_id": str(envelope.event_id),
                    "event_type": event_type,
                },
            ) as span:
                try:
                    result = await handler.handle(
                        msg=msg,
                        envelope=envelope,
                        http_session=http_session,
                        correlation_id=correlation_id,
                        span=span,
                    )

                    if result:
                        logger.info(
                            "Event processed successfully",
                            extra={"correlation_id": str(correlation_id), "event_type": event_type},
                        )
                    else:
                        logger.error(
                            "Event processing failed",
                            extra={"correlation_id": str(correlation_id), "event_type": event_type},
                        )

                    return result

                except Exception as e:
                    # Record error to span
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
    else:
        # No parent context, process without tracing
        try:
            result = await handler.handle(
                msg=msg,
                envelope=envelope,
                http_session=http_session,
                correlation_id=correlation_id,
                span=None,
            )

            if result:
                logger.info(
                    "Event processed successfully",
                    extra={"correlation_id": str(correlation_id), "event_type": event_type},
                )
            else:
                logger.error(
                    "Event processing failed",
                    extra={"correlation_id": str(correlation_id), "event_type": event_type},
                )

            return result

        except Exception:
            # Re-raise for caller to handle
            raise

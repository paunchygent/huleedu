"""Clean message processing logic for the NLP Service.

This module contains the core message processing logic for student matching,
depending on injected protocol implementations for all external interactions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

import aiohttp
from aiokafka import ConsumerRecord
from common_core.batch_service_models import BatchServiceNLPInitiateCommandDataV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import (
    HuleEduError,
    raise_parsing_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger, log_event_processing
from huleedu_service_libs.observability import trace_operation, use_trace_context
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.protocols import KafkaPublisherProtocol
from opentelemetry import trace
from pydantic import ValidationError

from services.nlp_service.protocols import (
    ClassManagementClientProtocol,
    ContentClientProtocol,
    NlpEventPublisherProtocol,
    RosterCacheProtocol,
    StudentMatcherProtocol,
)

logger = create_service_logger("nlp_service.event_processor")


def determine_match_status(suggestions: list) -> str:
    """Determine overall match status based on suggestions.
    
    Args:
        suggestions: List of student match suggestions
        
    Returns:
        Match status: HIGH_CONFIDENCE, NEEDS_REVIEW, or NO_MATCH
    """
    if not suggestions:
        return "NO_MATCH"
    
    # Get the highest confidence score
    highest_confidence = max(s.confidence_score for s in suggestions)
    
    if highest_confidence >= 0.9:
        return "HIGH_CONFIDENCE"
    elif highest_confidence >= 0.7:
        return "NEEDS_REVIEW"
    else:
        return "NO_MATCH"


async def process_single_message(
    msg: ConsumerRecord,
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    class_management_client: ClassManagementClientProtocol,
    roster_cache: RosterCacheProtocol,
    student_matcher: StudentMatcherProtocol,
    event_publisher: NlpEventPublisherProtocol,
    outbox_repository: OutboxRepositoryProtocol,
    kafka_bus: KafkaPublisherProtocol,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process a single NLP batch initiate command message with proper trace context propagation."""
    # First, parse the message to get the envelope with structured error handling
    try:
        raw_message = msg.value.decode("utf-8")
        request_envelope = EventEnvelope[BatchServiceNLPInitiateCommandDataV1].model_validate_json(
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
            service="nlp_service",
            operation="parse_kafka_message",
            parse_target="EventEnvelope[BatchServiceNLPInitiateCommandDataV1]",
            message=f"Failed to parse Kafka message: {str(e)}",
            correlation_id=correlation_id,
            topic=msg.topic,
            offset=msg.offset,
            raw_message_length=len(raw_message),
        )

    # Extract correlation_id early - this is critical for error tracking
    correlation_id = request_envelope.correlation_id

    # If we have trace context in metadata and a tracer, use the parent context
    if request_envelope.metadata and tracer:
        with use_trace_context(request_envelope.metadata):
            # Create a child span for this Kafka message processing
            with trace_operation(
                tracer,
                "kafka.consume.nlp_initiate",
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
                        class_management_client,
                        roster_cache,
                        student_matcher,
                        event_publisher,
                        outbox_repository,
                        kafka_bus,
                        tracer,
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
                    # Convert to structured error
                    if span:
                        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
    else:
        # No parent context, process without it
        try:
            return await _process_single_message_impl(
                msg,
                request_envelope,
                http_session,
                content_client,
                class_management_client,
                roster_cache,
                student_matcher,
                event_publisher,
                outbox_repository,
                kafka_bus,
                tracer,
                None,  # No span
            )
        except HuleEduError:
            # Already structured - re-raise
            raise
        except Exception:
            # Re-raise for caller to handle
            raise


async def _process_single_message_impl(
    msg: ConsumerRecord,
    request_envelope: EventEnvelope[BatchServiceNLPInitiateCommandDataV1],
    http_session: aiohttp.ClientSession,
    content_client: ContentClientProtocol,
    class_management_client: ClassManagementClientProtocol,
    roster_cache: RosterCacheProtocol,
    student_matcher: StudentMatcherProtocol,
    event_publisher: NlpEventPublisherProtocol,
    outbox_repository: OutboxRepositoryProtocol,
    kafka_bus: KafkaPublisherProtocol,
    tracer: "Tracer | None" = None,
    span: "trace.Span | None" = None,
) -> bool:
    """Implementation of message processing logic for NLP student matching.

    Args:
        msg: The Kafka message to process
        request_envelope: Already parsed event envelope
        http_session: HTTP session for external service calls
        content_client: Client for fetching essay content
        class_management_client: Client for fetching class rosters
        roster_cache: Cache for class rosters
        student_matcher: Student matching implementation
        event_publisher: Publisher for result events
        outbox_repository: Outbox repository for reliable publishing
        kafka_bus: Kafka bus for publishing events
        tracer: Optional tracer for distributed tracing
        span: Optional span for tracing

    Returns:
        bool: True if processing succeeded, False otherwise
    """
    correlation_id = request_envelope.correlation_id
    
    try:
        request_data = request_envelope.data

        # Log about the event we received
        log_event_processing(
            logger=logger,
            message="Received NLP batch initiate command",
            envelope=request_envelope,
            current_processing_event="batch.nlp.initiate",
            essay_count=len(request_data.essays_to_process),
        )

        # Process each essay in the batch
        for essay_ref in request_data.essays_to_process:
            essay_id = essay_ref.essay_id
            
            logger.info(
                f"Step 1: Fetching content for essay {essay_id}",
                extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
            )

            # Fetch essay content
            try:
                essay_text = await content_client.fetch_content(
                    storage_id=essay_ref.text_storage_id,
                    http_session=http_session,
                    correlation_id=correlation_id,
                )
                logger.info(
                    f"Step 2: Content fetched successfully for essay {essay_id}",
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )
            except HuleEduError:
                # Already structured error from content client - re-raise
                raise
            except Exception as e:
                logger.error(
                    f"Failed to fetch content for essay {essay_id}: {e}",
                    exc_info=True,
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )
                # Continue with next essay
                continue

            if not essay_text:
                logger.warning(
                    f"Empty content for essay {essay_id}, skipping",
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )
                continue

            # Extract class_id from essay_ref - need to determine where this comes from
            # For now, assuming it's part of the metadata or we need to extract it
            # This would need to be provided in the actual implementation
            class_id = getattr(essay_ref, "class_id", None)
            
            if not class_id:
                logger.warning(
                    f"No class_id available for essay {essay_id}, skipping matching",
                    extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
                )
                # Still publish a NO_MATCH result
                await event_publisher.publish_author_match_result(
                    kafka_bus=kafka_bus,
                    essay_id=essay_id,
                    suggestions=[],
                    match_status="NO_MATCH",
                    correlation_id=correlation_id,
                )
                continue

            logger.info(
                f"Step 3: Fetching roster for class {class_id}",
                extra={"correlation_id": str(correlation_id), "essay_id": essay_id, "class_id": class_id},
            )

            # Get roster (with caching)
            roster = await roster_cache.get_roster(class_id)
            if not roster:
                # Cache miss - fetch from service
                try:
                    roster = await class_management_client.get_class_roster(
                        class_id=class_id,
                        http_session=http_session,
                        correlation_id=correlation_id,
                    )
                    # Cache the roster
                    await roster_cache.set_roster(class_id, roster)
                except HuleEduError:
                    # Already structured error - re-raise
                    raise
                except Exception as e:
                    logger.error(
                        f"Failed to fetch roster for class {class_id}: {e}",
                        exc_info=True,
                        extra={"correlation_id": str(correlation_id), "class_id": class_id},
                    )
                    # Continue with next essay
                    continue

            if not roster:
                logger.warning(
                    f"Empty roster for class {class_id}, cannot match students",
                    extra={"correlation_id": str(correlation_id), "class_id": class_id},
                )
                # Publish NO_MATCH result
                await event_publisher.publish_author_match_result(
                    kafka_bus=kafka_bus,
                    essay_id=essay_id,
                    suggestions=[],
                    match_status="NO_MATCH",
                    correlation_id=correlation_id,
                )
                continue

            logger.info(
                f"Step 4: Performing student matching for essay {essay_id}",
                extra={"correlation_id": str(correlation_id), "essay_id": essay_id},
            )

            # Perform student matching
            suggestions = await student_matcher.find_matches(
                essay_text=essay_text,
                roster=roster,
                correlation_id=correlation_id,
            )

            # Determine overall match status
            match_status = determine_match_status(suggestions)

            logger.info(
                f"Step 5: Publishing match result for essay {essay_id}",
                extra={
                    "correlation_id": str(correlation_id),
                    "essay_id": essay_id,
                    "match_status": match_status,
                    "suggestion_count": len(suggestions),
                },
            )

            # Publish result via outbox
            await event_publisher.publish_author_match_result(
                kafka_bus=kafka_bus,
                essay_id=essay_id,
                suggestions=suggestions,
                match_status=match_status,
                correlation_id=correlation_id,
            )

        logger.info(
            f"Completed processing NLP batch with {len(request_data.essays_to_process)} essays",
            extra={"correlation_id": str(correlation_id)},
        )
        return True

    except ValidationError as e:
        # Use structured error handling for validation errors
        logger.error(
            f"Invalid message format: {e.errors()}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id)},
        )
        raise_validation_error(
            service="nlp_service",
            operation="validate_message_format",
            field="message",
            message=f"Invalid message format: {str(e)}",
            correlation_id=correlation_id,
            value=str(e.errors())[:200],
            validation_errors=e.errors(),
        )

    except HuleEduError:
        # Already structured error - re-raise
        raise

    except Exception as e:
        logger.error(
            f"Unhandled error processing NLP batch: {e}",
            exc_info=True,
            extra={"correlation_id": str(correlation_id)},
        )
        # Re-raise for caller to handle
        raise

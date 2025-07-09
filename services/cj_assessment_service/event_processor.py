"""Event processing logic for CJ Assessment Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import ConsumerRecord
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import (
    inject_trace_context,
    trace_operation,
    use_trace_context,
)

from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import (
    CJAssessmentCompletedV1,
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from services.cj_assessment_service.cj_core_logic import run_cj_assessment_workflow
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.exceptions import (
    CJAssessmentError,
)
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.models_api import ErrorDetail
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

logger = create_service_logger("event_processor")


async def process_single_message(
    msg: ConsumerRecord,  # Typed msg
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    event_publisher: CJEventPublisherProtocol,
    llm_interaction: LLMInteractionProtocol,
    settings_obj: Settings,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process a single Kafka message containing CJ assessment request.

    Args:
        msg: Kafka consumer record
        database: Database access protocol implementation
        content_client: Content client protocol implementation
        event_publisher: Event publisher protocol implementation
        llm_interaction: LLM interaction protocol implementation
        settings_obj: Application settings

    Returns:
        True if message processed successfully, False otherwise
    """
    # First, parse the message to get the envelope
    try:
        envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
            msg.value.decode("utf-8"),
        )
    except Exception as e:
        # Use structured error handling for parsing failures
        error_detail = _create_parsing_error_detail(str(e), type(e).__name__)
        logger.error(
            "Failed to parse CJ assessment message",
            extra={
                "error_code": error_detail.error_code.value,
                "error_type": error_detail.details.get("exception_type"),
                "message_size": len(msg.value) if msg.value else 0,
            },
            exc_info=True,
        )
        return False

    # If we have trace context in metadata and a tracer, use the parent context
    if envelope.metadata and tracer:
        with use_trace_context(envelope.metadata):
            # Create a child span for this Kafka message processing
            with trace_operation(
                tracer,
                "kafka.consume.cj_assessment_request",
                {
                    "messaging.system": "kafka",
                    "messaging.destination": msg.topic,
                    "messaging.operation": "consume",
                    "kafka.partition": msg.partition,
                    "kafka.offset": msg.offset,
                    "correlation_id": str(envelope.correlation_id),
                    "event_id": str(envelope.event_id),
                },
            ):
                return await _process_cj_assessment_impl(
                    msg,
                    envelope,
                    database,
                    content_client,
                    event_publisher,
                    llm_interaction,
                    settings_obj,
                    tracer,
                )
    else:
        # No parent context, process without it
        return await _process_cj_assessment_impl(
            msg,
            envelope,
            database,
            content_client,
            event_publisher,
            llm_interaction,
            settings_obj,
            tracer,
        )


async def _process_cj_assessment_impl(
    msg: ConsumerRecord,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
    database: CJRepositoryProtocol,
    content_client: ContentClientProtocol,
    event_publisher: CJEventPublisherProtocol,
    llm_interaction: LLMInteractionProtocol,
    settings_obj: Settings,
    tracer: "Tracer | None" = None,
) -> bool:
    """Implementation of CJ Assessment message processing logic."""
    processing_started_at = datetime.now(UTC)

    # Get business metrics from shared module
    business_metrics = get_business_metrics()
    comparisons_metric = business_metrics.get("cj_comparisons_made")
    duration_metric = business_metrics.get("cj_assessment_duration_seconds")
    kafka_queue_latency_metric = business_metrics.get("kafka_queue_latency_seconds")

    try:
        logger.info(f"Processing CJ assessment message: {msg.topic}:{msg.partition}:{msg.offset}")

        request_event_data: ELS_CJAssessmentRequestV1 = envelope.data

        # Record queue latency metric if available
        if (
            kafka_queue_latency_metric
            and hasattr(envelope, "event_timestamp")
            and envelope.event_timestamp
        ):
            queue_latency_seconds = (
                processing_started_at - envelope.event_timestamp
            ).total_seconds()
            if queue_latency_seconds >= 0:  # Avoid negative values from clock skew
                kafka_queue_latency_metric.observe(queue_latency_seconds)
                logger.debug(
                    f"Recorded queue latency: {queue_latency_seconds:.3f}s for {msg.topic}",
                )

        # Use correlation_id from envelope
        correlation_id = envelope.correlation_id

        log_extra = {
            "correlation_id": str(correlation_id),
            "event_id": str(envelope.event_id),
            "bos_batch_id": str(request_event_data.entity_ref.entity_id),
            "essay_count": len(request_event_data.essays_for_cj),
            "language": request_event_data.language,
            "course_code": request_event_data.course_code,
        }

        logger.info("Received CJ assessment request from ELS", extra=log_extra)
        logger.info(
            f"📚 Processing {len(request_event_data.essays_for_cj)} essays for CJ assessment",
            extra=log_extra,
        )

        # Convert event data to format expected by core_assessment_logic
        essays_to_process = []
        for essay_ref in request_event_data.essays_for_cj:
            essays_to_process.append(
                {
                    "els_essay_id": essay_ref.essay_id,
                    "text_storage_id": essay_ref.text_storage_id,
                },
            )

        converted_request_data = {
            "bos_batch_id": str(request_event_data.entity_ref.entity_id),
            "essays_to_process": essays_to_process,
            "language": request_event_data.language,
            "course_code": request_event_data.course_code,
            "essay_instructions": request_event_data.essay_instructions,
            "llm_config_overrides": request_event_data.llm_config_overrides,
        }

        logger.info(
            f"Starting CJ assessment workflow for batch {converted_request_data['bos_batch_id']}",
            extra=log_extra,
        )

        # Run CJ assessment workflow with LLM interaction
        rankings, cj_job_id_ref = await run_cj_assessment_workflow(
            request_data=converted_request_data,
            correlation_id=str(correlation_id),
            database=database,
            content_client=content_client,
            llm_interaction=llm_interaction,
            event_publisher=event_publisher,
            settings=settings_obj,
        )

        logger.info(
            f"CJ assessment workflow completed for batch {converted_request_data['bos_batch_id']}",
            extra={
                **log_extra,
                "job_id": cj_job_id_ref,
                "rankings_count": len(rankings) if rankings else 0,
                "rankings_preview": rankings[:2] if rankings else [],
            },
        )

        # Record business metrics for completed assessment
        processing_ended_at = datetime.now(UTC)
        processing_duration = (processing_ended_at - processing_started_at).total_seconds()

        if duration_metric:
            duration_metric.observe(processing_duration)
            logger.debug(
                f"Recorded assessment duration: {processing_duration:.2f}s for batch "
                f"{converted_request_data['bos_batch_id']}",
                extra=log_extra,
            )

        # Record comparisons made (estimated from rankings count)
        if comparisons_metric and rankings:
            # CJ assessments typically require n(n-1)/2 comparisons for n essays
            estimated_comparisons = len(rankings) * (len(rankings) - 1) // 2
            comparisons_metric.observe(estimated_comparisons)
            logger.debug(
                f"Recorded estimated comparisons: {estimated_comparisons} for batch "
                f"{converted_request_data['bos_batch_id']}",
                extra=log_extra,
            )

        # Construct and publish CJAssessmentCompletedV1 event
        completed_event_data = CJAssessmentCompletedV1(
            event_name=ProcessingEvent.CJ_ASSESSMENT_COMPLETED,
            entity_ref=request_event_data.entity_ref,  # Propagate original batch reference
            status=BatchStatus.COMPLETED_SUCCESSFULLY,
            system_metadata=SystemProcessingMetadata(  # New metadata for *this* completion event
                entity=request_event_data.entity_ref,
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.COMPLETED,
                event=ProcessingEvent.CJ_ASSESSMENT_COMPLETED.value,
            ),
            cj_assessment_job_id=cj_job_id_ref,
            rankings=rankings,
        )

        # The envelope for the outgoing event
        correlation_uuid = correlation_id
        completed_envelope = EventEnvelope[CJAssessmentCompletedV1](
            event_type=settings_obj.CJ_ASSESSMENT_COMPLETED_TOPIC,
            source_service=settings_obj.SERVICE_NAME,
            correlation_id=correlation_uuid,
            data=completed_event_data,
            metadata={},
        )

        if completed_envelope.metadata is not None:
            inject_trace_context(completed_envelope.metadata)

        logger.info(
            (
                f"📤 Publishing CJ assessment completion event for batch "
                f"{converted_request_data['bos_batch_id']}"
            ),
            extra={
                **log_extra,
                "completion_topic": settings_obj.CJ_ASSESSMENT_COMPLETED_TOPIC,
                "job_id": cj_job_id_ref,
                "rankings_count": len(rankings) if rankings else 0,
            },
        )

        await event_publisher.publish_assessment_completed(
            completion_data=completed_envelope,
            correlation_id=completed_envelope.correlation_id,
        )

        logger.info(
            "CJ assessment message processed successfully and completion event published.",
            extra=log_extra,
        )
        return True

    except Exception as e:
        # Use structured error handling for processing failures
        error_detail = _categorize_processing_error(e)

        # Try to extract correlation_id if available
        try:
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
            error_detail.correlation_id = envelope.correlation_id
        except:
            pass  # correlation_id remains None if envelope parsing fails

        # Publish failure event
        try:
            # Re-deserialize for failure handling if needed
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
            request_event_data = envelope.data
            correlation_id = envelope.correlation_id

            logger.error(
                "Error processing CJ assessment message",
                extra={
                    "error_code": error_detail.error_code.value,
                    "correlation_id": str(correlation_id),
                    "error_type": error_detail.details.get("exception_type"),
                    "entity_ref": request_event_data.entity_ref,
                },
                exc_info=True,
            )

            # Create structured error info for the event
            structured_error_info = {
                "error_code": error_detail.error_code.value,
                "error_message": error_detail.message,
                "correlation_id": str(error_detail.correlation_id),
                "timestamp": error_detail.timestamp.isoformat(),
                "service": error_detail.service,
                "details": error_detail.details,
            }

            failed_event_data = CJAssessmentFailedV1(
                event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                entity_ref=request_event_data.entity_ref,
                status=BatchStatus.FAILED_CRITICALLY,
                system_metadata=SystemProcessingMetadata(
                    entity=request_event_data.entity_ref,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.FAILED,
                    event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                    error_info=structured_error_info,
                ),
                cj_assessment_job_id=ErrorCode.INITIALIZATION_FAILED.value,  # No CJ job created due to failure
            )

            correlation_uuid = correlation_id
            failed_envelope = EventEnvelope[CJAssessmentFailedV1](
                event_type=settings_obj.CJ_ASSESSMENT_FAILED_TOPIC,
                source_service=settings_obj.SERVICE_NAME,
                correlation_id=correlation_uuid,
                data=failed_event_data,
                metadata={},
            )

            if failed_envelope.metadata is not None:
                inject_trace_context(failed_envelope.metadata)

            await event_publisher.publish_assessment_failed(
                failure_data=failed_envelope,
                correlation_id=failed_envelope.correlation_id,
            )
        except Exception as publish_error:
            # Use structured error handling for publishing failures
            publishing_error_detail = _create_publishing_error_detail(publish_error, correlation_id)
            logger.error(
                "Failed to publish failure event",
                extra={
                    "error_code": publishing_error_detail.error_code.value,
                    "correlation_id": str(correlation_id)
                    if "correlation_id" in locals()
                    else "unknown",
                    "original_error_type": error_detail.details.get("exception_type"),
                    "publishing_error_type": type(publish_error).__name__,
                },
            )

        return False  # Don't commit failed messages


# Helper functions for structured error handling


def _create_parsing_error_detail(error_message: str, exception_type: str) -> ErrorDetail:
    """Create structured error detail for message parsing failures."""
    return ErrorDetail(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"Failed to parse CJ assessment message: {error_message}",
        correlation_id=uuid4(),  # Generate correlation_id for parsing stage
        timestamp=datetime.now(UTC),
        details={
            "exception_type": exception_type,
            "parsing_stage": "event_envelope",
        },
    )


def _categorize_processing_error(exception: Exception) -> ErrorDetail:
    """Categorize processing exceptions into appropriate ErrorCode types."""
    if isinstance(exception, CJAssessmentError):
        # Already a structured CJ Assessment error
        return ErrorDetail(
            error_code=exception.error_code,
            message=exception.message,
            correlation_id=exception.correlation_id or uuid4(),
            timestamp=exception.timestamp,
            details=exception.details,
        )

    # Categorize based on exception type
    if "timeout" in str(exception).lower() or "TimeoutError" in type(exception).__name__:
        error_code = ErrorCode.TIMEOUT
    elif "connection" in str(exception).lower() or "ConnectionError" in type(exception).__name__:
        error_code = ErrorCode.CONNECTION_ERROR
    elif "validation" in str(exception).lower() or "ValidationError" in type(exception).__name__:
        error_code = ErrorCode.VALIDATION_ERROR
    elif "not found" in str(exception).lower() or "NotFound" in type(exception).__name__:
        error_code = ErrorCode.RESOURCE_NOT_FOUND
    else:
        error_code = ErrorCode.PROCESSING_ERROR

    return ErrorDetail(
        error_code=error_code,
        message=f"CJ assessment processing failed: {str(exception)}",
        correlation_id=uuid4(),  # Generate correlation_id for generic processing error
        timestamp=datetime.now(UTC),
        details={
            "exception_type": type(exception).__name__,
            "processing_stage": "cj_assessment_workflow",
        },
    )


def _create_publishing_error_detail(exception: Exception, correlation_id=None) -> ErrorDetail:
    """Create structured error detail for event publishing failures."""
    return ErrorDetail(
        error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
        message=f"Failed to publish failure event: {str(exception)}",
        correlation_id=correlation_id,
        timestamp=datetime.now(UTC),
        details={
            "exception_type": type(exception).__name__,
            "publishing_stage": "assessment_failed_event",
        },
    )

"""Event processing logic for CJ Assessment Service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.event_enums import ProcessingEvent
from common_core.events.cj_assessment_events import (
    CJAssessmentFailedV1,
    ELS_CJAssessmentRequestV1,
)
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from common_core.metadata_models import SystemProcessingMetadata
from common_core.models.error_models import ErrorDetail
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import (
    inject_trace_context,
    trace_operation,
    use_trace_context,
)

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.cj_core_logic.workflow_orchestrator import (
    run_cj_assessment_workflow,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.protocols import (
    CJEventPublisherProtocol,
    CJRepositoryProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
)

logger = create_service_logger("event_processor")


async def publish_assessment_completion(
    workflow_result: Any,  # CJAssessmentWorkflowResult
    grade_projections: Any,  # GradeProjectionSummary
    request_event_data: ELS_CJAssessmentRequestV1,
    settings: Settings,
    event_publisher: CJEventPublisherProtocol,
    correlation_id: UUID,
    processing_started_at: datetime,
) -> None:
    """Publish dual events: thin to ELS, rich to RAS using centralized function.

    This wrapper maintains the existing interface while delegating to the
    centralized dual event publisher for consistency.
    """

    # Create publishing data from request event
    publishing_data = DualEventPublishingData(
        bos_batch_id=str(request_event_data.entity_id),
        cj_batch_id=str(workflow_result.batch_id),
        assignment_id=request_event_data.assignment_id,
        course_code=request_event_data.course_code,
        user_id=request_event_data.user_id,  # Identity from event
        org_id=request_event_data.org_id,    # Identity from event
        created_at=processing_started_at,
    )

    # Use centralized dual event publishing function
    await publish_dual_assessment_events(
        rankings=workflow_result.rankings,
        grade_projections=grade_projections,
        publishing_data=publishing_data,  # Pass DTO instead of adapter
        event_publisher=event_publisher,
        settings=settings,
        correlation_id=correlation_id,
        processing_started_at=processing_started_at,
    )


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

        request_event_data: ELS_CJAssessmentRequestV1 = ELS_CJAssessmentRequestV1.model_validate(
            envelope.data
        )

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
            "bos_batch_id": str(request_event_data.entity_id),
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
            "bos_batch_id": str(request_event_data.entity_id),
            "essays_to_process": essays_to_process,
            "language": request_event_data.language,
            "course_code": request_event_data.course_code,
            "essay_instructions": request_event_data.essay_instructions,
            "llm_config_overrides": request_event_data.llm_config_overrides,
            # Identity fields for credit attribution (Phase 3: Entitlements integration)
            "user_id": request_event_data.user_id,
            "org_id": request_event_data.org_id,
        }

        logger.info(
            f"Starting CJ assessment workflow for batch {converted_request_data['bos_batch_id']}",
            extra=log_extra,
        )

        # Run CJ assessment workflow with LLM interaction
        workflow_result = await run_cj_assessment_workflow(
            request_data=converted_request_data,
            correlation_id=correlation_id,
            database=database,
            content_client=content_client,
            llm_interaction=llm_interaction,
            event_publisher=event_publisher,
            settings=settings_obj,
        )

        # ALL workflows are async - comparisons submitted, results come via callbacks
        # The workflow_result.rankings will ALWAYS be empty at this point
        logger.info(
            f"CJ assessment batch {converted_request_data['bos_batch_id']} "
            f"submitted for async processing. "
            "Results will be published when LLM callbacks complete.",
            extra={
                **log_extra,
                "job_id": workflow_result.batch_id,
                "async_processing": True,
            },
        )

        # Record initial metrics (submission time)
        processing_ended_at = datetime.now(UTC)
        submission_duration = (processing_ended_at - processing_started_at).total_seconds()

        if duration_metric:
            duration_metric.observe(submission_duration)
            logger.debug(
                f"Recorded submission duration: {submission_duration:.2f}s for batch "
                f"{converted_request_data['bos_batch_id']}",
                extra=log_extra,
            )

        logger.info(
            "CJ assessment message processed successfully - awaiting LLM callbacks.",
            extra=log_extra,
        )
        return True

    except Exception as e:
        # Try to extract correlation_id if available for better error tracking
        correlation_id_for_error = None
        try:
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
            correlation_id_for_error = envelope.correlation_id
        except Exception:
            correlation_id_for_error = uuid4()  # Generate new correlation_id if parsing fails

        # Use structured error handling for processing failures
        error_detail = _categorize_processing_error(e, correlation_id_for_error)

        # Publish failure event
        try:
            # Re-deserialize for failure handling if needed
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
            request_event_data = ELS_CJAssessmentRequestV1.model_validate(envelope.data)
            correlation_id = envelope.correlation_id

            logger.error(
                "Error processing CJ assessment message",
                extra={
                    "error_code": error_detail.error_code.value,
                    "correlation_id": str(correlation_id),
                    "error_type": error_detail.details.get("exception_type"),
                    "entity_id": request_event_data.entity_id,
                    "entity_type": request_event_data.entity_type,
                    "parent_id": request_event_data.parent_id,
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
                entity_id=request_event_data.entity_id,
                entity_type=request_event_data.entity_type,
                parent_id=request_event_data.parent_id,
                status=BatchStatus.FAILED_CRITICALLY,
                system_metadata=SystemProcessingMetadata(
                    entity_id=request_event_data.entity_id,
                    entity_type=request_event_data.entity_type,
                    parent_id=request_event_data.parent_id,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.FAILED,
                    event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                    error_info=structured_error_info,
                ),
                cj_assessment_job_id=ErrorCode.INITIALIZATION_FAILED.value,
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
    return create_error_detail_with_context(
        error_code=ErrorCode.PARSING_ERROR,
        message=f"Failed to parse CJ assessment message: {error_message}",
        service="cj_assessment_service",
        operation="parse_kafka_message",
        correlation_id=uuid4(),  # Generate correlation_id for parsing stage
        details={
            "exception_type": exception_type,
            "parsing_stage": "event_envelope",
        },
    )


def _categorize_processing_error(
    exception: Exception, correlation_id: UUID | None = None
) -> ErrorDetail:
    """Categorize processing exceptions into appropriate ErrorCode types."""
    if isinstance(exception, HuleEduError):
        # Already a structured HuleEdu error - return the error detail directly
        return exception.error_detail

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

    return create_error_detail_with_context(
        error_code=error_code,
        message=f"CJ assessment processing failed: {str(exception)}",
        service="cj_assessment_service",
        operation="categorize_processing_error",
        correlation_id=correlation_id or uuid4(),  # Use provided correlation_id or generate new one
        details={
            "exception_type": type(exception).__name__,
            "processing_stage": "cj_assessment_workflow",
        },
    )


def _create_publishing_error_detail(
    exception: Exception, correlation_id: UUID | None = None
) -> ErrorDetail:
    """Create structured error detail for event publishing failures."""
    return create_error_detail_with_context(
        error_code=ErrorCode.KAFKA_PUBLISH_ERROR,
        message=f"Failed to publish failure event: {str(exception)}",
        service="cj_assessment_service",
        operation="publish_failure_event",
        correlation_id=correlation_id or uuid4(),
        details={
            "exception_type": type(exception).__name__,
            "publishing_stage": "assessment_failed_event",
        },
    )


async def process_llm_result(
    msg: ConsumerRecord,
    database: CJRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    content_client: ContentClientProtocol,
    settings_obj: Settings,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process LLM comparison result callback from LLM Provider Service.

    Args:
        msg: Kafka consumer record containing LLM comparison result
        database: Database access protocol implementation
        event_publisher: Event publisher protocol implementation
        content_client: Content client for fetching anchor essays
        settings_obj: Application settings
        tracer: Optional OpenTelemetry tracer for distributed tracing

    Returns:
        True to acknowledge message (even on errors to prevent reprocessing)
    """
    processing_started_at = datetime.now(UTC)

    # Get business metrics from shared module
    business_metrics = get_business_metrics()
    callback_latency_metric = business_metrics.get("cj_callback_latency_seconds")
    callbacks_processed_metric = business_metrics.get("cj_callbacks_processed_total")
    callback_duration_metric = business_metrics.get("cj_callback_processing_duration_seconds")

    try:
        # Parse the message to get the envelope
        envelope = EventEnvelope[LLMComparisonResultV1].model_validate_json(
            msg.value.decode("utf-8"),
        )

        # Calculate callback latency
        callback_latency = (processing_started_at - envelope.event_timestamp).total_seconds()

        # Extract the comparison result data
        comparison_result: LLMComparisonResultV1 = LLMComparisonResultV1.model_validate(
            envelope.data
        )

        log_extra = {
            "correlation_id": str(envelope.correlation_id),
            "event_id": str(envelope.event_id),
            "request_id": comparison_result.request_id,
            "provider": comparison_result.provider.value,
            "model": comparison_result.model,
            "is_error": comparison_result.is_error,
            "callback_latency_seconds": callback_latency,
        }

        logger.info(
            f"Processing LLM comparison callback for request {comparison_result.request_id}",
            extra=log_extra,
        )

        # Record callback latency metric if available
        if (
            callback_latency_metric and callback_latency >= 0
        ):  # Avoid negative values from clock skew
            callback_latency_metric.observe(callback_latency)
            logger.debug(
                f"Recorded callback latency: {callback_latency:.3f}s for "
                f"request {comparison_result.request_id}",
                extra=log_extra,
            )

        # Check if this is an error callback
        if comparison_result.is_error and comparison_result.error_detail:
            logger.warning(
                f"Received error callback for request {comparison_result.request_id}",
                extra={
                    **log_extra,
                    "error_code": comparison_result.error_detail.error_code.value,
                    "error_message": comparison_result.error_detail.message,
                    "error_details": comparison_result.error_detail.details,
                },
            )
        else:
            # Log success callback details
            logger.info(
                f"Received successful comparison result for request {comparison_result.request_id}",
                extra={
                    **log_extra,
                    "winner": comparison_result.winner.value if comparison_result.winner else None,
                    "confidence": comparison_result.confidence,
                    "response_time_ms": comparison_result.response_time_ms,
                    "total_tokens": comparison_result.token_usage.total_tokens,
                    "cost_estimate": comparison_result.cost_estimate,
                },
            )

        # If we have trace context in metadata and a tracer, use the parent context
        if envelope.metadata and tracer:
            with use_trace_context(envelope.metadata):
                # Create a child span for this callback processing
                with trace_operation(
                    tracer,
                    "kafka.consume.llm_comparison_result",
                    {
                        "messaging.system": "kafka",
                        "messaging.destination": msg.topic,
                        "messaging.operation": "consume",
                        "kafka.partition": msg.partition,
                        "kafka.offset": msg.offset,
                        "correlation_id": str(envelope.correlation_id),
                        "event_id": str(envelope.event_id),
                        "request_id": comparison_result.request_id,
                        "is_error": comparison_result.is_error,
                    },
                ):
                    from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (  # noqa: E501
                        continue_cj_assessment_workflow,
                    )

                    await continue_cj_assessment_workflow(
                        comparison_result=comparison_result,
                        correlation_id=envelope.correlation_id,
                        database=database,
                        event_publisher=event_publisher,
                        settings=settings_obj,
                        content_client=content_client,
                    )
        else:
            # No parent context, process without it
            from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (
                continue_cj_assessment_workflow,
            )

            await continue_cj_assessment_workflow(
                comparison_result=comparison_result,
                correlation_id=envelope.correlation_id,
                database=database,
                event_publisher=event_publisher,
                settings=settings_obj,
                content_client=content_client,
            )

        # Record callback processing metrics
        processing_duration = (datetime.now(UTC) - processing_started_at).total_seconds()

        if callbacks_processed_metric:
            callbacks_processed_metric.labels(status="success").inc()

        if callback_duration_metric:
            callback_duration_metric.observe(processing_duration)

        logger.info(
            "Successfully processed LLM comparison callback",
            extra={
                **log_extra,
                "request_id": comparison_result.request_id,
                "processing_duration_ms": int(processing_duration * 1000),
            },
        )

        # Always return True to acknowledge the message
        return True

    except Exception as e:
        # Log the error but still return True to prevent message reprocessing
        error_detail = create_error_detail_with_context(
            error_code=ErrorCode.PROCESSING_ERROR,
            message=f"Failed to process LLM comparison callback: {str(e)}",
            service="cj_assessment_service",
            operation="process_llm_result",
            correlation_id=uuid4(),
            details={
                "exception_type": type(e).__name__,
                "message_topic": msg.topic,
                "message_offset": msg.offset,
                "message_partition": msg.partition,
            },
        )

        logger.error(
            "Error processing LLM comparison callback message",
            extra={
                "error_code": error_detail.error_code.value,
                "error_type": error_detail.details.get("exception_type"),
                "message_size": len(msg.value) if msg.value else 0,
            },
            exc_info=True,
        )

        # Still increment the processed counter even for errors
        if callbacks_processed_metric:
            callbacks_processed_metric.labels(status="error").inc()

        # Return True to acknowledge and prevent reprocessing of error messages
        return True

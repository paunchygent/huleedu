"""LLM Comparison Result Callback Handler.

Handles incoming LLM comparison result callbacks from LLM Provider Service,
processing both successful comparisons and error callbacks.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import ConsumerRecord
from common_core.error_enums import ErrorCode
from common_core.events.envelope import EventEnvelope
from common_core.events.llm_provider_events import LLMComparisonResultV1
from huleedu_service_libs.error_handling.error_detail_factory import (
    create_error_detail_with_context,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import trace_operation, use_trace_context

from services.cj_assessment_service.cj_core_logic.batch_callback_handler import (
    continue_cj_assessment_workflow,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
from services.cj_assessment_service.protocols import (
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment.llm_callback_handler")


async def handle_llm_comparison_callback(
    msg: ConsumerRecord,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    content_client: ContentClientProtocol,
    llm_interaction: LLMInteractionProtocol,
    settings: Settings,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    grade_projector: GradeProjector,
    tracer: "Tracer | None" = None,
) -> bool:
    """Handle LLM comparison result callback from LLM Provider Service.

    Args:
        msg: Kafka consumer record containing LLM comparison result
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch operations
        essay_repository: Essay repository for essay operations
        comparison_repository: Comparison repository for comparison operations
        event_publisher: Event publisher protocol
        content_client: Content client for fetching anchor essays
        llm_interaction: LLM interaction protocol
        settings: Application settings
        instruction_repository: Instruction repository for assessment instructions
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

        # Process callback with or without trace context
        if envelope.metadata and tracer:
            with use_trace_context(envelope.metadata):
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
                    await continue_cj_assessment_workflow(
                        comparison_result=comparison_result,
                        correlation_id=envelope.correlation_id,
                        session_provider=session_provider,
                        batch_repository=batch_repository,
                        essay_repository=essay_repository,
                        comparison_repository=comparison_repository,
                        event_publisher=event_publisher,
                        settings=settings,
                        content_client=content_client,
                        llm_interaction=llm_interaction,
                        instruction_repository=instruction_repository,
                        grade_projector=grade_projector,
                    )
        else:
            # No parent context, process without it
            await continue_cj_assessment_workflow(
                comparison_result=comparison_result,
                correlation_id=envelope.correlation_id,
                session_provider=session_provider,
                batch_repository=batch_repository,
                essay_repository=essay_repository,
                comparison_repository=comparison_repository,
                event_publisher=event_publisher,
                settings=settings,
                content_client=content_client,
                llm_interaction=llm_interaction,
                instruction_repository=instruction_repository,
                grade_projector=grade_projector,
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

"""Event processing logic for CJ Assessment Service.

This module provides thin routing for Kafka messages, delegating to specialized
handlers for different message types.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

if TYPE_CHECKING:
    from opentelemetry.trace import Tracer

from aiokafka import ConsumerRecord
from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import trace_operation, use_trace_context

from services.cj_assessment_service.cj_core_logic.dual_event_publisher import (
    DualEventPublishingData,
    publish_dual_assessment_events,
)
from services.cj_assessment_service.cj_core_logic.error_categorization import (
    create_parsing_error_detail,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.message_handlers.cj_request_handler import (
    handle_cj_assessment_request,
)
from services.cj_assessment_service.message_handlers.llm_callback_handler import (
    handle_llm_comparison_callback,
)
from services.cj_assessment_service.protocols import (
    AnchorRepositoryProtocol,
    AssessmentInstructionRepositoryProtocol,
    CJBatchRepositoryProtocol,
    CJComparisonRepositoryProtocol,
    CJEssayRepositoryProtocol,
    CJEventPublisherProtocol,
    ContentClientProtocol,
    LLMInteractionProtocol,
    PairMatchingStrategyProtocol,
    SessionProviderProtocol,
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
        org_id=request_event_data.org_id,  # Identity from event
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
    msg: ConsumerRecord,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    anchor_repository: AnchorRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    content_client: ContentClientProtocol,
    event_publisher: CJEventPublisherProtocol,
    llm_interaction: LLMInteractionProtocol,
    matching_strategy: PairMatchingStrategyProtocol,
    settings_obj: Settings,
    grade_projector: GradeProjector,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process a single Kafka message containing CJ assessment request.

    Routes the message to the appropriate handler after parsing and setting up
    distributed tracing context.

    Args:
        msg: Kafka consumer record
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch-level operations
        essay_repository: Essay repository for essay operations
        instruction_repository: Instruction repository for assessment instructions
        anchor_repository: Anchor repository for anchor essay management
        comparison_repository: Comparison repository for comparison pair operations
        content_client: Content client protocol
        event_publisher: Event publisher protocol
        llm_interaction: LLM interaction protocol
        matching_strategy: DI-injected strategy for computing optimal pairs
        settings_obj: Application settings
        tracer: Optional OpenTelemetry tracer

    Returns:
        True if message processed successfully, False otherwise
    """
    # Parse the message to get the envelope
    try:
        envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
            msg.value.decode("utf-8"),
        )
    except Exception as e:
        # Use structured error handling for parsing failures
        error_detail = create_parsing_error_detail(str(e), type(e).__name__)
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

    # Route to handler with or without trace context
    if envelope.metadata and tracer:
        with use_trace_context(envelope.metadata):
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
                return await handle_cj_assessment_request(
                    msg,
                    envelope,
                    session_provider,
                    batch_repository,
                    essay_repository,
                    instruction_repository,
                    anchor_repository,
                    comparison_repository,
                    content_client,
                    event_publisher,
                    llm_interaction,
                    matching_strategy,
                    settings_obj,
                    grade_projector,
                    tracer,
                )
    else:
        # No parent context, process without it
        return await handle_cj_assessment_request(
            msg,
            envelope,
            session_provider,
            batch_repository,
            essay_repository,
            instruction_repository,
            anchor_repository,
            comparison_repository,
            content_client,
            event_publisher,
            llm_interaction,
            matching_strategy,
            settings_obj,
            grade_projector,
            tracer,
        )


async def process_llm_result(
    msg: ConsumerRecord,
    session_provider: SessionProviderProtocol,
    batch_repository: CJBatchRepositoryProtocol,
    essay_repository: CJEssayRepositoryProtocol,
    comparison_repository: CJComparisonRepositoryProtocol,
    event_publisher: CJEventPublisherProtocol,
    content_client: ContentClientProtocol,
    llm_interaction: LLMInteractionProtocol,
    matching_strategy: PairMatchingStrategyProtocol,
    settings_obj: Settings,
    instruction_repository: AssessmentInstructionRepositoryProtocol,
    grade_projector: GradeProjector,
    tracer: "Tracer | None" = None,
) -> bool:
    """Process LLM comparison result callback from LLM Provider Service.

    Routes the callback message to the specialized LLM callback handler.

    Args:
        msg: Kafka consumer record containing LLM comparison result
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch operations
        essay_repository: Essay repository for essay operations
        comparison_repository: Comparison repository for comparison operations
        event_publisher: Event publisher protocol
        content_client: Content client for fetching anchor essays
        llm_interaction: LLM interaction protocol
        matching_strategy: DI-injected strategy for computing optimal pairs
        settings_obj: Application settings
        instruction_repository: Instruction repository for assessment instructions
        tracer: Optional OpenTelemetry tracer

    Returns:
        True to acknowledge message (even on errors to prevent reprocessing)
    """
    return await handle_llm_comparison_callback(
        msg,
        session_provider,
        batch_repository,
        essay_repository,
        comparison_repository,
        event_publisher,
        content_client,
        llm_interaction,
        matching_strategy,
        settings_obj,
        instruction_repository,
        grade_projector,
        tracer,
    )

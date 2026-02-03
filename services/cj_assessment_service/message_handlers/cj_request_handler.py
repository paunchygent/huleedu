"""CJ Assessment Request Message Handler.

Handles incoming CJ assessment request messages from ELS, orchestrating content
hydration, request transformation, and workflow execution.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

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
from common_core.metadata_models import SystemProcessingMetadata
from common_core.status_enums import BatchStatus, ProcessingStage
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.cj_assessment_service.cj_core_logic.content_hydration import (
    extract_prompt_storage_id,
    hydrate_prompt_text,
)
from services.cj_assessment_service.cj_core_logic.error_categorization import (
    categorize_processing_error,
    create_publishing_error_detail,
)
from services.cj_assessment_service.cj_core_logic.grade_projector import GradeProjector
from services.cj_assessment_service.cj_core_logic.request_transformer import (
    transform_cj_assessment_request,
)
from services.cj_assessment_service.cj_core_logic.workflow_orchestrator import (
    run_cj_assessment_workflow,
)
from services.cj_assessment_service.config import Settings
from services.cj_assessment_service.metrics import get_business_metrics
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
    PairOrientationStrategyProtocol,
    SessionProviderProtocol,
)

logger = create_service_logger("cj_assessment.cj_request_handler")


async def handle_cj_assessment_request(
    msg: ConsumerRecord,
    envelope: EventEnvelope[ELS_CJAssessmentRequestV1],
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
    settings: Settings,
    grade_projector: GradeProjector,
    orientation_strategy: PairOrientationStrategyProtocol,
    tracer: "Tracer | None" = None,
) -> bool:
    """Handle CJ assessment request message from ELS.

    Args:
        msg: Kafka consumer record (for logging)
        envelope: Parsed event envelope with CJ assessment request
        session_provider: Session provider for database transactions
        batch_repository: Batch repository for batch-level operations
        essay_repository: Essay repository for essay operations
        instruction_repository: Instruction repository for assessment instructions
        anchor_repository: Anchor repository for anchor essay management
        comparison_repository: Comparison repository for comparison pair operations
        content_client: Content client for fetching prompts/rubrics
        event_publisher: Event publisher for success/failure events
        llm_interaction: LLM interaction protocol
        matching_strategy: DI-injected strategy for computing optimal pairs
        settings: Application settings
        grade_projector: Grade projector for grade predictions
        orientation_strategy: DI-injected strategy for deciding A/B orientation
        tracer: Optional OpenTelemetry tracer

    Returns:
        True if processed successfully, False otherwise
    """
    processing_started_at = datetime.now(UTC)

    # Get business metrics from shared module
    business_metrics = get_business_metrics()
    duration_metric = business_metrics.get("cj_assessment_duration_seconds")
    kafka_queue_latency_metric = business_metrics.get("kafka_queue_latency_seconds")
    prompt_failure_metric = business_metrics.get("prompt_fetch_failures")
    prompt_success_metric = business_metrics.get("prompt_fetch_success")

    try:
        logger.info(f"Processing CJ assessment message: {msg.topic}:{msg.partition}:{msg.offset}")

        request_event_data: ELS_CJAssessmentRequestV1 = ELS_CJAssessmentRequestV1.model_validate(
            envelope.data
        )

        prompt_storage_id: str | None = None
        prompt_text: str | None = None
        judge_rubric_storage_id: str | None = None
        judge_rubric_text: str | None = None

        # Assignment-scoped requests must not accept event-level prompt/rubric inputs.
        # Prompt/rubric hydration is handled downstream via assessment_instructions.
        if request_event_data.assignment_id is None:
            prompt_storage_id = extract_prompt_storage_id(
                request_event_data.student_prompt_ref,
                correlation_id=envelope.correlation_id,
                log_extra={
                    "event_id": str(envelope.event_id),
                    "bos_batch_id": str(request_event_data.entity_id),
                },
                prompt_failure_metric=prompt_failure_metric,
            )

            prompt_result = await hydrate_prompt_text(
                storage_id=prompt_storage_id,
                content_client=content_client,
                correlation_id=envelope.correlation_id,
                log_extra={
                    "event_id": str(envelope.event_id),
                    "bos_batch_id": str(request_event_data.entity_id),
                },
                prompt_failure_metric=prompt_failure_metric,
            )

            if prompt_result.is_ok:
                hydrated_prompt = prompt_result.value
                prompt_text = hydrated_prompt or None
                if prompt_text and prompt_success_metric:
                    try:
                        prompt_success_metric.inc()
                    except Exception:  # pragma: no cover - defensive
                        logger.debug("Unable to increment prompt success metric", exc_info=True)
            else:
                prompt_text = None

            # Guest runs do not hydrate assignment-owned judge rubrics here; rely on overrides.
            judge_rubric_storage_id, judge_rubric_text = None, None

        # Build log context
        log_extra: dict[str, Any] = {
            "correlation_id": str(envelope.correlation_id),
            "event_id": str(envelope.event_id),
            "bos_batch_id": str(request_event_data.entity_id),
        }
        if prompt_storage_id:
            log_extra["prompt_storage_id"] = prompt_storage_id
        if judge_rubric_storage_id:
            log_extra["judge_rubric_storage_id"] = judge_rubric_storage_id

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

        correlation_id = envelope.correlation_id

        log_extra.update(
            {
                "essay_count": len(request_event_data.essays_for_cj),
                "language": request_event_data.language,
                "course_code": request_event_data.course_code,
            }
        )

        logger.info("Received CJ assessment request from ELS", extra=log_extra)
        logger.info(
            f"📚 Processing {len(request_event_data.essays_for_cj)} essays for CJ assessment",
            extra=log_extra,
        )

        # Transform event data to internal request model
        converted_request_data = transform_cj_assessment_request(
            request_event_data,
            prompt_text=prompt_text,
            prompt_storage_id=prompt_storage_id,
            judge_rubric_text=judge_rubric_text,
            judge_rubric_storage_id=judge_rubric_storage_id,
            metadata_payload=envelope.metadata,
        )

        logger.info(
            f"Starting CJ assessment workflow for batch {converted_request_data.bos_batch_id}",
            extra=log_extra,
        )

        # Run CJ assessment workflow
        workflow_result = await run_cj_assessment_workflow(
            request_data=converted_request_data,
            correlation_id=correlation_id,
            session_provider=session_provider,
            batch_repository=batch_repository,
            essay_repository=essay_repository,
            instruction_repository=instruction_repository,
            anchor_repository=anchor_repository,
            comparison_repository=comparison_repository,
            content_client=content_client,
            llm_interaction=llm_interaction,
            matching_strategy=matching_strategy,
            event_publisher=event_publisher,
            settings=settings,
            grade_projector=grade_projector,
            orientation_strategy=orientation_strategy,
        )

        # ALL workflows are async - comparisons submitted, results come via callbacks
        logger.info(
            f"CJ assessment batch {converted_request_data.bos_batch_id} "
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
                f"{converted_request_data.bos_batch_id}",
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
            correlation_id_for_error = uuid4()

        # Use structured error handling
        error_detail = categorize_processing_error(e, correlation_id_for_error)

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
                event_type=settings.CJ_ASSESSMENT_FAILED_TOPIC,
                source_service=settings.SERVICE_NAME,
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
            publishing_error_detail = create_publishing_error_detail(publish_error, correlation_id)
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

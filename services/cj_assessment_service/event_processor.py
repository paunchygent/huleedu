"""Event processing logic for CJ Assessment Service."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from aiokafka import ConsumerRecord
from huleedu_service_libs.logging_utils import create_service_logger

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
from services.cj_assessment_service.metrics import get_business_metrics
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
    processing_started_at = datetime.now(UTC)

    # Get business metrics from shared module
    business_metrics = get_business_metrics()
    comparisons_metric = business_metrics.get("cj_comparisons_made")
    duration_metric = business_metrics.get("cj_assessment_duration_seconds")
    kafka_queue_latency_metric = business_metrics.get("kafka_queue_latency_seconds")

    try:
        logger.info(f"Processing CJ assessment message: {msg.topic}:{msg.partition}:{msg.offset}")

        # Deserialize to specific EventEnvelope with typed data
        try:
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
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

            # Use correlation_id from envelope, fall back to system metadata entity reference
            correlation_id = (
                envelope.correlation_id or request_event_data.system_metadata.entity.entity_id
            )

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

        except (
            Exception
        ) as e:  # Catches Pydantic's ValidationError, JSONDecodeError, UnicodeDecodeError
            logger.error(
                f"Failed to deserialize or validate ELS_CJAssessmentRequestV1 message: {e}",
                exc_info=True,
            )
            return False  # Do not commit unparseable messages

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
        correlation_uuid = (
            correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))
        )
        completed_envelope = EventEnvelope[CJAssessmentCompletedV1](
            event_type=settings_obj.CJ_ASSESSMENT_COMPLETED_TOPIC,
            source_service=settings_obj.SERVICE_NAME,
            correlation_id=correlation_uuid,
            data=completed_event_data,
        )

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
        logger.error(f"Error processing CJ assessment message: {e}", exc_info=True)

        # Publish failure event
        try:
            # Re-deserialize for failure handling if needed
            envelope = EventEnvelope[ELS_CJAssessmentRequestV1].model_validate_json(
                msg.value.decode("utf-8"),
            )
            request_event_data = envelope.data
            correlation_id = (
                envelope.correlation_id or request_event_data.system_metadata.entity.entity_id
            )

            # Create detailed error information including exception type and traceback
            import traceback

            error_details = {
                "error_message": str(e),
                "error_type": type(e).__name__,
                "traceback": traceback.format_exc(),
            }

            # Log detailed error information
            logger.error(f"Detailed error information: {error_details}")

            failed_event_data = CJAssessmentFailedV1(
                event_name=ProcessingEvent.CJ_ASSESSMENT_FAILED,
                entity_ref=request_event_data.entity_ref,
                status=BatchStatus.FAILED_CRITICALLY,
                system_metadata=SystemProcessingMetadata(
                    entity=request_event_data.entity_ref,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.FAILED,
                    event=ProcessingEvent.CJ_ASSESSMENT_FAILED.value,
                    error_info=error_details,
                ),
                cj_assessment_job_id="unknown",  # No CJ job created due to failure
            )

            correlation_uuid = (
                correlation_id if isinstance(correlation_id, UUID) else UUID(str(correlation_id))
            )
            failed_envelope = EventEnvelope[CJAssessmentFailedV1](
                event_type=settings_obj.CJ_ASSESSMENT_FAILED_TOPIC,
                source_service=settings_obj.SERVICE_NAME,
                correlation_id=correlation_uuid,
                data=failed_event_data,
            )

            await event_publisher.publish_assessment_failed(
                failure_data=failed_envelope,
                correlation_id=failed_envelope.correlation_id,
            )
        except Exception as publish_error:
            logger.error(f"Failed to publish failure event: {publish_error}")

        return False  # Don't commit failed messages

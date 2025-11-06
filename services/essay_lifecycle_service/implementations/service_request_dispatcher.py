"""
Specialized service request dispatcher implementation for Essay Lifecycle Service.

Implements SpecializedServiceRequestDispatcher protocol for dispatching requests
    to specialized services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from common_core.events.ai_feedback_events import AIFeedbackInputDataV1
    from common_core.metadata_models import EssayProcessingInputRefV1, StorageReferenceMetadata
    from huleedu_service_libs.outbox import OutboxRepositoryProtocol
    from huleedu_service_libs.protocols import KafkaPublisherProtocol
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.essay_lifecycle_service.config import Settings

from common_core.domain_enums import CourseCode, Language
from huleedu_service_libs.error_handling import (
    raise_cj_assessment_service_error,
    raise_spellcheck_service_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.essay_lifecycle_service.protocols import SpecializedServiceRequestDispatcher


class DefaultSpecializedServiceRequestDispatcher(SpecializedServiceRequestDispatcher):
    """Default implementation of SpecializedServiceRequestDispatcher protocol."""

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        outbox_repository: OutboxRepositoryProtocol,
    ) -> None:
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.outbox_repository = outbox_repository

    async def dispatch_spellcheck_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        batch_id: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch individual spellcheck requests to Spell Checker Service."""
        from datetime import UTC, datetime

        from common_core.essay_service_models import EssayLifecycleSpellcheckRequestV1
        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import SystemProcessingMetadata  # EntityReference removed
        from common_core.status_enums import EssayStatus, ProcessingStage

        logger = create_service_logger("specialized_service_dispatcher")

        logger.info(
            "Dispatching spellcheck requests to Spell Checker Service",
            extra={
                "essay_count": len(essays_to_process),
                "language": language.value,
                "correlation_id": str(correlation_id),
            },
        )

        # Create and publish EssayLifecycleSpellcheckRequestV1 for each essay
        for essay_ref in essays_to_process:
            try:
                # EntityReference removed - using primitive parameters

                # Create system metadata with primitive parameters
                system_metadata = SystemProcessingMetadata(
                    entity_id=essay_ref.essay_id,
                    entity_type="essay",
                    parent_id=batch_id,
                    event=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED.value,
                    timestamp=datetime.now(UTC),
                    processing_stage=ProcessingStage.PENDING,
                )

                # Create spellcheck request event data with primitive parameters
                spellcheck_request = EssayLifecycleSpellcheckRequestV1(
                    event_name=ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED,
                    entity_id=essay_ref.essay_id,
                    entity_type="essay",
                    parent_id=batch_id,
                    status=EssayStatus.AWAITING_SPELLCHECK,
                    system_metadata=system_metadata,
                    text_storage_id=essay_ref.text_storage_id,
                    language=language.value,  # Use enum value for serialization
                )

                # Create event envelope
                envelope = EventEnvelope[EssayLifecycleSpellcheckRequestV1](
                    event_type=topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED),
                    source_service=self.settings.SERVICE_NAME,
                    correlation_id=correlation_id,
                    data=spellcheck_request,
                    metadata={},
                )

                if envelope.metadata is not None:
                    inject_trace_context(envelope.metadata)

                # Publish to outbox for reliable delivery
                topic = topic_name(ProcessingEvent.ESSAY_SPELLCHECK_REQUESTED)
                # Serialize envelope for outbox storage
                event_data = envelope.model_dump(mode="json")
                await self.outbox_repository.add_event(
                    aggregate_id=essay_ref.essay_id,
                    aggregate_type="essay",
                    event_type=envelope.event_type,
                    event_data=event_data,
                    topic=topic,
                    event_key=essay_ref.essay_id,
                    session=session,
                )

                logger.info(
                    f"Dispatched spellcheck request for essay {essay_ref.essay_id}",
                    extra={
                        "essay_id": essay_ref.essay_id,
                        "text_storage_id": essay_ref.text_storage_id,
                        "language": language.value,
                        "event_id": str(envelope.event_id),
                        "correlation_id": str(correlation_id),
                    },
                )

            except Exception as e:
                # Re-raise HuleEduError as-is, or wrap other exceptions
                if hasattr(e, "error_detail"):
                    raise
                else:
                    raise_spellcheck_service_error(
                        service="essay_lifecycle_service",
                        operation="dispatch_spellcheck_requests",
                        message=f"Failed to dispatch spellcheck request to outbox for essay {essay_ref.essay_id}: {e.__class__.__name__}",
                        correlation_id=correlation_id,
                        essay_id=essay_ref.essay_id,
                        text_storage_id=essay_ref.text_storage_id,
                        language=language.value,
                        batch_id=batch_id,
                        error_type=e.__class__.__name__,
                        error_details=str(e),
                    )

        logger.info(
            "Completed dispatching spellcheck requests",
            extra={
                "essays_processed": len(essays_to_process),
                "correlation_id": str(correlation_id),
            },
        )

    async def dispatch_nlp_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        batch_id: str,
        correlation_id: UUID,
        session: AsyncSession | None = None,
        student_prompt_ref: StorageReferenceMetadata | None = None,
    ) -> None:
        """Dispatch NLP processing request to NLP Service with optional prompt reference.

        Following the architectural pattern established by spellcheck,
        ELS forwards the batch request to NLP service for processing.

        Args:
            essays_to_process: List of essays to process
            language: Language of the essays
            batch_id: Batch identifier
            correlation_id: Request correlation ID
            session: Optional database session
            student_prompt_ref: Storage reference for prompt text (if provided)
        """

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope
        from common_core.events.nlp_events import BatchNlpProcessingRequestedV2

        logger = create_service_logger("specialized_service_dispatcher")

        logger.info(
            "Dispatching NLP processing request to NLP Service",
            extra={
                "batch_id": batch_id,
                "essay_count": len(essays_to_process),
                "language": language.value,
                "correlation_id": str(correlation_id),
                "prompt_reference_present": bool(student_prompt_ref),
            },
        )

        try:
            # Create batch NLP processing request with hydrated instructions
            nlp_request = BatchNlpProcessingRequestedV2(
                event_name=ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2,
                entity_id=batch_id,
                entity_type="batch",
                essays_to_process=essays_to_process,
                language=language.value,
                batch_id=batch_id,
                student_prompt_ref=student_prompt_ref,
            )

            # Create event envelope
            envelope = EventEnvelope[BatchNlpProcessingRequestedV2](
                event_type=topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2),
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=nlp_request,
                metadata={},
            )

            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            # Publish to outbox for reliable delivery
            topic = topic_name(ProcessingEvent.BATCH_NLP_PROCESSING_REQUESTED_V2)
            event_data = envelope.model_dump(mode="json")

            await self.outbox_repository.add_event(
                aggregate_id=batch_id,
                aggregate_type="batch",
                event_type=envelope.event_type,
                event_data=event_data,
                topic=topic,
                event_key=batch_id,
                session=session,
            )

            logger.info(
                f"Dispatched NLP processing request for batch {batch_id}",
                extra={
                    "batch_id": batch_id,
                    "event_id": str(envelope.event_id),
                    "correlation_id": str(correlation_id),
                    "essays_count": len(essays_to_process),
                },
            )

        except Exception as e:
            if hasattr(e, "error_detail"):
                raise
            else:
                from huleedu_service_libs.error_handling import raise_processing_error

                raise_processing_error(
                    service="essay_lifecycle_service",
                    operation="dispatch_nlp_requests",
                    message=f"Failed to dispatch NLP request to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    language=language.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def dispatch_ai_feedback_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        context: AIFeedbackInputDataV1,
        batch_correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """Dispatch individual AI feedback requests to AI Feedback Service."""
        # TODO: Implement when AI Feedback Service is available
        logger = create_service_logger("specialized_service_dispatcher")
        logger.info("Dispatching AI feedback requests (STUB)")

    async def dispatch_cj_assessment_requests(
        self,
        essays_to_process: list[EssayProcessingInputRefV1],
        language: Language,
        course_code: CourseCode,
        batch_id: str,
        user_id: str,
        org_id: str | None,
        correlation_id: UUID,
        session: AsyncSession | None = None,
        student_prompt_ref: StorageReferenceMetadata | None = None,
    ) -> None:
        """Dispatch CJ assessment request to CJ Assessment Service with optional prompt reference."""
        from datetime import UTC, datetime

        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.cj_assessment_events import ELS_CJAssessmentRequestV1
        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import SystemProcessingMetadata  # EntityReference removed
        from common_core.status_enums import ProcessingStage

        logger = create_service_logger("specialized_service_dispatcher")

        logger.info(
            "Dispatching CJ assessment request to CJ Assessment Service",
            extra={
                "batch_id": batch_id,
                "essay_count": len(essays_to_process),
                "essay_ids": [essay.essay_id for essay in essays_to_process],
                "language": language.value,
                "course_code": course_code.value,
                "correlation_id": str(correlation_id),
                "prompt_reference_present": bool(student_prompt_ref),
            },
        )

        try:
            system_metadata = SystemProcessingMetadata(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                event=ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED.value,
                timestamp=datetime.now(UTC),
                processing_stage=ProcessingStage.PENDING,
            )

            cj_request = ELS_CJAssessmentRequestV1(
                entity_id=batch_id,
                entity_type="batch",
                parent_id=None,
                system_metadata=system_metadata,
                essays_for_cj=essays_to_process,
                language=language.value,
                course_code=course_code,
                student_prompt_ref=student_prompt_ref,
                llm_config_overrides=None,
                user_id=user_id,
                org_id=org_id,
            )

            envelope = EventEnvelope[ELS_CJAssessmentRequestV1](
                event_type=topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED),
                source_service=self.settings.SERVICE_NAME,
                correlation_id=correlation_id,
                data=cj_request,
                metadata={},
            )

            if envelope.metadata is not None:
                inject_trace_context(envelope.metadata)

            topic = topic_name(ProcessingEvent.ELS_CJ_ASSESSMENT_REQUESTED)
            event_data = envelope.model_dump(mode="json")
            await self.outbox_repository.add_event(
                aggregate_id=batch_id,
                aggregate_type="batch",
                event_type=envelope.event_type,
                event_data=event_data,
                topic=topic,
                event_key=batch_id,
                session=session,
            )

            logger.info(
                "Successfully dispatched CJ assessment request",
                extra={
                    "batch_id": batch_id,
                    "essay_count": len(essays_to_process),
                    "language": language.value,
                    "course_code": course_code.value,
                    "event_id": str(envelope.event_id),
                    "correlation_id": str(correlation_id),
                },
            )

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_cj_assessment_service_error(
                    service="essay_lifecycle_service",
                    operation="dispatch_cj_assessment_requests",
                    message=f"Failed to dispatch CJ assessment request to outbox: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    batch_id=batch_id,
                    essay_count=len(essays_to_process),
                    language=language.value,
                    course_code=course_code.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

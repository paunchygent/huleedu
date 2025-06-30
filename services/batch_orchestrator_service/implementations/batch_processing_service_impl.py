"""Batch processing service implementation for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from services.batch_orchestrator_service.api_models import BatchRegistrationRequestV1
from services.batch_orchestrator_service.config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_orchestrator_service.protocols import (
    BatchEventPublisherProtocol,
    BatchRepositoryProtocol,
)

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.batch_coordination_events import BatchEssaysRegistered
from common_core.events.envelope import EventEnvelope
from common_core.metadata_models import EntityReference, SystemProcessingMetadata
from common_core.pipeline_models import ProcessingPipelineState


class BatchProcessingServiceImpl:
    """Service layer implementation for batch processing operations."""

    def __init__(
        self,
        batch_repo: BatchRepositoryProtocol,
        event_publisher: BatchEventPublisherProtocol,
        settings: Settings,
    ) -> None:
        """Initialize with repository, event publisher, and settings dependencies."""
        self.batch_repo = batch_repo
        self.event_publisher = event_publisher
        self.settings = settings
        self.logger = create_service_logger("bos.service.batch_processing")

    async def register_new_batch(
        self,
        registration_data: BatchRegistrationRequestV1,
        correlation_id: uuid.UUID,
    ) -> str:
        """Register a new batch for processing.

        Args:
            registration_data: Validated batch registration request data
            correlation_id: Correlation ID for tracking

        Returns:
            Generated batch ID
        """
        batch_id = str(uuid.uuid4())

        # Generate internal essay_id slots based on expected_essay_count
        # These become the authoritative essay identifiers for this batch
        internal_essay_ids = [
            str(uuid.uuid4()) for _ in range(registration_data.expected_essay_count)
        ]

        self.logger.info(
            f"Registering new batch {batch_id} with "
            f"{registration_data.expected_essay_count} essays. Generated internal essay IDs: "
            f"{len(internal_essay_ids)} slots",
            extra={"correlation_id": str(correlation_id)},
        )

        # 1. Persist Full Batch Context
        await self.batch_repo.store_batch_context(batch_id, registration_data)

        # 2. Determine requested pipelines based on registration data (Task 3.1)
        requested_pipelines = ["spellcheck"]  # Always include spellcheck first
        if registration_data.enable_cj_assessment:
            requested_pipelines.append("cj_assessment")
            self.logger.info(
                f"CJ assessment enabled for batch {batch_id}",
                extra={"correlation_id": str(correlation_id)},
            )

        # Future pipeline support
        if getattr(registration_data, "enable_ai_feedback", False):
            requested_pipelines.append("ai_feedback")
        if getattr(registration_data, "enable_nlp_metrics", False):
            requested_pipelines.append("nlp_metrics")

        # 3. Initialize pipeline state with proper PipelineStateDetail objects (Task 3.1)
        from common_core.pipeline_models import PipelineExecutionStatus, PipelineStateDetail

        # Initialize each pipeline phase with correct status
        spellcheck_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if "spellcheck" in requested_pipelines
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        cj_assessment_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if "cj_assessment" in requested_pipelines
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        ai_feedback_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if "ai_feedback" in requested_pipelines
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )
        nlp_metrics_detail = PipelineStateDetail(
            status=(
                PipelineExecutionStatus.PENDING_DEPENDENCIES
                if "nlp_metrics" in requested_pipelines
                else PipelineExecutionStatus.SKIPPED_BY_USER_CONFIG
            ),
        )

        initial_pipeline_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=requested_pipelines,
            spellcheck=spellcheck_detail,
            cj_assessment=cj_assessment_detail,
            ai_feedback=ai_feedback_detail,
            nlp_metrics=nlp_metrics_detail,
        )
        await self.batch_repo.save_processing_pipeline_state(
            batch_id,
            initial_pipeline_state.model_dump(mode="json"),
        )

        # 3. Construct lightweight BatchEssaysRegistered event with internal essay IDs
        batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")
        event_metadata = SystemProcessingMetadata(
            entity=batch_entity_ref,
            event=ProcessingEvent.BATCH_ESSAYS_REGISTERED.value,
            timestamp=datetime.now(UTC),
        )
        batch_registered_event_data = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=registration_data.expected_essay_count,
            essay_ids=internal_essay_ids,  # Use generated internal IDs instead of user-provided
            metadata=event_metadata,
            # Course context for ELS to use in BatchEssaysReady events
            course_code=registration_data.course_code,
            essay_instructions=registration_data.essay_instructions,
            user_id=registration_data.user_id,
        )

        # 4. Create EventEnvelope
        envelope = EventEnvelope[BatchEssaysRegistered](
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=batch_registered_event_data,
        )

        # 5. Publish event
        await self.event_publisher.publish_batch_event(envelope, key=batch_id)

        self.logger.info(
            f"Published BatchEssaysRegistered event for batch {batch_id} with "
            f"{len(internal_essay_ids)} internal essay slots, pipelines: {requested_pipelines}, "
            f"event_id {envelope.event_id}",
            extra={"correlation_id": str(correlation_id)},
        )

        return batch_id

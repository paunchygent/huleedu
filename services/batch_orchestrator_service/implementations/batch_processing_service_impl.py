"""Batch processing service implementation for Batch Orchestrator Service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from api_models import BatchRegistrationRequestV1
from config import Settings
from huleedu_service_libs.logging_utils import create_service_logger
from protocols import BatchEventPublisherProtocol, BatchRepositoryProtocol

from common_core.enums import ProcessingEvent, topic_name
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
        self, registration_data: BatchRegistrationRequestV1, correlation_id: uuid.UUID
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
            extra={"correlation_id": str(correlation_id)}
        )

        # 1. Persist Full Batch Context
        await self.batch_repo.store_batch_context(batch_id, registration_data)

        # Also store initial pipeline state
        initial_pipeline_state = ProcessingPipelineState(
            batch_id=batch_id,
            requested_pipelines=[], # Spellcheck will be added when BatchEssaysReady is received
        )
        await self.batch_repo.save_processing_pipeline_state(batch_id, initial_pipeline_state)

        # 2. Construct lightweight BatchEssaysRegistered event with internal essay IDs
        batch_entity_ref = EntityReference(entity_id=batch_id, entity_type="batch")
        event_metadata = SystemProcessingMetadata(
            entity=batch_entity_ref,
            event=ProcessingEvent.BATCH_ESSAYS_REGISTERED.value,
            timestamp=datetime.now(timezone.utc)
        )
        batch_registered_event_data = BatchEssaysRegistered(
            batch_id=batch_id,
            expected_essay_count=registration_data.expected_essay_count,
            essay_ids=internal_essay_ids,  # Use generated internal IDs instead of user-provided
            metadata=event_metadata
        )

        # 3. Create EventEnvelope
        envelope = EventEnvelope[BatchEssaysRegistered](
            event_type=topic_name(ProcessingEvent.BATCH_ESSAYS_REGISTERED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=batch_registered_event_data
        )

        # 4. Publish event
        await self.event_publisher.publish_batch_event(envelope)

        self.logger.info(
            f"Published BatchEssaysRegistered event for batch {batch_id} with "
            f"{len(internal_essay_ids)} internal essay slots, event_id {envelope.event_id}",
            extra={"correlation_id": str(correlation_id)}
        )

        return batch_id

"""
Batch lifecycle event publishing for major milestones.

Handles batch lifecycle events like batch ready, excess content,
slot assignments, and phase outcomes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from services.essay_lifecycle_service.config import Settings
    from services.essay_lifecycle_service.implementations.outbox_manager import OutboxManager
    from services.essay_lifecycle_service.protocols import TopicNamingProtocol

logger = create_service_logger("essay_lifecycle_service.batch_lifecycle_publisher")


class BatchLifecyclePublisher:
    """
    Handles major batch lifecycle event publishing.

    Publishes events for batch completion, excess content handling,
    slot assignments, and phase outcomes using TRUE OUTBOX PATTERN for
    transactional safety and reliable delivery.
    """

    def __init__(
        self,
        settings: Settings,
        outbox_manager: OutboxManager,
        topic_naming: TopicNamingProtocol,
    ) -> None:
        self.settings = settings
        self.outbox_manager = outbox_manager
        self.topic_naming = topic_naming

    def _get_topic_for_event_type(self, event_type: str) -> str:
        """Map event type to appropriate Kafka topic."""
        if "spellcheck" in event_type:
            return "essay.spellcheck.requests"
        elif "nlp" in event_type:
            return "essay.nlp.requests"
        elif "ai_feedback" in event_type:
            return "essay.ai_feedback.requests"
        else:
            return "essay.processing.requests"

    async def publish_excess_content_provisioned(
        self,
        event_data: Any,  # ExcessContentProvisionedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish ExcessContentProvisionedV1 event when no slots are available.

        Args:
            event_data: The excess content provisioned event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.topic_naming.get_topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.EXCESS_CONTENT_PROVISIONED),
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "ExcessContentProvisionedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_batch_essays_ready(
        self,
        event_data: Any,  # BatchEssaysReady
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish BatchEssaysReady event when batch is complete.

        Args:
            event_data: The batch essays ready event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.topic_naming.get_topic_name(ProcessingEvent.BATCH_ESSAYS_READY)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.BATCH_ESSAYS_READY),
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "BatchEssaysReady event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "ready_count": len(getattr(event_data, "ready_essays", [])),
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_batch_content_provisioning_completed(
        self,
        event_data: Any,  # BatchContentProvisioningCompletedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish BatchContentProvisioningCompletedV1 event when all content is provisioned.

        This replaces BatchEssaysReady for initial content provisioning completion.
        For GUEST batches, BOS will transition directly to READY_FOR_PIPELINE_EXECUTION.
        For REGULAR batches, BOS will initiate student matching workflow.

        Args:
            event_data: The batch content provisioning completed event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.topic_naming.get_topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.BATCH_CONTENT_PROVISIONING_COMPLETED),
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "BatchContentProvisioningCompletedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "provisioned_count": getattr(event_data, "provisioned_count", 0),
                "expected_count": getattr(event_data, "expected_count", 0),
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_batch_validation_errors(
        self,
        event_data: Any,  # BatchValidationErrorsV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish BatchValidationErrorsV1 event for structured error handling.

        This method implements the new dual-event publishing pattern where validation
        errors are published separately from success events, following HuleEdu
        structured error handling principles.

        Args:
            event_data: The batch validation errors event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope for validation errors
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Store validation error event in outbox
        from common_core.event_enums import ProcessingEvent

        topic = self.topic_naming.get_topic_name(ProcessingEvent.BATCH_VALIDATION_ERRORS)  # New topic for error events
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=topic,
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "BatchValidationErrors event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "error_count": len(getattr(event_data, "failed_essays", [])),
                "critical_failure": getattr(event_data.error_summary, "critical_failure", False)
                if hasattr(event_data, "error_summary")
                else False,
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_essay_slot_assigned(
        self,
        event_data: Any,  # EssaySlotAssignedV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish EssaySlotAssignedV1 event when content is assigned to a slot.

        Args:
            event_data: The essay slot assigned event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
            metadata={},
        )

        # Inject current trace context
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # Try immediate Kafka publishing first
        topic = self.topic_naming.get_topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED)
        essay_id = getattr(event_data, "essay_id", "unknown")

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="essay",
            aggregate_id=essay_id,
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.ESSAY_SLOT_ASSIGNED),
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "EssaySlotAssignedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": getattr(event_data, "batch_id", "unknown"),
                "essay_id": essay_id,
                "file_upload_id": getattr(event_data, "file_upload_id", "unknown"),
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

    async def publish_els_batch_phase_outcome(
        self,
        event_data: Any,  # ELSBatchPhaseOutcomeV1
        correlation_id: UUID,
        session: AsyncSession | None = None,
    ) -> None:
        """
        Publish ELSBatchPhaseOutcomeV1 event when phase is complete.

        Args:
            event_data: The batch phase outcome event data
            correlation_id: Correlation ID for event tracking
            session: Optional database session (unused in this implementation)

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from common_core.event_enums import ProcessingEvent
        from common_core.events.envelope import EventEnvelope

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id or uuid4(),
            data=event_data,
        )

        # Only inject trace context if we have an active span
        from huleedu_service_libs.observability import get_current_span

        if get_current_span():
            if envelope.metadata is None:
                envelope.metadata = {}
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = self.topic_naming.get_topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=self.topic_naming.get_topic_name(ProcessingEvent.ELS_BATCH_PHASE_OUTCOME),
            event_data=envelope,
            topic=topic,
            session=session,  # Pass session for transactional atomicity
        )

        logger.info(
            "ELSBatchPhaseOutcomeV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "phase": getattr(event_data, "phase", "unknown"),
                "outcome": getattr(event_data, "outcome", "unknown"),
                "correlation_id": str(correlation_id),
                "topic": topic,
            },
        )

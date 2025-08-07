"""Event publisher implementation for Result Aggregator Service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from common_core.events.result_events import BatchAssessmentCompletedV1, BatchResultsReadyV1
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

from services.result_aggregator_service.config import Settings
from services.result_aggregator_service.protocols import OutboxManagerProtocol

if TYPE_CHECKING:
    from services.result_aggregator_service.notification_projector import (
        ResultNotificationProjector,
    )

logger = create_service_logger("result_aggregator_service.implementations.event_publisher")


class ResultEventPublisher:
    """Event publisher for Result Aggregator Service using TRUE OUTBOX PATTERN."""

    def __init__(
        self,
        outbox_manager: OutboxManagerProtocol,
        settings: Settings,
        notification_projector: ResultNotificationProjector | None = None,
    ):
        self.outbox_manager = outbox_manager
        self.settings = settings
        self.notification_projector = notification_projector

    async def publish_batch_results_ready(
        self,
        event_data: BatchResultsReadyV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchResultsReadyV1 event when all phases complete.

        Uses TRUE OUTBOX PATTERN - stores in DB first, relay worker publishes async.
        """
        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope with type safety
        envelope = EventEnvelope[BatchResultsReadyV1](
            event_type=topic_name(ProcessingEvent.BATCH_RESULTS_READY),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = topic_name(ProcessingEvent.BATCH_RESULTS_READY)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=topic,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "BatchResultsReadyV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "correlation_id": str(correlation_id),
                "topic": topic,
                "total_essays": getattr(event_data, "total_essays", 0),
                "completed_essays": getattr(event_data, "completed_essays", 0),
            },
        )

        # CANONICAL NOTIFICATION PATTERN: Direct invocation after domain event
        # No Kafka round-trip - immediate teacher notification
        if self.notification_projector:
            await self.notification_projector.handle_batch_results_ready(event_data, correlation_id)

    async def publish_batch_assessment_completed(
        self,
        event_data: BatchAssessmentCompletedV1,
        correlation_id: UUID,
    ) -> None:
        """
        Publish BatchAssessmentCompletedV1 event when CJ assessment completes.

        Uses TRUE OUTBOX PATTERN - stores in DB first, relay worker publishes async.
        """
        from common_core.event_enums import ProcessingEvent, topic_name
        from common_core.events.envelope import EventEnvelope

        # Create event envelope with type safety
        envelope = EventEnvelope[BatchAssessmentCompletedV1](
            event_type=topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED),
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=event_data,
            metadata={},
        )

        # Inject current trace context into the envelope metadata
        if envelope.metadata is not None:
            inject_trace_context(envelope.metadata)

        # TRUE OUTBOX PATTERN: Always use outbox for transactional safety
        # Store event in outbox within same transaction as business data
        # The relay worker will publish from outbox asynchronously
        topic = topic_name(ProcessingEvent.BATCH_ASSESSMENT_COMPLETED)
        batch_id = getattr(event_data, "batch_id", "unknown")

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="batch",
            aggregate_id=batch_id,
            event_type=topic,
            event_data=envelope,
            topic=topic,
        )

        logger.info(
            "BatchAssessmentCompletedV1 event stored in outbox for reliable delivery",
            extra={
                "batch_id": batch_id,
                "correlation_id": str(correlation_id),
                "topic": topic,
                "assessment_job_id": getattr(event_data, "assessment_job_id", "unknown"),
            },
        )

        # CANONICAL NOTIFICATION PATTERN: Direct invocation after domain event
        # No Kafka round-trip - immediate teacher notification
        if self.notification_projector:
            await self.notification_projector.handle_batch_assessment_completed(event_data, correlation_id)

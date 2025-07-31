"""
Batch progress and conclusion event publishing.

Handles batch-level progress reporting and phase conclusion events
for coordination with the Batch Service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from huleedu_service_libs.error_handling import raise_outbox_storage_error
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

if TYPE_CHECKING:
    from huleedu_service_libs.protocols import KafkaPublisherProtocol

    from services.essay_lifecycle_service.config import Settings

logger = create_service_logger("essay_lifecycle_service.batch_progress_publisher")


class BatchProgressPublisher:
    """
    Handles batch progress and conclusion event publishing.

    Publishes progress updates and phase conclusion events to coordinate
    with the Batch Service and provide visibility into batch processing.
    """

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
    ) -> None:
        self.kafka_bus = kafka_bus
        self.settings = settings

    async def publish_batch_phase_progress(
        self,
        batch_id: str,
        phase: str,
        completed_count: int,
        failed_count: int,
        total_essays_in_phase: int,
        correlation_id: UUID,
    ) -> None:
        """
        Report aggregated progress of a specific phase for a batch to BS.

        Args:
            batch_id: The batch identifier
            phase: Name of the processing phase
            completed_count: Number of essays completed in this phase
            failed_count: Number of essays failed in this phase
            total_essays_in_phase: Total essays in this phase
            correlation_id: Correlation ID for event tracking

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from datetime import UTC, datetime

        from common_core.events.envelope import EventEnvelope
        # EntityReference removed - using primitive parameters

        # Create batch progress event data with primitive parameters
        event_data = {
            "event_name": "batch.phase.progress.v1",
            "entity_id": batch_id,
            "entity_type": "batch",
            "parent_id": None,
            "phase": phase,
            "completed_count": completed_count,
            "failed_count": failed_count,
            "total_essays_in_phase": total_essays_in_phase,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.progress.v1",
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

        # Try immediate Kafka publishing first
        topic = "batch.phase.progress.events"
        key = batch_id

        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "Batch phase progress published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, will need outbox fallback",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

            # Kafka failed - caller should handle outbox fallback
            raise_outbox_storage_error(
                service="essay_lifecycle_service",
                operation="publish_batch_phase_progress",
                message=f"Kafka publish failed: {kafka_error.__class__.__name__}",
                correlation_id=correlation_id,
                aggregate_id=batch_id,
                aggregate_type="batch",
                event_type="huleedu.els.batch_phase.progress.v1",
                topic=topic,
                batch_id=batch_id,
                phase=phase,
                completed_count=completed_count,
                failed_count=failed_count,
                total_essays_in_phase=total_essays_in_phase,
                error_type=kafka_error.__class__.__name__,
                error_details=str(kafka_error),
            )

    async def publish_batch_phase_concluded(
        self,
        batch_id: str,
        phase: str,
        status: str,
        details: dict[str, Any],
        correlation_id: UUID,
    ) -> None:
        """
        Report the final conclusion of a phase for a batch to BS.

        Args:
            batch_id: The batch identifier
            phase: Name of the processing phase
            status: Final status of the phase
            details: Additional details about the conclusion
            correlation_id: Correlation ID for event tracking

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox would be needed
        """
        from datetime import UTC, datetime

        from common_core.events.envelope import EventEnvelope
        # EntityReference removed - using primitive parameters

        # Create batch conclusion event data with primitive parameters
        event_data = {
            "event_name": "batch.phase.concluded.v1",
            "entity_id": batch_id,
            "entity_type": "batch",
            "parent_id": None,
            "phase": phase,
            "status": status,
            "details": details,
            "timestamp": datetime.now(UTC).isoformat(),
        }

        # Create event envelope
        envelope = EventEnvelope[Any](
            event_type="huleedu.els.batch_phase.concluded.v1",
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

        # Try immediate Kafka publishing first
        topic = "batch.phase.concluded.events"
        key = batch_id

        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )

            logger.info(
                "Batch phase conclusion published directly to Kafka",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "status": status,
                    "correlation_id": str(correlation_id),
                    "topic": topic,
                },
            )
            return  # Success - no outbox needed!

        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, will need outbox fallback",
                extra={
                    "batch_id": batch_id,
                    "phase": phase,
                    "error": str(kafka_error),
                    "error_type": kafka_error.__class__.__name__,
                },
            )

            # Kafka failed - caller should handle outbox fallback
            raise_outbox_storage_error(
                service="essay_lifecycle_service",
                operation="publish_batch_phase_concluded",
                message=f"Kafka publish failed: {kafka_error.__class__.__name__}",
                correlation_id=correlation_id,
                aggregate_id=batch_id,
                aggregate_type="batch",
                event_type="huleedu.els.batch_phase.concluded.v1",
                topic=topic,
                batch_id=batch_id,
                phase=phase,
                status=status,
                error_type=kafka_error.__class__.__name__,
                error_details=str(kafka_error),
            )

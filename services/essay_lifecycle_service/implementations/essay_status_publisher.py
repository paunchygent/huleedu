"""
Essay status event publishing and real-time notification management.

Handles individual essay status updates, both Kafka event publishing
and Redis real-time notifications for UI updates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from huleedu_service_libs.error_handling import (
    raise_external_service_error,
    raise_outbox_storage_error,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.observability import inject_trace_context

if TYPE_CHECKING:
    from common_core.status_enums import EssayStatus
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol, KafkaPublisherProtocol

    from services.essay_lifecycle_service.config import Settings
    from services.essay_lifecycle_service.protocols import BatchEssayTracker

logger = create_service_logger("essay_lifecycle_service.essay_status_publisher")


class EssayStatusPublisher:
    """
    Handles essay status event publishing and real-time notifications.

    Publishes essay status updates to Kafka for downstream services
    and to Redis for real-time UI notifications.
    """

    def __init__(
        self,
        kafka_bus: KafkaPublisherProtocol,
        settings: Settings,
        redis_client: AtomicRedisClientProtocol,
        batch_tracker: BatchEssayTracker,
    ) -> None:
        self.kafka_bus = kafka_bus
        self.settings = settings
        self.redis_client = redis_client
        self.batch_tracker = batch_tracker

    async def publish_status_update(
        self, essay_id: str, batch_id: str | None, status: EssayStatus, correlation_id: UUID
    ) -> None:
        """
        Publish essay status update event to both Kafka and Redis.

        Args:
            essay_id: Essay identifier
            batch_id: Batch identifier (if applicable)
            status: New essay status
            correlation_id: Correlation ID for event tracking

        Raises:
            HuleEduError: If publishing fails to both Kafka and outbox
        """
        from datetime import UTC, datetime

        from common_core.events.envelope import EventEnvelope
        from common_core.metadata_models import SystemProcessingMetadata

        # Create status update event data as a dict that's JSON serializable
        event_data = {
            "event_name": "essay.status.updated.v1",
            "entity_id": essay_id,
            "entity_type": "essay",
            "parent_id": batch_id,
            "status": status.value,
            "system_metadata": SystemProcessingMetadata(
                entity_id=essay_id,
                entity_type="essay",
                parent_id=batch_id,
                timestamp=datetime.now(UTC),
            ).model_dump(),
        }

        # Create event envelope (using Any type for now)
        envelope = EventEnvelope[Any](
            event_type="essay.status.updated.v1",
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
        topic = "essay.status.events"
        key = str(essay_id)

        try:
            await self.kafka_bus.publish(
                topic=topic,
                envelope=envelope,
                key=key,
            )
            logger.info(
                "Essay status update published directly to Kafka",
                extra={
                    "essay_id": essay_id,
                    "status": status.value,
                    "correlation_id": str(correlation_id),
                },
            )
        except Exception as kafka_error:
            # Check if it's already a HuleEduError and re-raise
            if hasattr(kafka_error, "error_detail"):
                raise

            logger.warning(
                "Kafka publish failed, will need outbox fallback",
                extra={
                    "essay_id": essay_id,
                    "status": status.value,
                    "error": str(kafka_error),
                },
            )

            # Kafka failed - caller should handle outbox fallback
            raise_outbox_storage_error(
                service="essay_lifecycle_service",
                operation="publish_status_update",
                message=f"Kafka publish failed: {kafka_error.__class__.__name__}",
                correlation_id=correlation_id,
                aggregate_id=str(essay_id),
                aggregate_type="essay",
                event_type="essay.status.updated.v1",
                topic=topic,
                essay_id=essay_id,
                status=status.value,
                error_type=kafka_error.__class__.__name__,
                error_details=str(kafka_error),
            )

        # Publish to Redis for real-time updates (independent of Kafka)
        await self._publish_essay_status_to_redis(essay_id, batch_id, status, correlation_id)

    async def _publish_essay_status_to_redis(
        self,
        essay_id: str,
        batch_id: str | None,
        status: EssayStatus,
        correlation_id: UUID,
    ) -> None:
        """
        Publish essay status update to Redis for real-time UI notifications.

        Args:
            essay_id: Essay identifier
            batch_id: Batch identifier (if applicable)
            status: New essay status
            correlation_id: Correlation ID for event tracking

        Raises:
            HuleEduError: If Redis operation fails
        """
        try:
            from datetime import UTC, datetime

            # Look up the user_id for this essay from batch context
            user_id = await self.batch_tracker.get_user_id_for_essay(essay_id)

            if user_id:
                # Publish real-time notification to user-specific Redis channel
                await self.redis_client.publish_user_notification(
                    user_id=user_id,
                    event_type="essay_status_updated",
                    data={
                        "essay_id": essay_id,
                        "status": status.value,
                        "timestamp": datetime.now(UTC).isoformat(),
                        "correlation_id": str(correlation_id),
                    },
                )

                logger.info(
                    f"Published real-time essay status notification to Redis for user {user_id}",
                    extra={
                        "essay_id": essay_id,
                        "user_id": user_id,
                        "status": status.value,
                        "correlation_id": str(correlation_id),
                    },
                )
            else:
                logger.warning(
                    "Cannot publish Redis notification: user_id not found for essay",
                    extra={
                        "essay_id": essay_id,
                        "status": status.value,
                        "correlation_id": str(correlation_id),
                    },
                )

        except Exception as e:
            # Re-raise HuleEduError as-is, or wrap other exceptions
            if hasattr(e, "error_detail"):
                raise
            else:
                raise_external_service_error(
                    service="essay_lifecycle_service",
                    operation="_publish_essay_status_to_redis",
                    external_service="Redis",
                    message=f"Failed to publish essay status to Redis: {e.__class__.__name__}",
                    correlation_id=correlation_id,
                    essay_id=essay_id,
                    user_id=user_id if "user_id" in locals() else None,
                    status=status.value,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

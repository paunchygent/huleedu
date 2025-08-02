"""
Outbox pattern and relay worker management for reliable event publishing.

Handles the transactional outbox pattern as a fallback mechanism when
Kafka is unavailable, and manages relay worker notifications.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from huleedu_service_libs.outbox import OutboxRepositoryProtocol
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

    from services.class_management_service.config import Settings

logger = create_service_logger("class_management_service.outbox_manager")


class OutboxManager:
    """
    Manages outbox pattern and relay worker coordination.

    Provides reliable event publishing through the transactional outbox pattern
    when direct Kafka publishing fails, and handles relay worker notifications.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings

    async def publish_to_outbox(
        self,
        aggregate_id: str,
        aggregate_type: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
        session: Any | None = None,  # AsyncSession | None
    ) -> None:
        """
        Store event in outbox for reliable delivery.

        This implements the Transactional Outbox Pattern as a fallback mechanism
        when Kafka is unavailable. Events are stored in the database and
        published asynchronously by the relay worker.

        Args:
            aggregate_type: Type of aggregate (e.g., "student", "class", "batch")
            aggregate_id: ID of the aggregate that produced the event
            event_type: Type of event being published
            event_data: Complete event envelope to publish
            topic: Kafka topic to publish to
            session: Optional database session for transactional atomicity

        Raises:
            HuleEduError: If outbox repository is not configured or storage fails
        """
        if not self.outbox_repository:
            raise_external_service_error(
                service="class_management_service",
                operation="publish_to_outbox",
                external_service="outbox_repository",
                message="Outbox repository not configured for transactional publishing",
                correlation_id=event_data.correlation_id
                if hasattr(event_data, "correlation_id")
                else UUID("00000000-0000-0000-0000-000000000000"),
                aggregate_id=aggregate_id,
                event_type=event_type,
            )

        try:
            # CLEAN ARCHITECTURE: Always expect Pydantic EventEnvelope
            # Publishers should pass the original envelope, not reconstructed data
            if not hasattr(event_data, "model_dump"):
                raise ValueError(
                    f"OutboxManager expects Pydantic EventEnvelope, got {type(event_data)}"
                )

            # Serialize the envelope to JSON for storage
            serialized_data = event_data.model_dump(mode="json")

            # Add topic to the event data for relay worker
            serialized_data["topic"] = topic

            # Determine Kafka key from envelope metadata or aggregate ID
            event_key = aggregate_id
            if hasattr(event_data, "metadata") and event_data.metadata:
                event_key = event_data.metadata.get("partition_key", aggregate_id)

            # Store in outbox repository (atomically within session if provided)
            await self.outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=serialized_data,
                topic=topic,
                event_key=event_key,
                session=session,
            )

            # Notify relay worker via Redis
            await self._notify_relay_worker()

            logger.info(
                "Event stored in outbox for reliable delivery",
                extra={
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "event_type": event_type,
                    "topic": topic,
                    "correlation_id": str(event_data.correlation_id)
                    if hasattr(event_data, "correlation_id")
                    else "unknown",
                },
            )

        except Exception as e:
            logger.error(
                f"Failed to store event in outbox: {e}",
                extra={
                    "aggregate_type": aggregate_type,
                    "aggregate_id": aggregate_id,
                    "event_type": event_type,
                    "topic": topic,
                },
                exc_info=True,
            )
            raise

    async def _notify_relay_worker(self) -> None:
        """Notify relay worker about pending outbox events via Redis."""
        try:
            # Publish notification to Redis channel for relay worker
            # Using publish_user_notification with system user ID for relay worker
            await self.redis_client.publish_user_notification(
                user_id="system:relay_worker",
                event_type=f"outbox:relay:{self.settings.SERVICE_NAME}",
                data={"service": self.settings.SERVICE_NAME, "action": "process_outbox"},
            )
            logger.debug(f"Notified relay worker for service: {self.settings.SERVICE_NAME}")
        except Exception as e:
            # Log but don't fail - relay worker has polling fallback
            logger.warning(
                f"Failed to notify relay worker via Redis: {e}",
                extra={"service": self.settings.SERVICE_NAME},
            )
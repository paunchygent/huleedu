"""
Outbox Manager implementation for Entitlements Service.

This module implements the transactional outbox pattern for reliable event publishing
from credit operations. It ensures events are published atomically with database
operations using the outbox table.
"""

import logging
from typing import Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.outbox import OutboxRepositoryProtocol
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol

from services.entitlements_service.config import Settings

logger = logging.getLogger(__name__)


class OutboxManager:
    """
    Manager for transactional outbox pattern in Entitlements Service.

    Ensures events are stored atomically with business operations and
    published asynchronously by the relay worker.
    """

    def __init__(
        self,
        outbox_repository: OutboxRepositoryProtocol,
        redis_client: AtomicRedisClientProtocol,
        settings: Settings,
    ) -> None:
        """
        Initialize outbox manager with dependencies.

        Args:
            outbox_repository: Repository for outbox operations
            redis_client: Redis client for wake-up notifications
            settings: Service settings including service name
        """
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,  # EventEnvelope[Any]
        topic: str,
    ) -> None:
        """
        Store event in outbox for reliable delivery.

        This implements the transactional outbox pattern for transactional safety,
        ensuring events are stored atomically with business data and
        published asynchronously by the relay worker.

        Args:
            aggregate_type: Type of aggregate (e.g., "credit_balance", "rate_limit")
            aggregate_id: ID of the aggregate that produced the event
            event_type: Type of event being published
            event_data: Complete event envelope to publish
            topic: Kafka topic to publish to

        Raises:
            HuleEduError: If outbox repository is not configured or storage fails
        """
        if not self.outbox_repository:
            raise_external_service_error(
                service="entitlements_service",
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
            # Always expect Pydantic EventEnvelope
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

            # Store in outbox
            outbox_id = await self.outbox_repository.add_event(
                aggregate_id=aggregate_id,
                aggregate_type=aggregate_type,
                event_type=event_type,
                event_data=serialized_data,
                topic=topic,
                event_key=event_key,
            )

            logger.debug(
                "Event stored in outbox for transactional safety",
                extra={
                    "outbox_id": str(outbox_id),
                    "event_type": event_type,
                    "aggregate_id": aggregate_id,
                    "aggregate_type": aggregate_type,
                    "topic": topic,
                    "correlation_id": str(event_data.correlation_id),
                },
            )

            # Wake up the relay worker immediately
            await self.notify_relay_worker()

        except Exception as e:
            # Re-raise HuleEduError as-is, wrap others
            if hasattr(e, "error_detail"):
                raise
            else:
                # Extract correlation ID for error context
                error_correlation_id = UUID("00000000-0000-0000-0000-000000000000")
                if hasattr(event_data, "correlation_id"):
                    error_correlation_id = event_data.correlation_id
                elif isinstance(event_data, dict):
                    try:
                        error_correlation_id = UUID(
                            str(
                                event_data.get(
                                    "correlation_id", "00000000-0000-0000-0000-000000000000"
                                )
                            )
                        )
                    except (ValueError, TypeError):
                        pass  # Use default UUID

                raise_external_service_error(
                    service="entitlements_service",
                    operation="publish_to_outbox",
                    external_service="outbox_repository",
                    message=f"Failed to store event in outbox: {e.__class__.__name__}",
                    correlation_id=error_correlation_id,
                    aggregate_id=aggregate_id,
                    event_type=event_type,
                    error_type=e.__class__.__name__,
                    error_details=str(e),
                )

    async def notify_relay_worker(self) -> None:
        """
        Send wake-up notification to relay worker via Redis.

        Uses Redis LPUSH to notify the relay worker that new events
        are available for processing, enabling immediate processing
        instead of waiting for the next polling interval.
        """
        try:
            wake_key = f"{self.settings.SERVICE_NAME}:outbox:wake"
            await self.redis_client.lpush(wake_key, "wake")
            logger.debug(f"Wake notification sent to relay worker: {wake_key}")
        except Exception as e:
            # Don't fail the operation if wake notification fails
            logger.warning(
                f"Failed to send wake notification to relay worker: {e}",
                exc_info=True,
            )

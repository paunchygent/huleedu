"""Event publisher implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJEventPublisherProtocol,
enabling the CJ service to publish assessment results and failures using the
TRUE OUTBOX PATTERN for transactional safety.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from huleedu_service_libs.logging_utils import create_service_logger

if TYPE_CHECKING:
    from services.cj_assessment_service.config import Settings
    from services.cj_assessment_service.protocols import OutboxRepositoryProtocol
    from huleedu_service_libs.protocols import AtomicRedisClientProtocol

from services.cj_assessment_service.protocols import CJEventPublisherProtocol

logger = create_service_logger("cj_assessment_service.event_publisher")


class CJEventPublisherImpl(CJEventPublisherProtocol):
    """Implementation of CJEventPublisherProtocol using TRUE OUTBOX PATTERN."""

    def __init__(self, outbox_repository: OutboxRepositoryProtocol, redis_client: AtomicRedisClientProtocol, settings: Settings) -> None:
        """Initialize event publisher with outbox repository for transactional safety."""
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client
        self.settings = settings

    async def publish_assessment_completed(
        self,
        completion_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment completion event using TRUE OUTBOX PATTERN.

        Args:
            completion_data: The CJ assessment completion event data (already an EventEnvelope)
            correlation_id: Correlation ID for event tracing

        Note:
            This uses the transactional outbox pattern to ensure atomic consistency
            between database state and event publishing. Events are stored in the
            outbox table and published asynchronously by the relay worker.
        """
        # completion_data is already an EventEnvelope from event_processor.py
        # Extract aggregate information from the event data
        aggregate_id = str(correlation_id)  # Default to correlation_id
        if hasattr(completion_data, "data") and hasattr(completion_data.data, "entity_id"):
            aggregate_id = str(completion_data.data.entity_id)

        # Store in outbox for transactional safety (TRUE OUTBOX PATTERN)
        await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="cj_batch",
            event_type=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            event_data=completion_data.model_dump(mode='json'),  # Convert EventEnvelope to JSON-serializable dict
            topic=self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            event_key=aggregate_id,
        )

        # Wake up the relay worker via Redis notification
        try:
            redis_key = f"outbox:wake:{self.settings.SERVICE_NAME}"
            await self.redis_client.lpush(redis_key, "1")
            logger.debug("Relay worker notified via Redis")
        except Exception as e:
            # Log but don't fail - the relay worker will still poll eventually
            logger.warning(f"Failed to notify relay worker via Redis: {e}")
        
        logger.info(
            "CJ assessment completion event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_id": aggregate_id,
                "topic": self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC,
            }
        )

    async def publish_assessment_failed(
        self,
        failure_data: Any,
        correlation_id: UUID,
    ) -> None:
        """Publish CJ assessment failure event using TRUE OUTBOX PATTERN.

        Args:
            failure_data: The CJ assessment failure event data (already an EventEnvelope)
            correlation_id: Correlation ID for event tracing

        Note:
            This uses the transactional outbox pattern to ensure atomic consistency
            between database state and event publishing. Events are stored in the
            outbox table and published asynchronously by the relay worker.
        """
        # failure_data is already an EventEnvelope from event_processor.py
        # Extract aggregate information from the event data
        aggregate_id = str(correlation_id)  # Default to correlation_id
        if hasattr(failure_data, "data") and hasattr(failure_data.data, "entity_id"):
            aggregate_id = str(failure_data.data.entity_id)

        # Store in outbox for transactional safety (TRUE OUTBOX PATTERN)
        await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type="cj_batch",
            event_type=self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
            event_data=failure_data.model_dump(mode='json'),  # Convert EventEnvelope to JSON-serializable dict
            topic=self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
            event_key=aggregate_id,
        )

        # Wake up the relay worker via Redis notification
        try:
            redis_key = f"outbox:wake:{self.settings.SERVICE_NAME}"
            await self.redis_client.lpush(redis_key, "1")
            logger.debug("Relay worker notified via Redis")
        except Exception as e:
            # Log but don't fail - the relay worker will still poll eventually
            logger.warning(f"Failed to notify relay worker via Redis: {e}")
        
        logger.info(
            "CJ assessment failure event stored in outbox",
            extra={
                "correlation_id": str(correlation_id),
                "aggregate_id": aggregate_id,
                "topic": self.settings.CJ_ASSESSMENT_FAILED_TOPIC,
            }
        )

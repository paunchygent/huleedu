"""Event publisher implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJEventPublisherProtocol,
enabling the CJ service to publish assessment results and failures to Kafka.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from config import Settings
from huleedu_service_libs.kafka_client import KafkaBus

from services.cj_assessment_service.protocols import CJEventPublisherProtocol


class CJEventPublisherImpl(CJEventPublisherProtocol):
    """Implementation of CJEventPublisherProtocol for publishing CJ events."""

    def __init__(self, kafka_bus: KafkaBus, settings: Settings) -> None:
        """Initialize the event publisher with Kafka bus and settings."""
        self.kafka_bus = kafka_bus
        self.settings = settings

    async def publish_assessment_completed(
        self, completion_data: Any, correlation_id: UUID | None
    ) -> None:
        """Publish CJ assessment completion event to Kafka.

        Args:
            completion_data: The CJ assessment completion event data
            correlation_id: Optional correlation ID for event tracing

        Raises:
            Exception: If publishing fails
        """
        topic = self.settings.CJ_ASSESSMENT_COMPLETED_TOPIC

        # Create EventEnvelope for proper event structure
        from common_core.events.envelope import EventEnvelope

        envelope = EventEnvelope[Any](
            event_type=topic,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=completion_data,
        )

        # Use correlation_id as partition key if available
        key = str(correlation_id) if correlation_id else None

        try:
            await self.kafka_bus.publish(topic, envelope, key=key)
        except Exception as e:
            raise Exception(f"Failed to publish CJ assessment completion event: {e!s}") from e

    async def publish_assessment_failed(
        self, failure_data: Any, correlation_id: UUID | None
    ) -> None:
        """Publish CJ assessment failure event to Kafka.

        Args:
            failure_data: The CJ assessment failure event data
            correlation_id: Optional correlation ID for event tracing

        Raises:
            Exception: If publishing fails
        """
        topic = self.settings.CJ_ASSESSMENT_FAILED_TOPIC

        # Create EventEnvelope for proper event structure
        from common_core.events.envelope import EventEnvelope

        envelope = EventEnvelope[Any](
            event_type=topic,
            source_service=self.settings.SERVICE_NAME,
            correlation_id=correlation_id,
            data=failure_data,
        )

        # Use correlation_id as partition key if available
        key = str(correlation_id) if correlation_id else None

        try:
            await self.kafka_bus.publish(topic, envelope, key=key)
        except Exception as e:
            raise Exception(f"Failed to publish CJ assessment failure event: {e!s}") from e

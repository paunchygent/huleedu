"""Event publisher implementation for the CJ Assessment Service.

This module provides the concrete implementation of CJEventPublisherProtocol,
enabling the CJ service to publish assessment results and failures to Kafka.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from aiokafka import AIOKafkaProducer
from config import Settings

from services.cj_assessment_service.protocols import CJEventPublisherProtocol


class CJEventPublisherImpl(CJEventPublisherProtocol):
    """Implementation of CJEventPublisherProtocol for publishing CJ events."""

    def __init__(self, producer: AIOKafkaProducer, settings: Settings) -> None:
        """Initialize the event publisher with Kafka producer and settings."""
        self.producer = producer
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

        # Convert completion_data to JSON bytes
        if hasattr(completion_data, "model_dump"):
            # Pydantic model
            message_data = completion_data.model_dump(mode="json")
        else:
            # Dict or other JSON-serializable object
            message_data = completion_data

        message_bytes = json.dumps(message_data).encode("utf-8")

        # Use correlation_id as partition key if available
        key = str(correlation_id).encode("utf-8") if correlation_id else None

        try:
            await self.producer.send_and_wait(topic, message_bytes, key=key)
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

        # Convert failure_data to JSON bytes
        if hasattr(failure_data, "model_dump"):
            # Pydantic model
            message_data = failure_data.model_dump(mode="json")
        else:
            # Dict or other JSON-serializable object
            message_data = failure_data

        message_bytes = json.dumps(message_data).encode("utf-8")

        # Use correlation_id as partition key if available
        key = str(correlation_id).encode("utf-8") if correlation_id else None

        try:
            await self.producer.send_and_wait(topic, message_bytes, key=key)
        except Exception as e:
            raise Exception(f"Failed to publish CJ assessment failure event: {e!s}") from e

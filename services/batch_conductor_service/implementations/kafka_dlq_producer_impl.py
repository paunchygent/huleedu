"""
Kafka Dead Letter Queue (DLQ) producer implementation for BCS.

Handles publishing failed messages to DLQ topics following the schema:
{
  "schema_version": 1,
  "failed_event_envelope": { "...": "full original envelope" },
  "dlq_reason": "DependencyCycleDetected",
  "timestamp": "2025-06-18T20:40:00Z",
  "service": "batch_conductor_service"
}
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.kafka_client import KafkaBus
from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.protocols import DlqProducerProtocol

logger = create_service_logger("bcs.dlq_producer")


class KafkaDlqProducerImpl(DlqProducerProtocol):
    """
    Kafka implementation for Dead Letter Queue message production.

    Publishes failed processing messages to DLQ topics for manual inspection
    and potential reprocessing after issues are resolved.
    """

    def __init__(self, kafka_bus: KafkaBus, timeout_seconds: float = 5.0):
        self.kafka_bus = kafka_bus
        self._timeout_seconds = timeout_seconds

    def _extract_message_key(
        self, failed_event_envelope: EventEnvelope[Any] | dict[Any, Any]
    ) -> str | None:
        """
        Extract message key for Kafka partitioning from event envelope.

        Priority order: batch_id > entity_ref.parent_id > entity_ref.entity_id

        Args:
            failed_event_envelope: EventEnvelope or dict containing event data

        Returns:
            Message key string for Kafka partitioning, or None if no suitable key found
        """
        try:
            # Extract data from EventEnvelope or dict
            if isinstance(failed_event_envelope, EventEnvelope):
                data = failed_event_envelope.data
                # Convert Pydantic model to dict if needed
                if hasattr(data, "model_dump"):
                    data = data.model_dump()
                elif not isinstance(data, dict):
                    return None
            elif isinstance(failed_event_envelope, dict):
                data = failed_event_envelope.get("data", {})
            else:
                return None

            if not isinstance(data, dict):
                return None

            # Priority 1: Direct batch_id
            if "batch_id" in data and data["batch_id"]:
                return str(data["batch_id"])

            # Priority 2: entity_ref.parent_id (typically batch identifier)
            if "entity_ref" in data and isinstance(data["entity_ref"], dict):
                entity_ref = data["entity_ref"]
                if "parent_id" in entity_ref and entity_ref["parent_id"]:
                    return str(entity_ref["parent_id"])

                # Priority 3: entity_ref.entity_id (fallback)
                if "entity_id" in entity_ref and entity_ref["entity_id"]:
                    return str(entity_ref["entity_id"])

            return None

        except Exception as e:
            logger.warning(
                f"Failed to extract message key for partitioning: {e}",
                extra={"error": str(e)},
                exc_info=True,
            )
            return None

    async def publish_to_dlq(
        self,
        base_topic: str,
        failed_event_envelope: EventEnvelope[Any] | dict[Any, Any],
        dlq_reason: str,
        additional_metadata: dict[str, Any] | None = None,
    ) -> bool:
        """
        Publish a failed message to Dead Letter Queue.

        Creates DLQ topic as base_topic + ".DLQ" and publishes message with
        standardized DLQ schema including original envelope and failure reason.
        """
        try:
            # Construct DLQ topic name
            dlq_topic = f"{base_topic}.DLQ"

            # Build DLQ message following task specification schema
            if isinstance(failed_event_envelope, EventEnvelope):
                envelope_data = failed_event_envelope.model_dump(mode="json")
                event_id = str(failed_event_envelope.event_id)
            else:
                # Handle dict case
                envelope_data = failed_event_envelope
                event_id = str(failed_event_envelope.get("event_id", "unknown"))

            dlq_message = {
                "schema_version": 1,
                "failed_event_envelope": envelope_data,
                "dlq_reason": dlq_reason,
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "batch_conductor_service",
            }

            # Add additional metadata if provided
            if additional_metadata:
                dlq_message["additional_metadata"] = additional_metadata

            # Extract message key for Kafka partitioning
            message_key = self._extract_message_key(failed_event_envelope)

            # Publish to DLQ topic with bounded timeout
            try:
                await asyncio.wait_for(
                    self.kafka_bus.producer.send(
                        topic=dlq_topic,
                        key=message_key,
                        value=json.dumps(dlq_message),
                        headers={},
                    ),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError:
                logger.error(
                    "DLQ publish timeout",
                    extra={
                        "base_topic": base_topic,
                        "dlq_topic": dlq_topic,
                        "dlq_reason": dlq_reason,
                        "original_event_id": event_id,
                        "timeout_seconds": self._timeout_seconds,
                    },
                )
                return False

            logger.error(
                f"Published message to DLQ: topic={dlq_topic}, reason={dlq_reason}",
                extra={
                    "dlq_topic": dlq_topic,
                    "dlq_reason": dlq_reason,
                    "original_event_id": event_id,
                    "message_key": message_key,
                },
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to publish message to DLQ: {e}",
                extra={
                    "base_topic": base_topic,
                    "dlq_reason": dlq_reason,
                    "original_event_id": event_id,
                },
                exc_info=True,
            )
            return False

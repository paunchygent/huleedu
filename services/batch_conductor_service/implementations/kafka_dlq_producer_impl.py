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

    def __init__(self, kafka_bus: KafkaBus):
        self.kafka_bus = kafka_bus

    async def publish_to_dlq(
        self,
        base_topic: str,
        failed_event_envelope: EventEnvelope[Any],
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
            dlq_message = {
                "schema_version": 1,
                "failed_event_envelope": failed_event_envelope.model_dump(mode="json"),
                "dlq_reason": dlq_reason,
                "timestamp": datetime.now(UTC).isoformat(),
                "service": "batch_conductor_service",
            }

            # Add additional metadata if provided
            if additional_metadata:
                dlq_message["additional_metadata"] = additional_metadata

            # Use original event's key if available, otherwise use batch_id or entity_id
            message_key = None
            if hasattr(failed_event_envelope, "data") and failed_event_envelope.data:
                # Try to extract batch_id or entity_id for partitioning
                data = failed_event_envelope.data
                if hasattr(data, "batch_id"):
                    message_key = data.batch_id
                elif hasattr(data, "entity_ref") and hasattr(data.entity_ref, "parent_id"):
                    message_key = data.entity_ref.parent_id
                elif hasattr(data, "entity_ref") and hasattr(data.entity_ref, "entity_id"):
                    message_key = data.entity_ref.entity_id

            # Publish to DLQ topic
            await self.kafka_bus.produce(
                topic=dlq_topic, key=message_key, value=json.dumps(dlq_message), headers={}
            )

            logger.error(
                f"Published message to DLQ: topic={dlq_topic}, reason={dlq_reason}",
                extra={
                    "dlq_topic": dlq_topic,
                    "dlq_reason": dlq_reason,
                    "original_event_id": str(failed_event_envelope.event_id),
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
                    "original_event_id": str(failed_event_envelope.event_id)
                    if failed_event_envelope
                    else "unknown",
                },
                exc_info=True,
            )
            return False

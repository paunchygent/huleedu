"""Kafka implementation of ``DlqProducerProtocol`` for Batch Conductor Service.

Uses aiokafka producer to send failed pipeline-resolution events to a dedicated
`<base_topic>.DLQ` topic. The original event envelope is embedded verbatim so
that consumers can re-process or inspect it. The producer itself purposely
remains very small because higher-level components are responsible for
constructing the envelope and failure reason.

The component is provided via Dishka (Scope.APP) in ``di.py``.
"""

from __future__ import annotations

import json
from typing import Final

from aiokafka import AIOKafkaProducer
from huleedu_service_libs.logging_utils import create_service_logger
from services.batch_conductor_service.protocols import DlqProducerProtocol

logger = create_service_logger("bcs.dlq_producer")


class KafkaDlqProducerImpl(DlqProducerProtocol):
    """Default dead-letter producer that pushes JSON messages to Kafka."""

    def __init__(
        self,
        bootstrap_servers: str,
        *,
        base_topic: str,
        client_id: str = "bcs-dlq-producer",
    ) -> None:
        self._producer: Final = AIOKafkaProducer(bootstrap_servers=bootstrap_servers, client_id=client_id)
        # DLQ topic follows <base_topic>.DLQ convention
        self._dlq_topic: Final = f"{base_topic}.DLQ"
        self._started: bool = False

    async def start(self) -> None:  # noqa: D401
        if not self._started:
            await self._producer.start()
            self._started = True
            logger.info("Kafka DLQ producer started", extra={"topic": self._dlq_topic})

    async def stop(self) -> None:  # noqa: D401
        if self._started:
            await self._producer.stop()
            self._started = False
            logger.info("Kafka DLQ producer stopped")

    async def publish(self, envelope: dict, reason: str) -> None:  # noqa: D401
        if not self._started:
            await self.start()

        payload = {
            "schema_version": 1,
            "failed_event_envelope": envelope,
            "dlq_reason": reason,
        }
        try:
            await self._producer.send_and_wait(
                topic=self._dlq_topic,
                key=(envelope.get("batch_id") or "unknown").encode(),
                value=json.dumps(payload).encode(),
            )
            logger.info("Published message to DLQ", extra={"reason": reason})
        except Exception as exc:  # pragma: no cover – network issues mostly
            logger.error("Failed to publish DLQ message: %s", exc, exc_info=True)

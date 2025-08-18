from __future__ import annotations

from typing import Any
from uuid import UUID

from huleedu_service_libs.error_handling import raise_external_service_error
from huleedu_service_libs.logging_utils import create_service_logger

logger = create_service_logger("identity_service.outbox_manager")


class OutboxManager:
    """Identity Service outbox manager wrapper following TRUE OUTBOX PATTERN."""

    def __init__(self, outbox_repository, redis_client) -> None:
        self.outbox_repository = outbox_repository
        self.redis_client = redis_client

    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,
        topic: str,
    ) -> None:
        if not self.outbox_repository:
            raise_external_service_error(
                service="identity_service",
                operation="publish_to_outbox",
                external_service="outbox_repository",
                message="Outbox repository not configured",
                correlation_id=getattr(event_data, "correlation_id", UUID(int=0)),
                aggregate_id=aggregate_id,
                event_type=event_type,
            )

        serialized = (
            event_data.model_dump(mode="json") if hasattr(event_data, "model_dump") else event_data
        )
        key = aggregate_id
        outbox_id = await self.outbox_repository.add_event(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            event_data=serialized,
            topic=topic,
            event_key=key,
        )
        logger.debug(
            "Stored event in outbox",
            extra={"outbox_id": str(outbox_id), "aggregate_id": aggregate_id, "topic": topic},
        )
        await self.notify_relay_worker()

    async def notify_relay_worker(self) -> None:
        try:
            await self.redis_client.lpush("outbox:wake:identity_service", "1")
        except Exception as e:
            logger.warning("Relay worker notify failed", extra={"error": str(e)})

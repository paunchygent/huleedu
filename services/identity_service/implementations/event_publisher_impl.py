from __future__ import annotations

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_models import UserRegisteredV1
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.protocols import IdentityEventPublisherProtocol

logger = create_service_logger("identity_service.event_publisher")


class DefaultIdentityEventPublisher(IdentityEventPublisherProtocol):
    def __init__(self, outbox_manager, source_service_name: str) -> None:
        self.outbox_manager = outbox_manager
        self.source_service_name = source_service_name

    async def publish_user_registered(self, user: dict, correlation_id: str) -> None:
        payload = UserRegisteredV1(
            user_id=user["id"],
            org_id=user.get("org_id"),
            email=user["email"],
            registered_at=user.get("registered_at"),
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[UserRegisteredV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
            source_service=self.source_service_name,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
        )

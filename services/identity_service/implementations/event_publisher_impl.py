from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_enums import LoginFailureReason
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    EmailVerifiedV1,
    LoginFailedV1,
    LoginSucceededV1,
    PasswordResetCompletedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.identity_service.implementations.outbox_manager import OutboxManager
from services.identity_service.protocols import IdentityEventPublisherProtocol

logger = create_service_logger("identity_service.event_publisher")


class DefaultIdentityEventPublisher(IdentityEventPublisherProtocol):
    def __init__(self, outbox_manager: OutboxManager, source_service_name: str) -> None:
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
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
        )

    async def publish_login_succeeded(self, user: dict, correlation_id: str) -> None:
        payload = LoginSucceededV1(
            user_id=user["id"],
            org_id=user.get("org_id"),
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[LoginSucceededV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_LOGIN_SUCCEEDED),
        )

    async def publish_login_failed(
        self, email: str, failure_reason: LoginFailureReason, correlation_id: str
    ) -> None:
        payload = LoginFailedV1(
            email=email,
            reason=failure_reason,
            timestamp=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[LoginFailedV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_LOGIN_FAILED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="login_attempt",
            aggregate_id=email,  # Use email as aggregate_id for failed attempts
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_LOGIN_FAILED),
        )

    async def publish_email_verification_requested(
        self, user: dict, verification_token: str, expires_at: datetime, correlation_id: str
    ) -> None:
        payload = EmailVerificationRequestedV1(
            user_id=user["id"],
            email=user["email"],
            verification_token=verification_token,
            expires_at=expires_at,
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[EmailVerificationRequestedV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFICATION_REQUESTED),
        )

    async def publish_email_verified(self, user: dict, correlation_id: str) -> None:
        payload = EmailVerifiedV1(
            user_id=user["id"],
            verified_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[EmailVerifiedV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFIED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_EMAIL_VERIFIED),
        )

    async def publish_password_reset_requested(
        self, user: dict, token_id: str, expires_at: datetime, correlation_id: str
    ) -> None:
        payload = PasswordResetRequestedV1(
            user_id=user["id"],
            email=user["email"],
            token_id=token_id,
            expires_at=expires_at,
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[PasswordResetRequestedV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_REQUESTED),
        )

    async def publish_password_reset_completed(self, user: dict, correlation_id: str) -> None:
        payload = PasswordResetCompletedV1(
            user_id=user["id"],
            reset_at=datetime.now(UTC),
            correlation_id=correlation_id,
        )
        envelope = EventEnvelope[PasswordResetCompletedV1](
            event_type=topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_COMPLETED),
            source_service=self.source_service_name,
            correlation_id=UUID(correlation_id) if isinstance(correlation_id, str) else correlation_id,
            data=payload,
        )
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=user["id"],
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.IDENTITY_PASSWORD_RESET_COMPLETED),
        )

    async def publish_user_logged_out(self, user_id: str, correlation_id: str) -> None:
        # For now, we'll log the event since UserLoggedOutV1 may not exist yet
        logger.info(
            "User logged out",
            extra={
                "user_id": user_id,
                "correlation_id": correlation_id,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        # In production, this would publish a UserLoggedOutV1 event similar to the others

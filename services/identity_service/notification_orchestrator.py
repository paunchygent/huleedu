"""Notification orchestrator for Identity Service email bridge.

This module provides event transformation from Identity-specific events
to generic email notification requests, bridging the service boundary
between Identity Service and Email Service.
"""

from __future__ import annotations

from uuid import uuid4

from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from huleedu_service_libs.logging_utils import create_service_logger
from huleedu_service_libs.outbox.manager import OutboxManager

logger = create_service_logger("identity_service.notification_orchestrator")


class NotificationOrchestrator:
    """Orchestrates transformation of Identity events to Email notifications.

    This component listens to Identity Service's own published events and transforms
    them into generic email notification requests that the Email Service can consume,
    effectively bridging the service boundary gap.
    """

    def __init__(self, outbox_manager: OutboxManager) -> None:
        self.outbox_manager = outbox_manager

    async def handle_email_verification_requested(
        self, event: EmailVerificationRequestedV1
    ) -> None:
        """Transform email verification request to notification request."""

        # Generate unique message ID for email tracking
        message_id = f"verification-{event.user_id}-{uuid4().hex[:8]}"

        # Create email notification request
        notification = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="verification",
            to=event.email,
            variables={
                "user_name": event.email.split("@")[0].title(),  # Extract name from email
                "verification_link": f"https://hule.education/verify?token={event.verification_token}",
                "verification_token": event.verification_token,
                "expires_in": "24 hours",  # Human-readable expiration
                "expires_at": event.expires_at.isoformat(),
                "current_year": "2025",
            },
            category="verification",
            correlation_id=event.correlation_id,
        )

        # Create event envelope for publishing
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_type=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            source_service="identity_service",
            correlation_id=event.correlation_id,
            data=notification,
        )

        # Publish to outbox for reliable delivery
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=event.user_id,
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
        )

        logger.info(
            f"Email verification notification published: {message_id}",
            extra={
                "user_id": event.user_id,
                "email": str(event.email),
                "message_id": message_id,
                "correlation_id": event.correlation_id,
            },
        )

    async def handle_password_reset_requested(self, event: PasswordResetRequestedV1) -> None:
        """Transform password reset request to notification request."""

        # Generate unique message ID for email tracking
        message_id = f"password-reset-{event.user_id}-{uuid4().hex[:8]}"

        # Create email notification request
        notification = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="password_reset",
            to=event.email,
            variables={
                "user_name": event.email.split("@")[0].title(),  # Extract name from email
                "reset_link": f"https://hule.education/reset-password?token={event.token_id}",
                "token_id": event.token_id,
                "expires_in": "1 hour",  # Human-readable expiration
                "expires_at": event.expires_at.isoformat(),
                "current_year": "2025",
            },
            category="password_reset",
            correlation_id=event.correlation_id,
        )

        # Create event envelope for publishing
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_type=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            source_service="identity_service",
            correlation_id=event.correlation_id,
            data=notification,
        )

        # Publish to outbox for reliable delivery
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=event.user_id,
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
        )

        logger.info(
            f"Password reset notification published: {message_id}",
            extra={
                "user_id": event.user_id,
                "email": str(event.email),
                "message_id": message_id,
                "correlation_id": event.correlation_id,
            },
        )

    async def handle_user_registered(self, event: UserRegisteredV1) -> None:
        """Transform user registration to welcome notification."""

        # Generate unique message ID for email tracking
        message_id = f"welcome-{event.user_id}-{uuid4().hex[:8]}"

        # Create email notification request
        notification = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="welcome",
            to=event.email,
            variables={
                "user_name": event.email.split("@")[0].title(),  # Extract name from email
                "first_name": event.email.split("@")[0].title(),  # Template compatibility
                "dashboard_link": "https://app.hule.education/dashboard",
                "org_name": "HuleEdu",
                "registered_at": event.registered_at.isoformat(),
                "current_year": "2025",
            },
            category="system",
            correlation_id=event.correlation_id,
        )

        # Create event envelope for publishing
        envelope = EventEnvelope[NotificationEmailRequestedV1](
            event_type=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
            source_service="identity_service",
            correlation_id=event.correlation_id,
            data=notification,
        )

        # Publish to outbox for reliable delivery
        await self.outbox_manager.publish_to_outbox(
            aggregate_type="user",
            aggregate_id=event.user_id,
            event_type=envelope.event_type,
            event_data=envelope,
            topic=topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED),
        )

        logger.info(
            f"Welcome email notification published: {message_id}",
            extra={
                "user_id": event.user_id,
                "email": str(event.email),
                "message_id": message_id,
                "correlation_id": event.correlation_id,
            },
        )

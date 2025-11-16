"""Email Service event contracts for notification and delivery tracking.

The models in this module formalize the email workflow contract documented in
`libs/common_core/docs/event-registry.md`. They describe the full lifecycle of
a transactional email across three events:

1. :class:`NotificationEmailRequestedV1` – upstream service request published to
   ``huleedu.email.notification.requested.v1``
2. :class:`EmailSentV1` – confirmation from Email Service that the provider
   accepted the message
3. :class:`EmailDeliveryFailedV1` – delivery failure emitted with provider
   diagnostics

These events are consumed by the Email Service, analytics pipelines, and audit
subsystems to keep student/teacher notifications reliable and traceable.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Literal

from pydantic import BaseModel, EmailStr, Field


class NotificationEmailRequestedV1(BaseModel):
    """Email send request event for transactional notifications.

    **Producer services**: Identity Service, Class Management Service,
    Batch Orchestrator Service, or any service that needs transactional email.

    **Consumer service**: Email Service.

    **Topic**: ``huleedu.email.notification.requested.v1``

    Workflow:
    1. Service publishes :class:`NotificationEmailRequestedV1` to Kafka.
    2. Email Service consumes the event and sends via external provider (Resend,
       SendGrid, etc.).
    3. Email Service publishes :class:`EmailSentV1` or
       :class:`EmailDeliveryFailedV1` based on provider response.
    """

    message_id: str = Field(
        description="Unique message identifier for idempotency and tracking. Generate with uuid4()."
    )
    template_id: str = Field(
        description=(
            "Email template identifier recognized by Email Service. "
            "Templates define subject, HTML body, and variable placeholders."
        )
    )
    to: EmailStr = Field(description="Recipient email address. Validated by Pydantic EmailStr.")
    variables: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Template variables for email personalization (e.g., user_name, verification_link). "
            "Keys match template placeholders."
        ),
    )
    category: Literal[
        "verification",
        "password_reset",
        "receipt",
        "teacher_notification",
        "system",
    ] = Field(
        description=(
            "Email category for analytics and filtering. "
            "Determines email priority and handling rules."
        )
    )
    correlation_id: str = Field(
        description=(
            "Distributed tracing ID. "
            "MUST propagate from originating request for end-to-end correlation."
        )
    )


class EmailSentV1(BaseModel):
    """Email successfully sent confirmation event.

    **Producer service**: Email Service.

    **Consumer services**: Analytics, Audit logging, Result Aggregator
    pipelines that track notification SLAs.

    **Topic**: ``huleedu.email.sent.v1``

    Published after Email Service receives success confirmation from the external
    provider. Used for analytics, billing tracking, and audit trails, and it
    allows clients to correlate request-to-delivery using ``message_id`` and
    ``correlation_id``.
    """

    message_id: str = Field(
        description=(
            "Message identifier from original NotificationEmailRequestedV1. "
            "Links request to delivery confirmation."
        )
    )
    provider: str = Field(
        description=(
            "External email provider used (e.g., resend, sendgrid). "
            "For analytics and provider reliability tracking."
        )
    )
    sent_at: datetime = Field(
        description="Timestamp when email was successfully sent by provider. UTC timezone."
    )
    correlation_id: str = Field(
        description="Distributed tracing ID from original request. Enables end-to-end correlation."
    )


class EmailDeliveryFailedV1(BaseModel):
    """Email delivery failure event for error handling and monitoring.

    **Producer service**: Email Service.

    **Consumer services**: Analytics, error handling systems,
    Monitoring/Alerting pipelines.

    **Topic**: ``huleedu.email.delivery.failed.v1``

    Published when Email Service fails to deliver via the configured provider.
    Triggers retry logic, alerting, and provider reliability monitoring.
    """

    message_id: str = Field(
        description=(
            "Message identifier from original NotificationEmailRequestedV1. "
            "Links request to failure event."
        )
    )
    provider: str = Field(
        description=(
            "External email provider that failed (e.g., resend, sendgrid). "
            "For provider reliability analysis."
        )
    )
    failed_at: datetime = Field(
        description="Timestamp when delivery failure occurred. UTC timezone."
    )
    reason: str = Field(
        description=(
            "Failure reason from provider (e.g., invalid email, rate limit, provider error). "
            "For error analysis and retry logic."
        )
    )
    correlation_id: str = Field(
        description=(
            "Distributed tracing ID from original request. "
            "Enables end-to-end error correlation."
        )
    )

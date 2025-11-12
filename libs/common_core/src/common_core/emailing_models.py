"""Email Service event contracts for notification and delivery tracking.

Defines event models for the email workflow: request → sent → delivery status.
Used by Identity Service, Class Management Service, Batch Orchestrator Service,
and other services that need to send transactional emails.

Producer: Identity, CMS, BOS, other services
Consumer: Email Service (for NotificationEmailRequestedV1), Analytics/Audit (for sent/failed)
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Literal

from pydantic import BaseModel, EmailStr, Field


class NotificationEmailRequestedV1(BaseModel):
    """Email send request event for transactional notifications.

    Producer: Identity Service, Class Management Service, Batch Orchestrator Service
    Consumer: Email Service
    Topic: huleedu.email.notification.requested.v1

    Workflow:
    1. Service publishes NotificationEmailRequestedV1 event to Kafka
    2. Email Service consumes event and sends via external provider (Resend, SendGrid)
    3. Email Service publishes EmailSentV1 or EmailDeliveryFailedV1 based on result
    """

    message_id: str = Field(
        description="Unique message identifier for idempotency and tracking. Generate with uuid4()."
    )
    template_id: str = Field(
        description="Email template identifier recognized by Email Service. Templates define subject, HTML body, and variable placeholders."
    )
    to: EmailStr = Field(description="Recipient email address. Validated by Pydantic EmailStr.")
    variables: Dict[str, str] = Field(
        default_factory=dict,
        description="Template variables for email personalization (e.g., user_name, verification_link). Keys match template placeholders.",
    )
    category: Literal[
        "verification",
        "password_reset",
        "receipt",
        "teacher_notification",
        "system",
    ] = Field(
        description="Email category for analytics and filtering. Determines email priority and handling rules."
    )
    correlation_id: str = Field(
        description="Distributed tracing ID. MUST propagate from originating request for end-to-end correlation."
    )


class EmailSentV1(BaseModel):
    """Email successfully sent confirmation event.

    Producer: Email Service
    Consumer: Analytics, Audit logging
    Topic: huleedu.email.sent.v1

    Published after Email Service successfully delivers email via external provider.
    Used for analytics, billing tracking, and audit trails.
    """

    message_id: str = Field(
        description="Message identifier from original NotificationEmailRequestedV1. Links request to delivery confirmation."
    )
    provider: str = Field(
        description="External email provider used (e.g., resend, sendgrid). For analytics and provider reliability tracking."
    )
    sent_at: datetime = Field(
        description="Timestamp when email was successfully sent by provider. UTC timezone."
    )
    correlation_id: str = Field(
        description="Distributed tracing ID from original request. Enables end-to-end correlation."
    )


class EmailDeliveryFailedV1(BaseModel):
    """Email delivery failure event for error handling and monitoring.

    Producer: Email Service
    Consumer: Analytics, Error handling systems, Monitoring/Alerting
    Topic: huleedu.email.delivery.failed.v1

    Published when Email Service fails to deliver email via external provider.
    Triggers error handling workflows and provider reliability monitoring.
    """

    message_id: str = Field(
        description="Message identifier from original NotificationEmailRequestedV1. Links request to failure event."
    )
    provider: str = Field(
        description="External email provider that failed (e.g., resend, sendgrid). For provider reliability analysis."
    )
    failed_at: datetime = Field(
        description="Timestamp when delivery failure occurred. UTC timezone."
    )
    reason: str = Field(
        description="Failure reason from provider (e.g., invalid email, rate limit, provider error). For error analysis and retry logic."
    )
    correlation_id: str = Field(
        description="Distributed tracing ID from original request. Enables end-to-end error correlation."
    )

"""Email event processor for business logic orchestration.

This module provides the core email processing workflow, coordinating
template rendering, email sending, and event publishing.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from common_core.emailing_models import (
    EmailDeliveryFailedV1,
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import (
    raise_processing_error,
    raise_validation_error,
)
from huleedu_service_libs.logging_utils import create_service_logger

from services.email_service.config import Settings
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.protocols import (
    EmailProvider,
    EmailRecord,
    EmailRepository,
    EmailSendResult,
    TemplateRenderer,
)

logger = create_service_logger("email_service.event_processor")


class EmailEventProcessor:
    """Processes email notification requests with full workflow orchestration.

    Coordinates template rendering, email sending, database updates, and event
    publishing following domain-driven design principles.
    """

    def __init__(
        self,
        repository: EmailRepository,
        template_renderer: TemplateRenderer,
        email_provider: EmailProvider,
        outbox_manager: OutboxManager,
        settings: Settings,
    ):
        self.repository = repository
        self.template_renderer = template_renderer
        self.email_provider = email_provider
        self.outbox_manager = outbox_manager
        self.settings = settings

    async def process_email_request(
        self,
        request: NotificationEmailRequestedV1,
    ) -> None:
        """Process a notification email request with full workflow.

        Args:
            request: Email notification request from Kafka event

        Raises:
            ValidationError: For invalid request data
            ProcessingError: For processing failures
        """
        logger.info(
            f"Processing email request - message_id: {request.message_id}, "
            f"template: {request.template_id}, category: {request.category}"
        )

        try:
            # 1. Validate template exists
            if not await self.template_renderer.template_exists(request.template_id):
                raise_validation_error(
                    service="email_service",
                    operation="process_email_request",
                    field="template_id",
                    message=f"Template not found: {request.template_id}",
                    correlation_id=UUID(request.correlation_id),
                )

            # 2. Create initial email record
            email_record = EmailRecord(
                message_id=request.message_id,
                to_address=request.to,
                from_address=self.settings.DEFAULT_FROM_EMAIL,
                from_name=self.settings.DEFAULT_FROM_NAME,
                subject="",  # Will be set after template rendering
                template_id=request.template_id,
                category=request.category,
                variables=request.variables,
                correlation_id=request.correlation_id,
                status="pending",
                created_at=datetime.utcnow(),
            )

            await self.repository.create_email_record(email_record)

            # 3. Update status to processing
            await self.repository.update_status(
                message_id=request.message_id,
                status="processing",
            )

            # 4. Render email template
            logger.debug(f"Rendering template: {request.template_id}")
            rendered = await self.template_renderer.render(
                template_id=request.template_id,
                variables=request.variables,
            )

            # 5. Send email via provider
            logger.debug(f"Sending email via {self.email_provider.get_provider_name()}")
            send_result = await self.email_provider.send_email(
                to=request.to,
                subject=rendered.subject,
                html_content=rendered.html_content,
                text_content=rendered.text_content,
                from_email=self.settings.DEFAULT_FROM_EMAIL,
                from_name=self.settings.DEFAULT_FROM_NAME,
            )

            # 6. Update record based on send result
            if send_result.success:
                await self._handle_send_success(
                    request=request,
                    send_result=send_result,
                    rendered_subject=rendered.subject,
                )
            else:
                await self._handle_send_failure(
                    request=request,
                    send_result=send_result,
                )

        except Exception as e:
            logger.error(
                f"Failed to process email request {request.message_id}: {e}",
                exc_info=True,
            )

            # Update record status to failed
            try:
                await self.repository.update_status(
                    message_id=request.message_id,
                    status="failed",
                    failed_at=datetime.utcnow(),
                    failure_reason=str(e),
                )
            except Exception as db_error:
                logger.error(f"Failed to update email record status: {db_error}")

            # Publish failure event
            await self._publish_delivery_failed_event(
                request=request,
                reason=str(e),
            )

            raise_processing_error(
                service="email_service",
                operation="process_email_request",
                message=f"Email processing failed: {e}",
                correlation_id=UUID(request.correlation_id),
            )

    async def _handle_send_success(
        self,
        request: NotificationEmailRequestedV1,
        send_result: EmailSendResult,
        rendered_subject: str,
    ) -> None:
        """Handle successful email send."""
        logger.info(f"Email sent successfully: {request.message_id}")

        # Update database record
        await self.repository.update_status(
            message_id=request.message_id,
            status="sent",
            provider_message_id=send_result.provider_message_id,
            sent_at=datetime.utcnow(),
        )

        # Publish success event
        event_data = EmailSentV1(
            message_id=request.message_id,
            provider=self.email_provider.get_provider_name(),
            sent_at=datetime.utcnow(),
            correlation_id=request.correlation_id,
        )

        envelope = EventEnvelope[EmailSentV1](
            event_type=topic_name(ProcessingEvent.EMAIL_SENT),
            source_service="email_service",
            correlation_id=UUID(request.correlation_id),
            data=event_data,
        )

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id=request.message_id,
            event_type=topic_name(ProcessingEvent.EMAIL_SENT),
            event_data=envelope,
            topic=topic_name(ProcessingEvent.EMAIL_SENT),
        )

        logger.info(f"Published EMAIL_SENT event for message: {request.message_id}")

    async def _handle_send_failure(
        self,
        request: NotificationEmailRequestedV1,
        send_result: EmailSendResult,
    ) -> None:
        """Handle failed email send."""
        logger.warning(
            f"Email send failed: {request.message_id}, reason: {send_result.error_message}"
        )

        # Update database record
        await self.repository.update_status(
            message_id=request.message_id,
            status="failed",
            failed_at=datetime.utcnow(),
            failure_reason=send_result.error_message,
        )

        # Publish failure event
        await self._publish_delivery_failed_event(
            request=request,
            reason=send_result.error_message or "Unknown provider error",
        )

    async def _publish_delivery_failed_event(
        self,
        request: NotificationEmailRequestedV1,
        reason: str,
    ) -> None:
        """Publish email delivery failed event."""
        event_data = EmailDeliveryFailedV1(
            message_id=request.message_id,
            provider=self.email_provider.get_provider_name(),
            failed_at=datetime.utcnow(),
            reason=reason,
            correlation_id=request.correlation_id,
        )

        envelope = EventEnvelope[EmailDeliveryFailedV1](
            event_type=topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED),
            source_service="email_service",
            correlation_id=UUID(request.correlation_id),
            data=event_data,
        )

        await self.outbox_manager.publish_to_outbox(
            aggregate_type="email_message",
            aggregate_id=request.message_id,
            event_type=topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED),
            event_data=envelope,
            topic=topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED),
        )

        logger.info(f"Published EMAIL_DELIVERY_FAILED event for message: {request.message_id}")

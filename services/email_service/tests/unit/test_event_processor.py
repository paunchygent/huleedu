"""Unit tests for EmailEventProcessor following Rule 075 methodology."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.emailing_models import (
    EmailDeliveryFailedV1,
    EmailSentV1,
    NotificationEmailRequestedV1,
)
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from huleedu_service_libs.error_handling import HuleEduError, create_test_huleedu_error

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from huleedu_service_libs.outbox.manager import OutboxManager
from services.email_service.protocols import (
    EmailProvider,
    EmailRecord,
    EmailRepository,
    EmailSendResult,
    RenderedTemplate,
    TemplateRenderer,
)


class TestEmailEventProcessor:
    """Tests for EmailEventProcessor workflow orchestration."""

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        return AsyncMock(spec=EmailRepository)

    @pytest.fixture
    def mock_template_renderer(self) -> AsyncMock:
        return AsyncMock(spec=TemplateRenderer)

    @pytest.fixture
    def mock_email_provider(self) -> AsyncMock:
        mock = AsyncMock(spec=EmailProvider)
        mock.get_provider_name.return_value = "mock_provider"
        return mock

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        return AsyncMock(spec=OutboxManager)

    @pytest.fixture
    def mock_settings(self) -> Settings:
        settings = AsyncMock(spec=Settings)
        settings.DEFAULT_FROM_EMAIL = "noreply@huleedu.com"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        return settings

    @pytest.fixture
    def event_processor(
        self,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_email_provider: AsyncMock,
        mock_outbox_manager: AsyncMock,
        mock_settings: Settings,
    ) -> EmailEventProcessor:
        return EmailEventProcessor(
            repository=mock_repository,
            template_renderer=mock_template_renderer,
            email_provider=mock_email_provider,
            outbox_manager=mock_outbox_manager,
            settings=mock_settings,
        )

    @pytest.fixture
    def correlation_id(self) -> str:
        return str(uuid4())

    @pytest.fixture
    def sample_rendered_template(self) -> RenderedTemplate:
        return RenderedTemplate(
            subject="Välkommen till HuleEdu - Verifiera din e-post",
            html_content="<p>Hej! Klicka på länken för att verifiera: åäöÅÄÖ</p>",
            text_content="Hej! Klicka på länken för att verifiera: åäöÅÄÖ",
        )

    @pytest.mark.parametrize(
        "template_id, category, to_email",
        [
            ("verification", "verification", "användare@huledu.se"),
            ("password_reset", "password_reset", "lärare@test.com"),
            ("welcome", "system", "student.åäö@example.se"),
        ],
    )
    async def test_process_email_request_success_workflow(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_email_provider: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
        sample_rendered_template: RenderedTemplate,
        template_id: str,
        category: str,
        to_email: str,
    ) -> None:
        """Test successful email processing workflow with various template types."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id=template_id,
            to=to_email,
            variables={"name": "Test Användare", "verification_link": "https://test.se"},
            category=category,
            correlation_id=correlation_id,
        )

        # Configure mocks
        mock_template_renderer.template_exists.return_value = True
        mock_template_renderer.render.return_value = sample_rendered_template
        mock_email_provider.send_email.return_value = EmailSendResult(
            success=True, provider_message_id="provider_123"
        )

        # Act
        await event_processor.process_email_request(request)

        # Assert template validation
        mock_template_renderer.template_exists.assert_called_once_with(template_id)

        # Assert email record creation
        mock_repository.create_email_record.assert_called_once()
        created_record = mock_repository.create_email_record.call_args[0][0]
        assert isinstance(created_record, EmailRecord)
        assert created_record.message_id == message_id
        assert created_record.to_address == to_email
        assert created_record.template_id == template_id
        assert created_record.category == category
        assert created_record.variables == request.variables
        assert created_record.correlation_id == correlation_id
        assert created_record.status == "pending"

        # Assert status updates
        assert mock_repository.update_status.call_count == 2
        # First call: set to processing
        first_call = mock_repository.update_status.call_args_list[0]
        assert first_call.kwargs["message_id"] == message_id
        assert first_call.kwargs["status"] == "processing"
        # Second call: set to sent
        second_call = mock_repository.update_status.call_args_list[1]
        assert second_call.kwargs["message_id"] == message_id
        assert second_call.kwargs["status"] == "sent"
        assert second_call.kwargs["provider_message_id"] == "provider_123"

        # Assert template rendering
        mock_template_renderer.render.assert_called_once_with(
            template_id=template_id, variables=request.variables
        )

        # Assert email sending
        mock_email_provider.send_email.assert_called_once_with(
            to=to_email,
            subject=sample_rendered_template.subject,
            html_content=sample_rendered_template.html_content,
            text_content=sample_rendered_template.text_content,
            from_email="noreply@huleedu.com",
            from_name="HuleEdu",
        )

        # Assert outbox publishing
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        outbox_call = mock_outbox_manager.publish_to_outbox.call_args
        assert outbox_call.kwargs["aggregate_type"] == "email_message"
        assert outbox_call.kwargs["aggregate_id"] == message_id
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)
        assert outbox_call.kwargs["topic"] == topic_name(ProcessingEvent.EMAIL_SENT)

        # Assert event envelope structure
        envelope = outbox_call.kwargs["event_data"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.EMAIL_SENT)
        assert envelope.source_service == "email_service"
        assert isinstance(envelope.data, EmailSentV1)
        assert envelope.data.message_id == message_id
        assert envelope.data.provider == "mock_provider"
        assert envelope.data.correlation_id == correlation_id

    async def test_process_email_request_template_not_found_error(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test template not found error handling and failure event publishing."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="nonexistent_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )

        mock_template_renderer.template_exists.return_value = False

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await event_processor.process_email_request(request)

        # Verify it's a validation error
        assert exc_info.value.error_detail.operation == "process_email_request"
        assert "Template not found: nonexistent_template" in str(exc_info.value)

        # Assert failure status update attempted
        mock_repository.update_status.assert_called()
        failure_call = None
        for call in mock_repository.update_status.call_args_list:
            if call.kwargs.get("status") == "failed":
                failure_call = call
                break
        assert failure_call is not None
        assert failure_call.kwargs["message_id"] == message_id
        assert failure_call.kwargs["status"] == "failed"

        # Assert failure event published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        outbox_call = mock_outbox_manager.publish_to_outbox.call_args
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

        envelope = outbox_call.kwargs["event_data"]
        assert isinstance(envelope.data, EmailDeliveryFailedV1)
        assert envelope.data.message_id == message_id
        assert envelope.data.correlation_id == correlation_id

    async def test_process_email_request_provider_failure_handling(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_email_provider: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
        sample_rendered_template: RenderedTemplate,
    ) -> None:
        """Test email provider failure handling and failure event publishing."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="recipient@example.se",
            variables={"name": "Test User"},
            category="verification",
            correlation_id=correlation_id,
        )

        mock_template_renderer.template_exists.return_value = True
        mock_template_renderer.render.return_value = sample_rendered_template
        mock_email_provider.send_email.return_value = EmailSendResult(
            success=False, error_message="SMTP server temporarily unavailable"
        )

        # Act
        await event_processor.process_email_request(request)

        # Assert failure status update
        failure_call = None
        for call in mock_repository.update_status.call_args_list:
            if call.kwargs.get("status") == "failed":
                failure_call = call
                break
        assert failure_call is not None
        assert failure_call.kwargs["message_id"] == message_id
        assert failure_call.kwargs["status"] == "failed"
        assert failure_call.kwargs["failure_reason"] == "SMTP server temporarily unavailable"

        # Assert failure event published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        outbox_call = mock_outbox_manager.publish_to_outbox.call_args
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

        envelope = outbox_call.kwargs["event_data"]
        assert isinstance(envelope.data, EmailDeliveryFailedV1)
        assert envelope.data.message_id == message_id
        assert envelope.data.reason == "SMTP server temporarily unavailable"
        assert envelope.data.provider == "mock_provider"

    async def test_handle_send_success_updates_record_and_publishes_event(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test successful email send handling updates record and publishes success event."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )
        send_result = EmailSendResult(success=True, provider_message_id="prov_456")
        rendered_subject = "Test Subject with åäö"

        # Act
        await event_processor._handle_send_success(request, send_result, rendered_subject)

        # Assert database update
        mock_repository.update_status.assert_called_once()
        call_args = mock_repository.update_status.call_args
        assert call_args.kwargs["message_id"] == message_id
        assert call_args.kwargs["status"] == "sent"
        assert call_args.kwargs["provider_message_id"] == "prov_456"
        assert isinstance(call_args.kwargs["sent_at"], datetime)

        # Assert success event published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["aggregate_type"] == "email_message"
        assert call_args.kwargs["aggregate_id"] == message_id
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)

    async def test_handle_send_failure_updates_record_and_publishes_event(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test failed email send handling updates record and publishes failure event."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )
        send_result = EmailSendResult(success=False, error_message="Rate limit exceeded")

        # Act
        await event_processor._handle_send_failure(request, send_result)

        # Assert database update
        mock_repository.update_status.assert_called_once()
        call_args = mock_repository.update_status.call_args
        assert call_args.kwargs["message_id"] == message_id
        assert call_args.kwargs["status"] == "failed"
        assert call_args.kwargs["failure_reason"] == "Rate limit exceeded"
        assert isinstance(call_args.kwargs["failed_at"], datetime)

        # Assert failure event published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

    async def test_publish_delivery_failed_event_creates_correct_envelope(
        self,
        event_processor: EmailEventProcessor,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
    ) -> None:
        """Test delivery failed event publishing creates proper envelope structure."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )
        failure_reason = "Invalid recipient address with Swedish chars: åäöÅÄÖ"

        # Act
        await event_processor._publish_delivery_failed_event(request, failure_reason)

        # Assert outbox manager called correctly
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args

        # Verify call parameters
        assert call_args.kwargs["aggregate_type"] == "email_message"
        assert call_args.kwargs["aggregate_id"] == message_id
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)
        assert call_args.kwargs["topic"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

        # Verify envelope structure
        envelope = call_args.kwargs["event_data"]
        assert isinstance(envelope, EventEnvelope)
        assert envelope.event_type == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)
        assert envelope.source_service == "email_service"

        # Verify event data payload
        assert isinstance(envelope.data, EmailDeliveryFailedV1)
        assert envelope.data.message_id == message_id
        assert envelope.data.provider == "mock_provider"
        assert envelope.data.reason == failure_reason
        assert envelope.data.correlation_id == correlation_id
        assert isinstance(envelope.data.failed_at, datetime)

    @pytest.mark.parametrize(
        "exception_type, exception_message",
        [
            (ValueError, "Invalid template variables"),
            (ConnectionError, "Network connection failed"),
            (TimeoutError, "Request timeout with åäö chars"),
            (RuntimeError, "Unexpected provider error"),
        ],
    )
    async def test_process_email_request_exception_handling(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
        exception_type: type[Exception],
        exception_message: str,
    ) -> None:
        """Test various exception scenarios in email processing workflow."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )

        mock_template_renderer.template_exists.return_value = True
        mock_template_renderer.render.side_effect = exception_type(exception_message)

        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await event_processor.process_email_request(request)

        # Verify it's a processing error
        assert exc_info.value.error_detail.operation == "process_email_request"
        assert "Email processing failed" in str(exc_info.value)

        # Assert failure status update attempted
        failure_updates = [
            call
            for call in mock_repository.update_status.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_updates) == 1
        assert failure_updates[0].kwargs["message_id"] == message_id
        assert exception_message in failure_updates[0].kwargs["failure_reason"]
        # Assert failure event published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        call_args = mock_outbox_manager.publish_to_outbox.call_args
        assert call_args.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

    async def test_outbox_manager_failure_propagates_during_success(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_template_renderer: AsyncMock,
        mock_email_provider: AsyncMock,
        mock_outbox_manager: AsyncMock,
        correlation_id: str,
        sample_rendered_template: RenderedTemplate,
    ) -> None:
        """Test that outbox manager failures during success path are properly handled."""
        # Arrange
        message_id = str(uuid4())
        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="test_template",
            to="test@example.se",
            variables={},
            category="verification",
            correlation_id=correlation_id,
        )

        mock_template_renderer.template_exists.return_value = True
        mock_template_renderer.render.return_value = sample_rendered_template
        mock_email_provider.send_email.return_value = EmailSendResult(
            success=True, provider_message_id="provider_123"
        )
        mock_outbox_manager.publish_to_outbox.side_effect = create_test_huleedu_error(
            message="Outbox storage failed", service="outbox_manager"
        )
        # Act & Assert
        with pytest.raises(HuleEduError) as exc_info:
            await event_processor.process_email_request(request)
        # Verify the original outbox error is propagated (not wrapped)
        assert exc_info.value.error_detail.service == "outbox_manager"
        assert "Outbox storage failed" in str(exc_info.value)

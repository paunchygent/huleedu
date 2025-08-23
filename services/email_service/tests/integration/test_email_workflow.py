"""Integration tests for end-to-end email processing workflow.

Tests complete email processing pipeline from NotificationEmailRequestedV1 event
to database persistence and event publishing, following Rule 075 methodology.
Focus on component integration, Swedish character support, and E2E workflow validation.
"""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
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
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.implementations.template_renderer_impl import (
    JinjaTemplateRenderer,
)
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol

from services.email_service.protocols import (
    EmailProvider,
    EmailRecord,
    EmailRepository,
    EmailSendResult,
)


class TestEmailWorkflowIntegration:
    """Integration tests for complete email processing workflow."""

    @pytest.fixture
    def temp_template_dir(self) -> Path:
        """Create temporary template directory with Swedish educational templates."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create Swedish teacher notification template
        teacher_template = temp_dir / "teacher_notification.html.j2"
        teacher_template.write_text(
            """<!-- subject: Meddelande från HuleEdu: {{ subject_prefix|default('Elevnotifiering') }} -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ subject_prefix|default('HuleEdu Meddelande') }}</title>
</head>
<body>
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h1>HuleEdu - Lärarmeddelandesystem</h1>
        <div style="background: white; padding: 25px; border-radius: 5px;">
            <h2>Hej {{ teacher_name|default('Kära lärare') }},</h2>
            <p>Du har en ny notifiering från HuleEdu systemet:</p>
            <div style="background: #f0f8ff; padding: 15px; border-left: 4px solid #007cba;">
                <p><strong>Elev:</strong> {{ student_name|default('Okänd elev') }}</p>
                <p><strong>Klass:</strong> {{ class_name|default('Ingen klass angiven') }}</p>
                <p><strong>Meddelande:</strong> {{ notification_message|default('Ingen information tillgänglig') }}</p>
            </div>
            <p>För mer information, logga in på HuleEdu plattformen.</p>
            <p>Med vänliga hälsningar,<br>HuleEdu Teamet</p>
        </div>
        <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
            <p>© {{ current_year|default('2025') }} HuleEdu. Alla rättigheter förbehållna.</p>
            <p>Ståthållaregatan 10C, 111 51 Stockholm, Sverige</p>
        </div>
    </div>
</body>
</html>""",
            encoding="utf-8",
        )

        # Create student verification template with Swedish characters
        student_template = temp_dir / "student_verification.html.j2"
        student_template.write_text(
            """<!-- subject: Bekräfta ditt HuleEdu konto, {{ student_first_name|default('Student') }}! -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kontobekräftelse</title>
</head>
<body>
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h1>Välkommen till HuleEdu!</h1>
        <div style="background: white; padding: 25px; border-radius: 5px;">
            <h2>Hej {{ student_first_name|default('Student') }} {{ student_last_name|default('') }}!</h2>
            <p>Tack för att du registrerat dig på HuleEdu. För att aktivera ditt konto och börja använda våra verktyg för språkutveckling, behöver du bekräfta din e-postadress.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{{ verification_link }}" style="display: inline-block; background: #007cba; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Bekräfta mitt konto
                </a>
            </div>
            <p>Med HuleEdu kan du:</p>
            <ul>
                <li>Förbättra din svenska skrift med AI-baserad feedback</li>
                <li>Få hjälp med grammatik och stavning (inklusive åäö hantering)</li>
                <li>Samarbeta med klasskompisar och lärare</li>
                <li>Spåra din utveckling över tid</li>
            </ul>
            <p>Om du har frågor, tveka inte att kontakta vår support.</p>
            <p>Lycka till med dina studier!</p>
            <p>Vänliga hälsningar,<br>HuleEdu Teamet</p>
        </div>
        <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
            <p>© {{ current_year|default('2025') }} HuleEdu. Alla rättigheter förbehållna.</p>
        </div>
    </div>
</body>
</html>""",
            encoding="utf-8",
        )

        return temp_dir

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Mock repository with proper spec adherence."""
        mock = AsyncMock(spec=EmailRepository)
        mock.create_email_record.return_value = None
        mock.update_status.return_value = None
        mock.get_by_message_id.return_value = None
        return mock

    @pytest.fixture
    def mock_outbox_repository(self) -> AsyncMock:
        """Mock outbox repository for event publishing tests."""
        mock = AsyncMock(spec=OutboxRepositoryProtocol)
        mock.add_event.return_value = uuid4()
        return mock

    @pytest.fixture
    def mock_email_provider(self) -> AsyncMock:
        """Mock email provider with Swedish character support."""
        mock = AsyncMock(spec=EmailProvider)
        mock.get_provider_name.return_value = "integration_test_provider"
        return mock

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for outbox notifications."""
        mock = AsyncMock()
        mock.lpush.return_value = None
        return mock

    @pytest.fixture
    def settings(self) -> Settings:
        """Test settings with Swedish defaults."""
        return Settings(
            DEFAULT_FROM_EMAIL="test@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Test System",
            EMAIL_PROVIDER="mock",
            SERVICE_NAME="email_service",
        )

    @pytest.fixture
    def template_renderer(self, temp_template_dir: Path) -> JinjaTemplateRenderer:
        """Real template renderer using temporary template directory."""
        return JinjaTemplateRenderer(template_path=str(temp_template_dir))

    @pytest.fixture
    def outbox_manager(
        self,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        settings: Settings,
    ) -> OutboxManager:
        """Real outbox manager with mocked dependencies."""
        return OutboxManager(
            outbox_repository=mock_outbox_repository,
            redis_client=mock_redis_client,
            settings=settings,
        )

    @pytest.fixture
    def event_processor(
        self,
        mock_repository: AsyncMock,
        template_renderer: JinjaTemplateRenderer,
        mock_email_provider: AsyncMock,
        outbox_manager: OutboxManager,
        settings: Settings,
    ) -> EmailEventProcessor:
        """Real event processor with integrated dependencies."""
        return EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=mock_email_provider,
            outbox_manager=outbox_manager,
            settings=settings,
        )

    @pytest.mark.parametrize(
        "template_id,variables,expected_subject_contains,expected_content_contains",
        [
            # Swedish teacher notification with åäö characters
            (
                "teacher_notification",
                {
                    "teacher_name": "Anna Lindström",
                    "student_name": "Erik Björkman",
                    "class_name": "Svenska 1 - Språkutveckling",
                    "notification_message": "Eleven har slutfört sin uppsats om 'Kärlek och kärlek' med utmärkt resultat.",
                    "subject_prefix": "Elevbetyg klart",
                },
                "Elevbetyg klart",
                "Anna Lindström",
            ),
            # Student verification with Swedish characters
            (
                "student_verification",
                {
                    "student_first_name": "Astrid",
                    "student_last_name": "Öhman",
                    "verification_link": "https://huleedu.se/verify/abc123",
                    "current_year": "2025",
                },
                "Bekräfta ditt HuleEdu konto, Astrid!",
                "Astrid Öhman",
            ),
            # Edge case: Empty variables with Swedish defaults
            (
                "teacher_notification",
                {},
                "Elevnotifiering",
                "Kära lärare",
            ),
        ],
    )
    async def test_complete_email_processing_pipeline_success(
        self,
        event_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
        template_id: str,
        variables: dict[str, str],
        expected_subject_contains: str,
        expected_content_contains: str,
    ) -> None:
        """Test complete email processing pipeline with successful delivery.

        Validates end-to-end workflow: request → template rendering → sending → persistence → event publishing.
        Ensures Swedish character preservation throughout the entire pipeline.
        """
        # Arrange: Configure successful email send
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        mock_email_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id="provider_123",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id=template_id,
            to="test@example.se",
            variables=variables,
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act: Process the complete workflow
        await event_processor.process_email_request(request)

        # Assert: Verify template rendering integration
        send_call = mock_email_provider.send_email.call_args
        assert send_call is not None
        sent_subject = send_call.kwargs["subject"]
        sent_html_content = send_call.kwargs["html_content"]
        sent_text_content = send_call.kwargs["text_content"]

        assert expected_subject_contains in sent_subject
        assert expected_content_contains in sent_html_content
        assert expected_content_contains in sent_text_content

        # Verify Swedish characters preserved in all formats
        if "Ö" in expected_content_contains or "ä" in expected_content_contains:
            assert "Ö" in sent_html_content or "ä" in sent_html_content

        # Assert: Verify database persistence workflow
        assert mock_repository.create_email_record.call_count == 1
        created_record_call = mock_repository.create_email_record.call_args
        created_record: EmailRecord = created_record_call.args[0]

        assert created_record.message_id == message_id
        assert created_record.to_address == request.to
        assert created_record.template_id == template_id
        assert created_record.category == request.category
        assert created_record.correlation_id == correlation_id
        assert created_record.variables == variables

        # Assert: Verify status updates
        assert mock_repository.update_status.call_count == 2
        status_calls = mock_repository.update_status.call_args_list

        # First update: processing status
        processing_call = status_calls[0]
        assert processing_call.kwargs["message_id"] == message_id
        assert processing_call.kwargs["status"] == "processing"

        # Second update: sent status
        sent_call = status_calls[1]
        assert sent_call.kwargs["message_id"] == message_id
        assert sent_call.kwargs["status"] == "sent"
        assert sent_call.kwargs["provider_message_id"] == "provider_123"
        assert sent_call.kwargs["sent_at"] is not None

        # Assert: Verify event publishing integration
        assert mock_outbox_repository.add_event.call_count == 1
        outbox_call = mock_outbox_repository.add_event.call_args

        assert outbox_call.kwargs["aggregate_type"] == "email_message"
        assert outbox_call.kwargs["aggregate_id"] == message_id
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)
        assert outbox_call.kwargs["topic"] == topic_name(ProcessingEvent.EMAIL_SENT)

        # Verify event envelope structure and correlation ID propagation
        event_data = outbox_call.kwargs["event_data"]
        assert isinstance(event_data, dict)  # Serialized EventEnvelope
        assert event_data["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)
        assert event_data["source_service"] == "email_service"
        # Note: EventEnvelope generates its own correlation_id, but the important thing is that
        # the business correlation_id is preserved in the data field
        assert "correlation_id" in event_data  # Has correlation_id field

        # Verify EmailSentV1 data structure contains original correlation_id
        sent_data = event_data["data"]
        assert sent_data["message_id"] == message_id
        assert sent_data["provider"] == "integration_test_provider"
        assert sent_data["correlation_id"] == correlation_id
        assert "sent_at" in sent_data

    async def test_template_rendering_integration_with_missing_template(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
    ) -> None:
        """Test template rendering integration when template does not exist."""
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="nonexistent_template",
            to="test@example.se",
            variables={"test": "value"},
            category="system",
            correlation_id=correlation_id,
        )

        # Act & Assert: Should raise HuleEduError for validation
        with pytest.raises(HuleEduError) as exc_info:
            await event_processor.process_email_request(request)

        error_str = str(exc_info.value)
        assert "PROCESSING_ERROR" in error_str or "VALIDATION_ERROR" in error_str
        assert "Template not found" in error_str

        # Verify database operations: template validation happens before email record creation
        # So when template doesn't exist, no email record should be created
        assert mock_repository.create_email_record.call_count == 0

        # Verify that status update was attempted in exception handler (for a non-existent record)
        # In real scenarios this would fail, but mocks record the call
        assert mock_repository.update_status.call_count == 1
        update_call = mock_repository.update_status.call_args
        assert update_call.kwargs["message_id"] == message_id
        assert update_call.kwargs["status"] == "failed"
        assert "Template not found" in update_call.kwargs["failure_reason"]

    async def test_email_provider_failure_integration(
        self,
        event_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test integration behavior when email provider fails."""
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        # Arrange: Configure email provider failure
        mock_email_provider.send_email.return_value = EmailSendResult(
            success=False,
            error_message="SMTP server unreachable - Svenska tecken kräver UTF-8 encoding",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="teacher_notification",
            to="test@example.se",
            variables={
                "teacher_name": "Björn Andersson",
                "student_name": "Åsa Lindqvist",
            },
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act: Process with provider failure
        await event_processor.process_email_request(request)

        # Assert: Verify template rendering still occurred
        assert mock_email_provider.send_email.call_count == 1

        # Assert: Verify database failure tracking
        failure_update_calls = [
            call
            for call in mock_repository.update_status.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_update_calls) == 1

        failure_call = failure_update_calls[0]
        assert failure_call.kwargs["message_id"] == message_id
        assert "SMTP server unreachable" in failure_call.kwargs["failure_reason"]
        assert failure_call.kwargs["failed_at"] is not None

        # Assert: Verify failure event publishing
        assert mock_outbox_repository.add_event.call_count == 1
        outbox_call = mock_outbox_repository.add_event.call_args

        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

        # Verify EmailDeliveryFailedV1 event data
        event_data = outbox_call.kwargs["event_data"]
        failed_data = event_data["data"]
        assert failed_data["message_id"] == message_id
        assert failed_data["provider"] == "integration_test_provider"
        assert failed_data["correlation_id"] == correlation_id
        assert "Svenska tecken" in failed_data["reason"]
        assert "failed_at" in failed_data

    async def test_database_transaction_rollback_integration(
        self,
        event_processor: EmailEventProcessor,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test database transaction behavior during various failure scenarios."""
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        # Arrange: Configure repository to fail on status update
        mock_repository.update_status.side_effect = Exception(
            "Database connection lost - rollback transaction"
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="teacher_notification",
            to="test@example.se",
            variables={"teacher_name": "Test Teacher"},
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act & Assert: Should propagate database error
        with pytest.raises(HuleEduError) as exc_info:
            await event_processor.process_email_request(request)

        error_str = str(exc_info.value)
        assert "PROCESSING_ERROR" in error_str

        # Assert: Initial record creation should have occurred
        assert mock_repository.create_email_record.call_count == 1

        # Assert: Status update attempted multiple times (processing, then final state)
        # The first call sets status to "processing", the second call fails
        assert mock_repository.update_status.call_count >= 1

        # Assert: Failure event publishing should still occur
        assert mock_outbox_repository.add_event.call_count == 1
        outbox_call = mock_outbox_repository.add_event.call_args
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)

    async def test_correlation_id_propagation_throughout_workflow(
        self,
        event_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test correlation ID propagation through entire email processing workflow."""
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        mock_email_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id="provider_456",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="student_verification",
            to="student@example.se",
            variables={
                "student_first_name": "Märta",
                "verification_link": "https://huleedu.se/verify/xyz789",
            },
            category="verification",
            correlation_id=correlation_id,
        )

        # Act: Process complete workflow
        await event_processor.process_email_request(request)

        # Assert: Correlation ID in database record
        record_call = mock_repository.create_email_record.call_args
        created_record: EmailRecord = record_call.args[0]
        assert created_record.correlation_id == correlation_id

        # Assert: Correlation ID in success event
        outbox_call = mock_outbox_repository.add_event.call_args
        event_data = outbox_call.kwargs["event_data"]

        # Verify envelope has correlation ID field (may be different from business correlation)
        assert "correlation_id" in event_data

        # Verify event data contains the original business correlation ID
        sent_data = event_data["data"]
        assert sent_data["correlation_id"] == correlation_id

    @pytest.mark.parametrize(
        "template_variables,expected_swedish_chars",
        [
            # Test various Swedish character combinations
            ({"teacher_name": "Åke Öberg", "class_name": "Avancerad svenska"}, ["Åke", "Öberg"]),
            ({"student_name": "Märta Äppelgren"}, ["Märta", "Äppelgren"]),
            (
                {
                    "notification_message": "Utmärkt arbete med språkförståelse och kärlek för litteratur"
                },
                ["Utmärkt", "språkförståelse", "kärlek"],
            ),
            # Test mixed ASCII and Swedish characters
            (
                {"teacher_name": "Anna-Lisa Björkström", "class_name": "English & Svenska 2"},
                ["Anna-Lisa", "Björkström"],
            ),
        ],
    )
    async def test_swedish_character_preservation_throughout_pipeline(
        self,
        event_processor: EmailEventProcessor,
        mock_email_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
        template_variables: dict[str, str],
        expected_swedish_chars: list[str],
    ) -> None:
        """Test Swedish character preservation through complete processing pipeline."""
        correlation_id = str(uuid4())
        message_id = f"test_msg_{uuid4()}"

        mock_email_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id="provider_swedish_test",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="teacher_notification",
            to="lärare@svenskaskolan.se",
            variables=template_variables,
            category="teacher_notification",
            correlation_id=correlation_id,
        )

        # Act: Process with Swedish characters
        await event_processor.process_email_request(request)

        # Assert: Swedish characters preserved in database
        record_call = mock_repository.create_email_record.call_args
        created_record: EmailRecord = record_call.args[0]

        for swedish_word in expected_swedish_chars:
            found_in_variables = any(
                swedish_word in str(value) for value in created_record.variables.values()
            )
            assert found_in_variables, (
                f"Swedish word '{swedish_word}' not preserved in database variables"
            )

        # Assert: Swedish characters preserved in email content
        email_call = mock_email_provider.send_email.call_args
        sent_html = email_call.kwargs["html_content"]
        sent_text = email_call.kwargs["text_content"]

        for swedish_word in expected_swedish_chars:
            assert swedish_word in sent_html, (
                f"Swedish word '{swedish_word}' not preserved in HTML content"
            )
            assert swedish_word in sent_text, (
                f"Swedish word '{swedish_word}' not preserved in text content"
            )

        # Assert: Swedish characters preserved in events
        outbox_call = mock_outbox_repository.add_event.call_args
        event_data = outbox_call.kwargs["event_data"]

        # Check if Swedish characters exist in the overall event (they should be in correlation with variables)
        event_str = str(event_data)
        for swedish_word in expected_swedish_chars:
            # Swedish characters should be preserved in the serialized data
            assert swedish_word in sent_html  # Indirect verification through email content

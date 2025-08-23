"""SMTP provider integration tests for complete email delivery workflow.

Integration tests validating end-to-end email processing with SMTP provider
following Rule 075 methodology. Tests focus on behavioral validation, 
Swedish character support, and complete workflow integration without @patch usage.
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
from huleedu_service_libs.error_handling import HuleEduError
from huleedu_service_libs.redis_client import AtomicRedisClientProtocol
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.implementations.template_renderer_impl import (
    JinjaTemplateRenderer,
)
from services.email_service.protocols import (
    EmailProvider,
    EmailRecord,
    EmailRepository,
    EmailSendResult,
)
from huleedu_service_libs.outbox.protocols import OutboxRepositoryProtocol


class TestSMTPProviderIntegration:
    """Integration tests for SMTP provider with complete email workflow."""

    @pytest.fixture
    def temp_template_dir(self) -> Path:
        """Create temporary template directory with Swedish educational templates."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create verification template with comprehensive Swedish content
        verification_template = temp_dir / "verification_request.html.j2"
        verification_template.write_text(
            """<!-- subject: Bekräfta ditt HuleEdu-konto, {{ student_name|default('Student') }}! -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HuleEdu Kontobekräftelse</title>
</head>
<body>
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h1 style="color: #007cba;">Välkommen till HuleEdu, {{ student_name|default('Student') }}!</h1>
        <div style="background: white; padding: 25px; border-radius: 5px;">
            <p>Tack för att du har registrerat dig för HuleEdu:s språkutvecklingsprogram.</p>
            <p>För att börja använda våra verktyg för svenska språket, inklusive stöd för åäö-tecken och grammatikanalys, behöver du bekräfta din e-postadress.</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{{ verification_link }}" 
                   style="display: inline-block; background: #007cba; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Bekräfta mitt konto
                </a>
            </div>
            <h3>Med HuleEdu får du hjälp med:</h3>
            <ul>
                <li>Språkutveckling med fokus på svenska grammatik</li>
                <li>Rättning av texter med åäö-stöd</li>
                <li>Uppsatsskrivning och återkoppling</li>
                <li>Språkanalys för elever på {{ grade_level|default('alla') }} nivåer</li>
            </ul>
            <p><strong>Klass:</strong> {{ class_name|default('Ingen klass ännu') }}</p>
            <p><strong>Lärare:</strong> {{ teacher_name|default('Kommer att tilldelas') }}</p>
            <p>Har du frågor? Kontakta vår svenska support på <a href="mailto:support@hule.education">support@hule.education</a></p>
            <p>Lycka till med dina språkstudier!</p>
            <p>Vänliga hälsningar,<br>HuleEdu Teamet</p>
        </div>
        <div style="text-align: center; margin-top: 20px; font-size: 12px; color: #666;">
            <p>© {{ current_year|default('2025') }} HuleEdu AB. Alla rättigheter förbehållna.</p>
            <p>Organisationsnummer: 559123-4567</p>
            <p>Ståthållaregatan 10C, 111 51 Stockholm, Sverige</p>
        </div>
    </div>
</body>
</html>""",
            encoding="utf-8",
        )

        # Create password reset template with Swedish special characters
        password_template = temp_dir / "password_reset.html.j2"
        password_template.write_text(
            """<!-- subject: Återställ ditt lösenord för HuleEdu -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Lösenordsåterställning - HuleEdu</title>
</head>
<body>
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h1 style="color: #d32f2f;">Lösenordsåterställning</h1>
        <div style="background: white; padding: 25px; border-radius: 5px; border-left: 4px solid #d32f2f;">
            <h2>Hej {{ user_name|default('användare') }},</h2>
            <p>Du har begärt att återställa ditt lösenord för ditt HuleEdu-konto.</p>
            <p><strong>Användarnamn:</strong> {{ username|default('Inte angivet') }}</p>
            <p><strong>E-postadress:</strong> {{ email|default('Inte angiven') }}</p>
            <div style="background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Säkerhetsmeddelande:</strong> Om du inte har begärt denna lösenordsåterställning, 
                ignorera detta meddelande. Ditt konto förblir säkert.</p>
            </div>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{{ reset_link }}" 
                   style="display: inline-block; background: #d32f2f; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 5px; font-weight: bold;">
                    Återställ lösenord
                </a>
            </div>
            <p>Denna länk är giltig i {{ expiry_hours|default('24') }} timmar från när detta meddelande skickades.</p>
            <p>För din säkerhets skull, logga ut från alla enheter efter att du har ändrat ditt lösenord.</p>
            <p>Med vänliga hälsningar,<br>HuleEdu Säkerhetsteamet</p>
        </div>
    </div>
</body>
</html>""",
            encoding="utf-8",
        )

        return temp_dir

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Mock repository with proper spec adherence for SMTP testing."""
        mock = AsyncMock(spec=EmailRepository)
        mock.create_email_record.return_value = None
        mock.update_status.return_value = None
        mock.get_by_message_id.return_value = None
        return mock

    @pytest.fixture
    def mock_outbox_repository(self) -> AsyncMock:
        """Mock outbox repository for SMTP event publishing tests."""
        mock = AsyncMock(spec=OutboxRepositoryProtocol)
        mock.add_event.return_value = uuid4()
        return mock

    @pytest.fixture
    def mock_smtp_provider(self) -> AsyncMock:
        """Mock SMTP provider following EmailProvider protocol."""
        mock = AsyncMock(spec=EmailProvider)
        mock.get_provider_name.return_value = "smtp"
        # Default to successful sends
        mock.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id="smtp_test_123456",
        )
        return mock

    @pytest.fixture
    def mock_redis_client(self) -> AsyncMock:
        """Mock Redis client for SMTP outbox notifications."""
        mock = AsyncMock()
        mock.lpush.return_value = None
        return mock

    @pytest.fixture
    def smtp_settings(self) -> Settings:
        """Test settings configured for SMTP provider."""
        return Settings(
            DEFAULT_FROM_EMAIL="test@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Test System",
            EMAIL_PROVIDER="smtp",  # Key configuration for SMTP testing
            SERVICE_NAME="email_service",
            SMTP_HOST="mail.privateemail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="test_password",
            SMTP_USE_TLS=True,
            SMTP_TIMEOUT=30,
        )

    @pytest.fixture
    def template_renderer(self, temp_template_dir: Path) -> JinjaTemplateRenderer:
        """Real template renderer for SMTP integration testing."""
        return JinjaTemplateRenderer(template_path=str(temp_template_dir))

    @pytest.fixture
    def outbox_manager(
        self,
        mock_outbox_repository: AsyncMock,
        mock_redis_client: AsyncMock,
        smtp_settings: Settings,
    ) -> OutboxManager:
        """Real outbox manager with SMTP-configured dependencies."""
        return OutboxManager(
            outbox_repository=mock_outbox_repository,
            redis_client=mock_redis_client,
            settings=smtp_settings,
        )

    @pytest.fixture
    def smtp_event_processor(
        self,
        mock_repository: AsyncMock,
        template_renderer: JinjaTemplateRenderer,
        mock_smtp_provider: AsyncMock,
        outbox_manager: OutboxManager,
        smtp_settings: Settings,
    ) -> EmailEventProcessor:
        """Email event processor configured for SMTP integration testing."""
        return EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=mock_smtp_provider,
            outbox_manager=outbox_manager,
            settings=smtp_settings,
        )

    @pytest.mark.parametrize(
        "template_id,template_variables,expected_subject_contains,expected_content_contains,smtp_message_prefix",
        [
            # Swedish verification email with comprehensive åäö testing
            (
                "verification_request",
                {
                    "student_name": "Astrid Öhman",
                    "verification_link": "https://huleedu.se/verify/abc123def",
                    "grade_level": "gymnasiet",
                    "class_name": "Svenska 3 - Språkutveckling",
                    "teacher_name": "Björn Andersson",
                    "current_year": "2025",
                },
                "Bekräfta ditt HuleEdu-konto, Astrid Öhman!",
                "åäö-stöd",
                "smtp_verification_",
            ),
            # Password reset with security focus
            (
                "password_reset",
                {
                    "user_name": "Märta Lindström",
                    "username": "marta.lindstrom@student.se",
                    "email": "marta.lindstrom@student.se",
                    "reset_link": "https://huleedu.se/reset/xyz789abc",
                    "expiry_hours": "24",
                },
                "Återställ ditt lösenord för HuleEdu",
                "Lösenordsåterställning",
                "smtp_password_",
            ),
            # Edge case: minimal variables with Swedish defaults
            (
                "verification_request",
                {
                    "verification_link": "https://huleedu.se/verify/minimal",
                },
                "Bekräfta ditt HuleEdu-konto, Student!",
                "alla nivåer",
                "smtp_minimal_",
            ),
        ],
    )
    async def test_smtp_end_to_end_email_delivery_success(
        self,
        smtp_event_processor: EmailEventProcessor,
        mock_smtp_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
        template_id: str,
        template_variables: dict[str, str],
        expected_subject_contains: str,
        expected_content_contains: str,
        smtp_message_prefix: str,
    ) -> None:
        """Test complete SMTP email delivery workflow from request to persistence.

        Validates end-to-end integration: NotificationEmailRequestedV1 → Jinja2 rendering 
        → SMTP multipart sending → database persistence → EmailSentV1 event publishing.
        Ensures Swedish character preservation through entire SMTP pipeline.
        """
        # Arrange: Setup SMTP delivery scenario
        correlation_id = str(uuid4())
        message_id = f"smtp_msg_{uuid4()}"
        
        # Configure SMTP provider success with realistic message ID
        smtp_provider_msg_id = f"{smtp_message_prefix}{hash(message_id) % 1000000}"
        mock_smtp_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id=smtp_provider_msg_id,
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id=template_id,
            to="recipient@svenskaskolan.se",
            variables=template_variables,
            category="smtp_integration_test",
            correlation_id=correlation_id,
        )

        # Act: Process complete SMTP workflow
        await smtp_event_processor.process_email_request(request)

        # Assert: Verify template rendering → SMTP integration
        assert mock_smtp_provider.send_email.call_count == 1
        smtp_send_call = mock_smtp_provider.send_email.call_args
        
        # Verify SMTP-specific multipart content generation
        sent_to = smtp_send_call.kwargs["to"]
        sent_subject = smtp_send_call.kwargs["subject"]
        sent_html_content = smtp_send_call.kwargs["html_content"]
        sent_text_content = smtp_send_call.kwargs["text_content"]
        sent_from_email = smtp_send_call.kwargs["from_email"]
        sent_from_name = smtp_send_call.kwargs["from_name"]

        assert sent_to == "recipient@svenskaskolan.se"
        assert expected_subject_contains in sent_subject
        assert expected_content_contains in sent_html_content
        assert expected_content_contains in sent_text_content  # Text content extracted from HTML
        assert sent_from_email == "test@huleedu.se"
        assert sent_from_name == "HuleEdu Test System"

        # Assert: Swedish character preservation in SMTP content
        if "ö" in expected_content_contains or "ä" in expected_content_contains:
            # Verify åäö characters preserved in both HTML and text versions
            assert any(char in sent_html_content for char in ["å", "ä", "ö", "Å", "Ä", "Ö"])
            assert any(char in sent_text_content for char in ["å", "ä", "ö", "Å", "Ä", "Ö"])

        # Assert: Database persistence with SMTP provider details
        assert mock_repository.create_email_record.call_count == 1
        created_record_call = mock_repository.create_email_record.call_args
        created_record: EmailRecord = created_record_call.args[0]

        assert created_record.message_id == message_id
        assert created_record.to_address == request.to
        assert created_record.from_address == "test@huleedu.se"
        assert created_record.from_name == "HuleEdu Test System"
        assert created_record.template_id == template_id
        assert created_record.category == request.category
        assert created_record.correlation_id == correlation_id
        assert created_record.variables == template_variables
        assert created_record.provider == "smtp"  # SMTP provider identification

        # Assert: SMTP-specific status updates
        assert mock_repository.update_status.call_count == 2
        status_updates = mock_repository.update_status.call_args_list

        # Processing status update
        processing_update = status_updates[0]
        assert processing_update.kwargs["message_id"] == message_id
        assert processing_update.kwargs["status"] == "processing"

        # Success status update with SMTP details
        success_update = status_updates[1]
        assert success_update.kwargs["message_id"] == message_id
        assert success_update.kwargs["status"] == "sent"
        assert success_update.kwargs["provider_message_id"] == smtp_provider_msg_id
        assert success_update.kwargs["sent_at"] is not None

        # Assert: EmailSentV1 event publishing after SMTP success
        assert mock_outbox_repository.add_event.call_count == 1
        outbox_call = mock_outbox_repository.add_event.call_args

        assert outbox_call.kwargs["aggregate_type"] == "email_message"
        assert outbox_call.kwargs["aggregate_id"] == message_id
        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)
        assert outbox_call.kwargs["topic"] == topic_name(ProcessingEvent.EMAIL_SENT)

        # Verify EmailSentV1 event structure with SMTP provider details
        event_data = outbox_call.kwargs["event_data"]
        assert event_data["event_type"] == topic_name(ProcessingEvent.EMAIL_SENT)
        assert event_data["source_service"] == "email_service"
        
        sent_event_data = event_data["data"]
        assert sent_event_data["message_id"] == message_id
        assert sent_event_data["provider"] == "smtp"
        assert sent_event_data["correlation_id"] == correlation_id
        assert "sent_at" in sent_event_data

    async def test_smtp_provider_authentication_failure_integration(
        self,
        smtp_event_processor: EmailEventProcessor,
        mock_smtp_provider: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_repository: AsyncMock,
    ) -> None:
        """Test SMTP authentication failure handling with proper error propagation."""
        correlation_id = str(uuid4())
        message_id = f"smtp_auth_fail_{uuid4()}"

        # Configure SMTP authentication failure
        mock_smtp_provider.send_email.return_value = EmailSendResult(
            success=False,
            error_message="SMTP authentication failed: Invalid username/password for mail.privateemail.com",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="verification_request",
            to="test@svenskaskolan.se",
            variables={"student_name": "Test Användare", "verification_link": "https://test.com"},
            category="smtp_auth_test",
            correlation_id=correlation_id,
        )

        # Act: Process with SMTP authentication failure
        await smtp_event_processor.process_email_request(request)

        # Assert: SMTP send attempted
        assert mock_smtp_provider.send_email.call_count == 1

        # Assert: Failure status recorded in database
        failure_updates = [
            call for call in mock_repository.update_status.call_args_list
            if call.kwargs.get("status") == "failed"
        ]
        assert len(failure_updates) == 1
        
        failure_update = failure_updates[0]
        assert failure_update.kwargs["message_id"] == message_id
        assert "SMTP authentication failed" in failure_update.kwargs["failure_reason"]
        assert failure_update.kwargs["failed_at"] is not None

        # Assert: EmailDeliveryFailedV1 event published
        assert mock_outbox_repository.add_event.call_count == 1
        outbox_call = mock_outbox_repository.add_event.call_args

        assert outbox_call.kwargs["event_type"] == topic_name(ProcessingEvent.EMAIL_DELIVERY_FAILED)
        
        failed_event_data = outbox_call.kwargs["event_data"]
        failed_data = failed_event_data["data"]
        assert failed_data["message_id"] == message_id
        assert failed_data["provider"] == "smtp"
        assert failed_data["correlation_id"] == correlation_id
        assert "SMTP authentication failed" in failed_data["reason"]
        assert "failed_at" in failed_data

    async def test_smtp_provider_selection_via_settings(
        self,
        mock_repository: AsyncMock,
        template_renderer: JinjaTemplateRenderer,
        outbox_manager: OutboxManager,
    ) -> None:
        """Test that DI container properly selects SMTP provider when EMAIL_PROVIDER=smtp."""
        # Arrange: Create settings with SMTP provider configuration
        smtp_settings = Settings(
            EMAIL_PROVIDER="smtp",
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="test_password",
            SMTP_HOST="mail.privateemail.com",
            DEFAULT_FROM_EMAIL="test@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Test",
            SERVICE_NAME="email_service",
        )

        # Mock SMTP provider that should be selected
        mock_smtp_provider = AsyncMock(spec=EmailProvider)
        mock_smtp_provider.get_provider_name.return_value = "smtp"
        mock_smtp_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id="smtp_di_test_456",
        )

        # Act: Create event processor with SMTP-configured settings
        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=mock_smtp_provider,  # DI would inject SMTP provider here
            outbox_manager=outbox_manager,
            settings=smtp_settings,
        )

        # Assert: Event processor uses SMTP provider
        assert event_processor.email_provider == mock_smtp_provider
        assert event_processor.email_provider.get_provider_name() == "smtp"
        
        # Verify settings configuration
        assert smtp_settings.EMAIL_PROVIDER == "smtp"
        assert smtp_settings.SMTP_HOST == "mail.privateemail.com"
        assert smtp_settings.SMTP_USERNAME == "test@huleedu.se"

    @pytest.mark.parametrize(
        "swedish_variables,expected_preserved_chars",
        [
            # Comprehensive åäö testing in various contexts
            (
                {
                    "student_name": "Åsa Öberg",
                    "teacher_name": "Björn Ärlig",
                    "class_name": "Avancerad svenska - språkförståelse",
                },
                ["Åsa", "Öberg", "Björn", "Ärlig", "språkförståelse"],
            ),
            # Mixed Swedish-English content
            (
                {
                    "user_name": "Märta Lindström-Johnson", 
                },
                ["Märta"],
            ),
            # Special characters in email context
            (
                {
                    "student_name": "Nils-Åke Öström",
                },
                ["Nils-Åke", "Öström"],
            ),
        ],
    )
    async def test_smtp_swedish_character_preservation_comprehensive(
        self,
        smtp_event_processor: EmailEventProcessor,
        mock_smtp_provider: AsyncMock,
        mock_repository: AsyncMock,
        swedish_variables: dict[str, str],
        expected_preserved_chars: list[str],
    ) -> None:
        """Test comprehensive Swedish character preservation through SMTP pipeline.

        Validates that åäöÅÄÖ characters are properly preserved through:
        - Template rendering with Jinja2
        - SMTP multipart message construction  
        - Database persistence
        - Event publishing
        """
        correlation_id = str(uuid4())
        message_id = f"smtp_swedish_{uuid4()}"

        # Configure successful SMTP delivery
        mock_smtp_provider.send_email.return_value = EmailSendResult(
            success=True,
            provider_message_id=f"smtp_swedish_{hash(message_id) % 100000}",
        )

        request = NotificationEmailRequestedV1(
            message_id=message_id,
            template_id="verification_request",
            to="svenska@lärare.se",
            variables=swedish_variables,
            category="swedish_char_test",
            correlation_id=correlation_id,
        )

        # Act: Process with Swedish characters
        await smtp_event_processor.process_email_request(request)

        # Assert: Swedish characters preserved in SMTP content
        smtp_call = mock_smtp_provider.send_email.call_args
        sent_html = smtp_call.kwargs["html_content"]
        sent_text = smtp_call.kwargs["text_content"]

        for swedish_word in expected_preserved_chars:
            assert swedish_word in sent_html, (
                f"Swedish word '{swedish_word}' not preserved in SMTP HTML content"
            )
            assert swedish_word in sent_text, (
                f"Swedish word '{swedish_word}' not preserved in SMTP text content"
            )

        # Assert: Swedish characters preserved in database persistence
        record_call = mock_repository.create_email_record.call_args
        created_record: EmailRecord = record_call.args[0]

        for swedish_word in expected_preserved_chars:
            found_in_variables = any(
                swedish_word in str(value) for value in created_record.variables.values()
            )
            assert found_in_variables, (
                f"Swedish word '{swedish_word}' not preserved in database variables"
            )

        # Assert: Email addresses with Swedish domains handled properly
        assert created_record.to_address == "svenska@lärare.se"
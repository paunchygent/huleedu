"""Integration tests for SMTP provider within email service workflow.

Tests complete email processing pipeline from NotificationEmailRequestedV1 event
to SMTP delivery, database persistence, and event publishing following Rule 075.
Focus on end-to-end workflow validation with minimal network-boundary mocking.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from common_core.emailing_models import (
    NotificationEmailRequestedV1,
)
from huleedu_service_libs.outbox.manager import OutboxManager

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.provider_smtp_impl import SMTPEmailProvider
from services.email_service.implementations.template_renderer_impl import (
    JinjaTemplateRenderer,
)
from services.email_service.protocols import EmailRecord, EmailRepository


class TestSMTPIntegrationWorkflow:
    """Integration tests for complete SMTP email workflow."""

    @pytest.fixture
    def smtp_settings(self) -> Settings:
        """Create SMTP-enabled settings for integration testing."""
        settings = Settings()
        settings.EMAIL_PROVIDER = "smtp"
        settings.SMTP_HOST = "mail.privateemail.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USERNAME = "noreply@hule.education"
        settings.SMTP_PASSWORD = "test_password"
        settings.SMTP_USE_TLS = True
        settings.DEFAULT_FROM_EMAIL = "noreply@hule.education"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        return settings

    @pytest.fixture
    def temp_template_dir(self) -> Path:
        """Create temporary template directory with Swedish educational templates."""
        temp_dir = Path(tempfile.mkdtemp())

        # Create verification template with Swedish content
        verification_template = temp_dir / "verification.html.j2"
        verification_template.write_text(
            """<!-- subject: Bekräfta ditt HuleEdu konto -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Kontobekräftelse</title>
</head>
<body>
    <h1>Välkommen till HuleEdu!</h1>
    <p>Hej {{ user_name|default('användare') }},</p>
    <p>Klicka på länken för att bekräfta ditt konto:</p>
    <p><a href="{{ verification_link }}">Bekräfta konto</a></p>
    <p>Länken förfaller den {{ expires_at }}.</p>
    <p>Med vänliga hälsningar,<br>HuleEdu Teamet</p>
</body>
</html>""",
            encoding="utf-8",
        )

        # Create password reset template with Swedish content
        password_reset_template = temp_dir / "password_reset.html.j2"
        password_reset_template.write_text(
            """<!-- subject: Återställ ditt lösenord -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Lösenordsåterställning</title>
</head>
<body>
    <h1>Återställ ditt lösenord</h1>
    <p>Hej {{ user_name|default('användare') }},</p>
    <p>Klicka på länken för att återställa ditt lösenord:</p>
    <p><a href="{{ reset_link }}">Återställ lösenord</a></p>
    <p>Länken förfaller den {{ expires_at }}.</p>
</body>
</html>""",
            encoding="utf-8",
        )

        return temp_dir

    @pytest.fixture
    def mock_smtp_server(self, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
        """Mock SMTP server at network boundary only - minimal mocking per Rule 075."""
        mock_smtp = AsyncMock()
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}  # No send errors
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)
        return mock_smtp

    @pytest.fixture
    def mock_repository(self) -> AsyncMock:
        """Mock repository with spec compliance per Rule 075."""
        mock_repo = AsyncMock(spec=EmailRepository)
        mock_repo.create_email_record.return_value = None
        mock_repo.update_status.return_value = None
        return mock_repo

    @pytest.fixture
    def mock_outbox_manager(self) -> AsyncMock:
        """Mock outbox manager with real behavior simulation."""
        mock_outbox = AsyncMock(spec=OutboxManager)
        mock_outbox.publish_to_outbox.return_value = None
        return mock_outbox

    @pytest.mark.asyncio
    async def test_end_to_end_verification_email_workflow(
        self,
        smtp_settings: Settings,
        temp_template_dir: Path,
        mock_smtp_server: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test complete workflow from NotificationEmailRequestedV1 to SMTP delivery."""

        # Use real implementations for everything except network boundary
        template_renderer = JinjaTemplateRenderer(str(temp_template_dir))
        smtp_provider = SMTPEmailProvider(smtp_settings)

        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=smtp_provider,
            outbox_manager=mock_outbox_manager,
            settings=smtp_settings,
        )

        # Create email request with Swedish characters
        correlation_id = str(uuid4())
        email_request = NotificationEmailRequestedV1(
            message_id=f"verify-{uuid4().hex[:8]}",
            template_id="verification",
            to="åsa.andersson@student.se",
            variables={
                "user_name": "Åsa Andersson",
                "verification_link": "https://hule.education/verify?token=åäö123",
                "expires_at": "2025-01-01T12:00:00Z",
            },
            category="verification",
            correlation_id=correlation_id,
        )

        # Process email request - end-to-end workflow
        await event_processor.process_email_request(email_request)

        # Verify SMTP provider was called with proper parameters
        # Note: connect() and starttls() are handled internally by async context manager
        mock_smtp_server.login.assert_called_once_with(
            smtp_settings.SMTP_USERNAME, smtp_settings.SMTP_PASSWORD
        )
        mock_smtp_server.send_message.assert_called_once()

        # Verify email record was created in repository
        mock_repository.create_email_record.assert_called_once()
        email_record_call = mock_repository.create_email_record.call_args[0][0]
        assert isinstance(email_record_call, EmailRecord)
        assert email_record_call.message_id == email_request.message_id
        assert email_record_call.to_address == email_request.to
        assert "Åsa Andersson" in email_record_call.variables["user_name"]

        # Verify status was updated to sent (may be called multiple times: processing -> sent)
        mock_repository.update_status.assert_called()
        status_calls = mock_repository.update_status.call_args_list

        # Find the final 'sent' status call
        sent_call = None
        for call in status_calls:
            if call.kwargs.get("status") == "sent":
                sent_call = call
                break

        assert sent_call is not None
        assert sent_call.kwargs["message_id"] == email_request.message_id
        assert sent_call.kwargs["status"] == "sent"
        assert "provider_message_id" in sent_call.kwargs

        # Verify EmailSentV1 event was published
        mock_outbox_manager.publish_to_outbox.assert_called_once()
        outbox_call = mock_outbox_manager.publish_to_outbox.call_args
        assert outbox_call[1]["event_type"].endswith("email.sent.v1")

    @pytest.mark.asyncio
    async def test_end_to_end_password_reset_workflow(
        self,
        smtp_settings: Settings,
        temp_template_dir: Path,
        mock_smtp_server: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test complete password reset email workflow with Swedish content."""

        template_renderer = JinjaTemplateRenderer(str(temp_template_dir))
        smtp_provider = SMTPEmailProvider(smtp_settings)

        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=smtp_provider,
            outbox_manager=mock_outbox_manager,
            settings=smtp_settings,
        )

        correlation_id = str(uuid4())
        email_request = NotificationEmailRequestedV1(
            message_id=f"reset-{uuid4().hex[:8]}",
            template_id="password_reset",
            to="erik.ström@teacher.se",
            variables={
                "user_name": "Erik Ström",
                "reset_link": "https://hule.education/reset?token=xyz789",
                "expires_at": "2025-01-01T15:00:00Z",
            },
            category="password_reset",
            correlation_id=correlation_id,
        )

        await event_processor.process_email_request(email_request)

        # Verify SMTP multipart message creation
        send_message_call = mock_smtp_server.send_message.call_args[0][0]
        assert send_message_call.get_charset() == "utf-8"
        # Swedish characters are checked in decoded content below

        # Verify Swedish characters preserved in template rendering
        email_record_call = mock_repository.create_email_record.call_args[0][0]
        assert "Erik Ström" in email_record_call.variables["user_name"]

        # Verify proper event correlation
        outbox_call = mock_outbox_manager.publish_to_outbox.call_args
        envelope_data = outbox_call[1]["event_data"]
        assert str(envelope_data.correlation_id) == correlation_id

    @pytest.mark.asyncio
    async def test_smtp_authentication_failure_workflow(
        self,
        smtp_settings: Settings,
        temp_template_dir: Path,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test complete workflow when SMTP authentication fails."""

        # Mock SMTP to raise authentication error
        import aiosmtplib

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.side_effect = aiosmtplib.SMTPAuthenticationError(535, "Invalid credentials")

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        template_renderer = JinjaTemplateRenderer(str(temp_template_dir))
        smtp_provider = SMTPEmailProvider(smtp_settings)

        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=smtp_provider,
            outbox_manager=mock_outbox_manager,
            settings=smtp_settings,
        )

        correlation_id = str(uuid4())
        email_request = NotificationEmailRequestedV1(
            message_id=f"fail-{uuid4().hex[:8]}",
            template_id="verification",
            to="test@example.com",
            variables={"user_name": "Test User", "verification_link": "https://test.com"},
            category="verification",
            correlation_id=correlation_id,
        )

        await event_processor.process_email_request(email_request)

        # Verify status was updated to failed
        mock_repository.update_status.assert_called()
        status_calls = [call for call in mock_repository.update_status.call_args_list]
        failed_status_call = None
        for call in status_calls:
            # Check both positional and keyword arguments
            if (len(call.args) >= 2 and call.args[1] == "failed") or call.kwargs.get(
                "status"
            ) == "failed":
                failed_status_call = call
                break

        assert failed_status_call is not None
        # Check for failure reason in kwargs
        failure_reason = failed_status_call.kwargs.get("failure_reason", "")
        assert "SMTP authentication failed" in failure_reason

        # Verify EmailDeliveryFailedV1 event was published
        mock_outbox_manager.publish_to_outbox.assert_called()
        outbox_calls = mock_outbox_manager.publish_to_outbox.call_args_list
        failure_call = None
        for call in outbox_calls:
            if "email.delivery_failed.v1" in call[1]["event_type"]:
                failure_call = call
                break

        assert failure_call is not None

    @pytest.mark.asyncio
    async def test_template_rendering_with_smtp_integration(
        self,
        smtp_settings: Settings,
        temp_template_dir: Path,
        mock_smtp_server: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test real Jinja2 template rendering integrated with SMTP delivery."""

        template_renderer = JinjaTemplateRenderer(str(temp_template_dir))
        smtp_provider = SMTPEmailProvider(smtp_settings)

        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=smtp_provider,
            outbox_manager=mock_outbox_manager,
            settings=smtp_settings,
        )

        # Test with comprehensive Swedish variables
        email_request = NotificationEmailRequestedV1(
            message_id=f"template-{uuid4().hex[:8]}",
            template_id="verification",
            to="maria.öberg@skola.se",
            variables={
                "user_name": "Maria Öberg",
                "verification_link": "https://hule.education/verify?token=åäö456",
                "expires_at": "2025-12-31T23:59:59Z",
            },
            category="verification",
            correlation_id=str(uuid4()),
        )

        await event_processor.process_email_request(email_request)

        # Verify SMTP message contains rendered Swedish content
        send_message_call = mock_smtp_server.send_message.call_args[0][0]

        # Check subject was rendered correctly
        assert "Bekräfta ditt HuleEdu konto" in send_message_call["Subject"]

        # Check Swedish characters preserved in body - decode content properly
        parts = list(send_message_call.walk())
        swedish_content_found = False
        for part in parts:
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                if (
                    "Maria Öberg" in payload
                    and "Välkommen till HuleEdu" in payload
                    and "åäö456" in payload
                ):
                    swedish_content_found = True
                    break
        assert swedish_content_found

        # Verify multipart structure (HTML + text)
        assert send_message_call.is_multipart()

        # Verify UTF-8 encoding
        assert send_message_call.get_charset() == "utf-8"

    @pytest.mark.parametrize(
        "template_id,subject_contains,content_contains",
        [
            ("verification", "Bekräfta", "Välkommen till HuleEdu"),
            ("password_reset", "Återställ", "Återställ ditt lösenord"),
        ],
    )
    @pytest.mark.asyncio
    async def test_multiple_template_workflows(
        self,
        template_id: str,
        subject_contains: str,
        content_contains: str,
        smtp_settings: Settings,
        temp_template_dir: Path,
        mock_smtp_server: AsyncMock,
        mock_repository: AsyncMock,
        mock_outbox_manager: AsyncMock,
    ) -> None:
        """Test multiple Swedish template types with SMTP integration."""

        template_renderer = JinjaTemplateRenderer(str(temp_template_dir))
        smtp_provider = SMTPEmailProvider(smtp_settings)

        event_processor = EmailEventProcessor(
            repository=mock_repository,
            template_renderer=template_renderer,
            email_provider=smtp_provider,
            outbox_manager=mock_outbox_manager,
            settings=smtp_settings,
        )

        email_request = NotificationEmailRequestedV1(
            message_id=f"{template_id}-{uuid4().hex[:8]}",
            template_id=template_id,
            to="test.användare@hule.education",
            variables={
                "user_name": "Test Användare",
                "verification_link": "https://hule.education/verify?token=test",
                "reset_link": "https://hule.education/reset?token=test",
                "expires_at": "2025-01-01T12:00:00Z",
            },
            category=template_id,
            correlation_id=str(uuid4()),
        )

        await event_processor.process_email_request(email_request)

        # Verify template-specific content rendered correctly
        send_message_call = mock_smtp_server.send_message.call_args[0][0]
        assert subject_contains in send_message_call["Subject"]

        # Check content in decoded payloads
        parts = list(send_message_call.walk())
        content_found = user_found = False
        for part in parts:
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                if content_contains in payload:
                    content_found = True
                if "Test Användare" in payload:
                    user_found = True

        assert content_found and user_found

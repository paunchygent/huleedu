"""Integration tests for SMTP email provider core functionality.

Tests SMTPEmailProvider protocol compliance, configuration validation, Swedish character 
support, message creation, authentication flow, and success scenarios following Rule 075 
methodology. Focus on behavioral testing without @patch usage.
"""

from __future__ import annotations

import asyncio
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import aiosmtplib  # type: ignore[import-not-found]
from huleedu_service_libs.error_handling import HuleEduError

from services.email_service.config import Settings
from services.email_service.implementations.provider_smtp_impl import SMTPEmailProvider
from services.email_service.protocols import EmailProvider, EmailSendResult


class TestSMTPProviderCore:
    """Comprehensive tests for SMTP email provider core functionality."""

    @pytest.fixture
    def smtp_settings(self) -> Settings:
        """Test SMTP settings with Swedish defaults."""
        return Settings(
            SMTP_HOST="mail.privateemail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="test_password",
            SMTP_USE_TLS=True,
            SMTP_TIMEOUT=30,
            DEFAULT_FROM_EMAIL="noreply@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Test",
            EMAIL_PROVIDER="smtp",
        )

    @pytest.fixture
    def provider(self, smtp_settings: Settings) -> SMTPEmailProvider:
        """SMTP provider instance for testing."""
        return SMTPEmailProvider(smtp_settings)

    @pytest.fixture
    def mock_smtp_server(self) -> AsyncMock:
        """Mock SMTP server that simulates successful connections."""
        mock_smtp = AsyncMock()
        # Configure successful authentication
        mock_smtp.login = AsyncMock(return_value=None)
        # Configure successful message sending (no errors)
        mock_smtp.send_message = AsyncMock(return_value={})
        # Configure async context manager protocol
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)
        return mock_smtp

    def test_protocol_compliance(self, provider: SMTPEmailProvider) -> None:
        """Test SMTPEmailProvider implements EmailProvider protocol correctly."""
        # Assert: Protocol compliance through duck typing
        assert hasattr(provider, "send_email")
        assert hasattr(provider, "get_provider_name")
        assert callable(provider.send_email)
        assert callable(provider.get_provider_name)
        
        # Verify method signatures match protocol
        import inspect
        send_email_sig = inspect.signature(provider.send_email)
        assert "to" in send_email_sig.parameters
        assert "subject" in send_email_sig.parameters
        assert "html_content" in send_email_sig.parameters

    def test_provider_identification(self, provider: SMTPEmailProvider) -> None:
        """Test provider returns correct identification."""
        provider_name = provider.get_provider_name()
        assert provider_name == "smtp"
        assert isinstance(provider_name, str)
        assert len(provider_name) > 0

    @pytest.mark.parametrize(
        "host,port,username,password,use_tls,timeout",
        [
            ("mail.privateemail.com", 587, "user@example.se", "password", True, 30),
            ("smtp.gmail.com", 465, "user@gmail.com", "app_password", True, 60),
            ("localhost", 1025, None, None, False, 10),  # Dev SMTP server
            ("mail.server.se", 25, "test@huleedu.se", "åäö_password_123", False, 5),
        ],
    )
    def test_configuration_handling(
        self, host: str, port: int, username: str | None, password: str | None, 
        use_tls: bool, timeout: int
    ) -> None:
        """Test SMTP settings configuration handling."""
        settings = Settings(
            SMTP_HOST=host,
            SMTP_PORT=port,
            SMTP_USERNAME=username,
            SMTP_PASSWORD=password,
            SMTP_USE_TLS=use_tls,
            SMTP_TIMEOUT=timeout,
            DEFAULT_FROM_EMAIL="test@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Test",
        )
        
        # Act & Assert: Provider creation should succeed
        provider = SMTPEmailProvider(settings)
        assert provider.settings.SMTP_HOST == host
        assert provider.settings.SMTP_PORT == port
        assert provider.settings.SMTP_USERNAME == username
        assert provider.settings.SMTP_PASSWORD == password
        assert provider.settings.SMTP_USE_TLS == use_tls
        assert provider.settings.SMTP_TIMEOUT == timeout

    @pytest.mark.parametrize(
        "subject,html_content,expected_subject_chars,expected_content_chars",
        [
            # Swedish characters in subject and content - MANDATORY for email domain
            (
                "Välkommen till HuleEdu - Språkutveckling för alla",
                "<h1>Hej Åsa!</h1><p>Välkommen till vår svenska plattform för språkutveckling.</p>",
                ["Välkommen", "Språkutveckling"],
                ["Åsa", "Välkommen", "språkutveckling"],
            ),
            # Mixed Swedish and English content
            (
                "English Subject with Swedish names: Björk & Andersson",
                "<div>Student Märta Öhman completed the Swedish grammar test with excellent results.</div>",
                ["Björk", "Andersson"],
                ["Märta", "Öhman"],
            ),
            # Long subject with Swedish characters (>78 chars)
            (
                "Meddelande från HuleEdu om språkutveckling och grammatikkontroll för elever i klass 7-9 på Stockholms skolor",
                "<p>Detta är ett långt meddelande med svenska tecken: åäöÅÄÖ</p>",
                ["språkutveckling", "grammatikkontroll"],
                ["åäöÅÄÖ"],
            ),
        ],
    )
    async def test_swedish_character_support(
        self,
        provider: SMTPEmailProvider,
        mock_smtp_server: AsyncMock,
        monkeypatch: Any,
        subject: str,
        html_content: str,
        expected_subject_chars: list[str],
        expected_content_chars: list[str],
    ) -> None:
        """Test Swedish character support in email messages (ÅÄÖ mandatory for email domain)."""
        # Arrange: Mock SMTP connection
        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Send email with Swedish characters
        result = await provider.send_email(
            to="test@svenskaskolan.se",
            subject=subject,
            html_content=html_content,
            text_content=None,  # Let provider generate from HTML
        )

        # Assert: Email sent successfully
        assert result.success is True
        assert result.provider_message_id is not None
        assert result.error_message is None

        # Assert: SMTP server received correctly formatted message
        assert mock_smtp_server.send_message.call_count == 1
        message_call = mock_smtp_server.send_message.call_args
        sent_message: EmailMessage = message_call.args[0]

        # Verify message headers preserve Swedish characters
        assert sent_message["Subject"] == subject
        assert sent_message["From"] == "HuleEdu Test <noreply@huleedu.se>"
        assert sent_message["To"] == "test@svenskaskolan.se"

        # Verify UTF-8 charset is set
        assert sent_message.get_charset() == "utf-8"

        # Verify Swedish characters preserved in subject
        for swedish_char in expected_subject_chars:
            assert swedish_char in sent_message["Subject"]

        # Verify message is multipart (HTML + text)
        assert sent_message.is_multipart()

        # Get message parts for content verification
        parts = list(sent_message.walk())
        html_part = None
        text_part = None
        
        for part in parts:
            if part.get_content_type() == "text/html":
                html_part = part
            elif part.get_content_type() == "text/plain":
                text_part = part

        assert html_part is not None, "HTML part should exist"
        assert text_part is not None, "Text part should exist"

        # Verify Swedish characters preserved in content
        html_payload_raw = html_part.get_payload(decode=True)
        text_payload_raw = text_part.get_payload(decode=True)
        
        html_payload = html_payload_raw.decode('utf-8') if isinstance(html_payload_raw, bytes) else str(html_payload_raw)
        text_payload = text_payload_raw.decode('utf-8') if isinstance(text_payload_raw, bytes) else str(text_payload_raw)

        for swedish_char in expected_content_chars:
            assert swedish_char in html_payload, f"Swedish char '{swedish_char}' missing from HTML"
            assert swedish_char in text_payload, f"Swedish char '{swedish_char}' missing from text"

    async def test_multipart_message_generation(
        self, provider: SMTPEmailProvider, mock_smtp_server: AsyncMock, monkeypatch: Any
    ) -> None:
        """Test multipart HTML/text message generation."""
        # Arrange: Mock SMTP connection
        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        html_content = """
        <html>
        <head><title>Svenska Test</title></head>
        <body>
            <h1>Välkommen Åsa!</h1>
            <p>Detta är en <strong>HTML</strong> version av meddelandet.</p>
            <ul>
                <li>Punkt ett: språkutveckling</li>
                <li>Punkt två: grammatikkontroll</li>
            </ul>
        </body>
        </html>
        """

        # Act: Send with HTML content only (text should be generated)
        result = await provider.send_email(
            to="student@huleedu.se",
            subject="Multipart Test - Svenska tecken ÅÄÖ",
            html_content=html_content,
            text_content=None,
        )

        # Assert: Successful send
        assert result.success is True

        # Assert: Message structure
        sent_message = mock_smtp_server.send_message.call_args.args[0]
        assert sent_message.is_multipart()

        # Get parts
        parts = list(sent_message.walk())
        content_parts = [p for p in parts if not p.is_multipart()]
        
        assert len(content_parts) == 2, "Should have text and HTML parts"

        # Verify text part was generated from HTML
        text_part = next(p for p in content_parts if p.get_content_type() == "text/plain")
        text_payload_raw = text_part.get_payload(decode=True)
        text_content = text_payload_raw.decode('utf-8') if isinstance(text_payload_raw, bytes) else str(text_payload_raw)

        # Text should contain Swedish characters without HTML tags
        assert "Välkommen Åsa!" in text_content
        assert "språkutveckling" in text_content
        assert "grammatikkontroll" in text_content
        assert "<html>" not in text_content
        assert "<strong>" not in text_content

    async def test_custom_text_content_preservation(
        self, provider: SMTPEmailProvider, mock_smtp_server: AsyncMock, monkeypatch: Any
    ) -> None:
        """Test custom text content is preserved when provided."""
        # Arrange: Mock SMTP connection
        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        html_content = "<h1>HTML Version: Språktest för Åsa</h1>"
        custom_text = "Textversion: Språktest för Åsa\n\nIngen HTML-formatering här."

        # Act: Send with both HTML and custom text
        result = await provider.send_email(
            to="test@huleedu.se",
            subject="Custom Text Test",
            html_content=html_content,
            text_content=custom_text,
        )

        # Assert: Successful send
        assert result.success is True

        # Assert: Custom text preserved
        sent_message = mock_smtp_server.send_message.call_args.args[0]
        parts = list(sent_message.walk())
        text_part = next(p for p in parts if p.get_content_type() == "text/plain")
        
        text_payload_raw = text_part.get_payload(decode=True)
        text_payload = text_payload_raw.decode('utf-8') if isinstance(text_payload_raw, bytes) else str(text_payload_raw)
        assert text_payload.strip() == custom_text.strip()

    @pytest.mark.parametrize(
        "to_address,from_email,from_name,expected_from_header",
        [
            # Use default sender
            ("student@huleedu.se", None, None, "HuleEdu Test <noreply@huleedu.se>"),
            # Custom sender with Swedish name
            ("lärare@svenskaskolan.se", "anna.lärare@huleedu.se", "Anna Lindström", "Anna Lindström <anna.lärare@huleedu.se>"),
            # Custom sender with special characters
            ("test@example.com", "björn@huleedu.se", "Björn Andersson", "Björn Andersson <björn@huleedu.se>"),
        ],
    )
    async def test_sender_information_handling(
        self,
        provider: SMTPEmailProvider,
        mock_smtp_server: AsyncMock,
        monkeypatch: Any,
        to_address: str,
        from_email: str | None,
        from_name: str | None,
        expected_from_header: str,
    ) -> None:
        """Test sender information handling with Swedish characters."""
        # Arrange: Mock SMTP connection
        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Send email with sender information
        result = await provider.send_email(
            to=to_address,
            subject="Sender Test",
            html_content="<p>Test content</p>",
            from_email=from_email,
            from_name=from_name,
        )

        # Assert: Successful send
        assert result.success is True

        # Assert: Correct sender information
        sent_message = mock_smtp_server.send_message.call_args.args[0]
        assert sent_message["From"] == expected_from_header
        assert sent_message["To"] == to_address

    async def test_authentication_flow(self, provider: SMTPEmailProvider, monkeypatch: Any) -> None:
        """Test successful SMTP authentication flow."""
        # Arrange: Mock successful SMTP connection and authentication
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(return_value={})
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)

        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            # Verify connection parameters - SMTP constructor uses keyword args
            assert kwargs.get("hostname") == "mail.privateemail.com"
            assert kwargs.get("port") == 587
            assert kwargs.get("start_tls") is True
            assert kwargs.get("timeout") == 30
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Send email (triggers authentication)
        result = await provider.send_email(
            to="test@example.com",
            subject="Auth Test",
            html_content="<p>Test</p>",
        )

        # Assert: Successful result
        assert result.success is True
        assert result.provider_message_id is not None
        assert result.error_message is None

        # Assert: Authentication was attempted with correct credentials
        mock_smtp.login.assert_called_once_with("test@huleedu.se", "test_password")

        # Assert: Message was sent
        mock_smtp.send_message.assert_called_once()

    async def test_authentication_failure(self, provider: SMTPEmailProvider, monkeypatch: Any) -> None:
        """Test authentication failure handling."""
        # Arrange: Mock SMTP authentication failure
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(
            side_effect=aiosmtplib.SMTPAuthenticationError(
                535, "Authentication failed: Invalid username or password"
            )
        )
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)

        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Attempt to send email
        result = await provider.send_email(
            to="test@example.com",
            subject="Auth Failure Test",
            html_content="<p>Test</p>",
        )

        # Assert: Failure result with appropriate error
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message is not None
        assert "SMTP authentication failed" in result.error_message
        assert "Authentication failed" in result.error_message

        # Assert: Send was not attempted after auth failure
        mock_smtp.send_message.assert_not_called()

    async def test_connection_failure(self, provider: SMTPEmailProvider, monkeypatch: Any) -> None:
        """Test SMTP connection failure handling."""
        # Arrange: Mock SMTP connection failure
        def mock_smtp_class(*args: Any, **kwargs: Any) -> None:
            raise aiosmtplib.SMTPConnectError("Connection refused")

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Attempt to send email
        result = await provider.send_email(
            to="test@example.com",
            subject="Connection Test",
            html_content="<p>Test</p>",
        )

        # Assert: Failure result with connection error
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message is not None
        assert "SMTP connection failed" in result.error_message
        assert "Connection refused" in result.error_message

    async def test_successful_email_send_result(
        self, provider: SMTPEmailProvider, mock_smtp_server: AsyncMock, monkeypatch: Any
    ) -> None:
        """Test successful email sending with proper EmailSendResult."""
        # Arrange: Mock successful SMTP operation
        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Send email
        result = await provider.send_email(
            to="recipient@example.com",
            subject="Success Test",
            html_content="<p>Success message</p>",
        )

        # Assert: Proper EmailSendResult structure
        assert isinstance(result, EmailSendResult)
        assert result.success is True
        assert result.provider_message_id is not None
        assert isinstance(result.provider_message_id, str)
        assert result.provider_message_id.startswith("smtp_")
        assert result.error_message is None

        # Assert: Provider message ID is deterministic for same inputs
        expected_hash = hash(f"recipient@example.com_Success Test_noreply@huleedu.se")
        expected_provider_id = f"smtp_{expected_hash}"
        assert result.provider_message_id == expected_provider_id

    async def test_partial_send_failure(
        self, provider: SMTPEmailProvider, monkeypatch: Any
    ) -> None:
        """Test handling of partial send failures from SMTP server."""
        # Arrange: Mock partial send failure
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(
            return_value={
                "invalid@domain.com": (550, "Mailbox not found"),
                "blocked@spam.com": (554, "Message rejected: spam"),
            }
        )
        mock_smtp.__aenter__ = AsyncMock(return_value=mock_smtp)
        mock_smtp.__aexit__ = AsyncMock(return_value=None)

        def mock_smtp_class(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_class)

        # Act: Send email
        result = await provider.send_email(
            to="recipient@example.com",
            subject="Partial Failure Test",
            html_content="<p>Test message</p>",
        )

        # Assert: Failure result with error details
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message is not None
        assert "Partial send failure" in result.error_message
        assert "invalid@domain.com: (550, 'Mailbox not found')" in result.error_message
        assert "blocked@spam.com: (554, 'Message rejected: spam')" in result.error_message

    async def test_html_to_text_conversion_with_swedish(self, provider: SMTPEmailProvider) -> None:
        """Test HTML to text conversion preserves Swedish characters."""
        # Arrange: HTML content with Swedish characters and formatting
        html_content = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Välkommen till HuleEdu</h1>
            <p>Hej <strong>Åsa Lindström</strong>!</p>
            <p>Vi hoppas du har en <em>fantastisk</em> dag.</p>
            <ul>
                <li>Språkutveckling för alla</li>
                <li>Grammatikkontroll med AI</li>
            </ul>
            <p>Specialtecken: &lt;script&gt; &amp; &quot;test&quot; &#39;test&#39;</p>
        </body>
        </html>
        """

        # Act: Convert HTML to text using provider's internal method
        text_content = provider._html_to_text(html_content)

        # Assert: Swedish characters preserved
        assert "Välkommen till HuleEdu" in text_content
        assert "Åsa Lindström" in text_content
        assert "Språkutveckling för alla" in text_content
        assert "Grammatikkontroll med AI" in text_content

        # Assert: HTML tags removed
        assert "<html>" not in text_content
        assert "<strong>" not in text_content
        assert "<em>" not in text_content
        assert "<ul>" not in text_content
        assert "<li>" not in text_content

        # Assert: HTML entities converted
        assert "&lt;script&gt;" not in text_content
        assert "<script>" in text_content
        assert "&amp;" not in text_content
        assert " & " in text_content
        assert "&quot;" not in text_content
        assert '"test"' in text_content
        assert "&#39;" not in text_content
        assert "'test'" in text_content

        # Assert: Whitespace cleaned up
        assert text_content.strip() == text_content
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

import aiosmtplib  # type: ignore[import-not-found]
import pytest
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.implementations.provider_smtp_impl import SMTPEmailProvider
from services.email_service.protocols import EmailSendResult


class TestSMTPProviderConfiguration:
    """Tests for SMTP provider configuration and validation."""

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

    def test_smtp_provider_protocol_compliance(self, smtp_settings: Settings) -> None:
        """Test SMTPEmailProvider implements EmailProvider protocol correctly."""
        # Act: Create provider instance
        provider = SMTPEmailProvider(smtp_settings)

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

    def test_provider_name_identification(self, smtp_settings: Settings) -> None:
        """Test provider returns correct identification."""
        # Arrange & Act
        provider = SMTPEmailProvider(smtp_settings)
        provider_name = provider.get_provider_name()

        # Assert: Correct provider identification
        assert provider_name == "smtp"
        assert isinstance(provider_name, str)
        assert len(provider_name) > 0

    @pytest.mark.parametrize(
        "host,port,username,password,use_tls,timeout,is_valid",
        [
            # Valid configurations
            ("mail.privateemail.com", 587, "user@example.se", "password", True, 30, True),
            ("smtp.gmail.com", 465, "user@gmail.com", "app_password", True, 60, True),
            ("localhost", 1025, None, None, False, 10, True),  # Dev SMTP server
            # Edge cases
            ("mail.server.se", 25, "test@huleedu.se", "åäö_password_123", False, 5, True),
            # Configuration validation (constructor doesn't validate, but we test settings)
            ("", 587, "user", "pass", True, 30, True),  # Empty host (valid for Settings)
            ("host", 0, "user", "pass", True, 30, True),  # Zero port (valid for Settings)
        ],
    )
    def test_smtp_settings_configuration(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        use_tls: bool,
        timeout: int,
        is_valid: bool,
    ) -> None:
        """Test SMTP settings configuration validation."""
        # Arrange: Create settings with specific configuration
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

        # Act & Assert: Provider creation should succeed regardless
        # (validation happens at connection time, not construction)
        provider = SMTPEmailProvider(settings)
        assert provider.settings.SMTP_HOST == host
        assert provider.settings.SMTP_PORT == port
        assert provider.settings.SMTP_USERNAME == username
        assert provider.settings.SMTP_PASSWORD == password
        assert provider.settings.SMTP_USE_TLS == use_tls
        assert provider.settings.SMTP_TIMEOUT == timeout


class TestSMTPEmailMessageCreation:
    """Tests for SMTP email message creation and formatting."""

    @pytest.fixture
    def provider(self) -> SMTPEmailProvider:
        """SMTP provider with Swedish-compatible settings."""
        settings = Settings(
            SMTP_HOST="mail.privateemail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="test_password",
            DEFAULT_FROM_EMAIL="noreply@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu Svenska",
            EMAIL_PROVIDER="smtp",
        )
        return SMTPEmailProvider(settings)

    @pytest.fixture
    def mock_smtp_server(self) -> AsyncMock:
        """Mock SMTP server that simulates successful connections."""
        mock_smtp = AsyncMock()

        # Configure successful authentication
        mock_smtp.login = AsyncMock(return_value=None)

        # Configure successful message sending (no errors)
        mock_smtp.send_message = AsyncMock(return_value={})

        return mock_smtp

    @pytest.mark.parametrize(
        "subject,html_content,expected_subject_chars,expected_content_chars",
        [
            # Swedish characters in subject and content
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
            # Long subject with Swedish characters
            (
                "Meddelande från HuleEdu om språkutveckling och grammatikkontroll för elever i klass 7-9 på Stockholms skolor",
                "<p>Detta är ett långt meddelande med svenska tecken: åäöÅÄÖ</p>",
                ["språkutveckling", "grammatikkontroll"],
                ["åäöÅÄÖ"],
            ),
            # HTML entities and special formatting
            (
                "Test & Validation för HTML-innehåll",
                """<div style="font-family: Arial;">
                   <h2>Rubrik: Språktest Åsa & Erik</h2>
                   <p>Innehåll med "citattecken" och 'apostrofer'</p>
                   <p>Specialtecken: &lt; &gt; &amp; &quot; &#39;</p>
                   </div>""",
                ["Validation", "HTML-innehåll"],
                ["Språktest", "citattecken", "apostrofer"],
            ),
        ],
    )
    async def test_swedish_character_support_in_messages(
        self,
        provider: SMTPEmailProvider,
        mock_smtp_server: AsyncMock,
        subject: str,
        html_content: str,
        expected_subject_chars: list[str],
        expected_content_chars: list[str],
        monkeypatch: Any,
    ) -> None:
        """Test Swedish character support in email messages (ÅÄÖ mandatory for email domain)."""

        # Arrange: Mock SMTP connection
        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email with Swedish characters
        result = await provider.send_email(
            to=EmailStr("test@svenskaskolan.se"),
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
        assert sent_message["From"] == "HuleEdu Svenska <noreply@huleedu.se>"
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

        # Should have HTML and text parts
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
        html_payload = html_part.get_payload()
        text_payload = text_part.get_payload()

        for swedish_char in expected_content_chars:
            assert swedish_char in html_payload, f"Swedish char '{swedish_char}' missing from HTML"
            assert swedish_char in text_payload, f"Swedish char '{swedish_char}' missing from text"

    async def test_multipart_message_generation(
        self,
        provider: SMTPEmailProvider,
        mock_smtp_server: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """Test multipart HTML/text message generation."""

        # Arrange: Mock SMTP connection
        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

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
            to=EmailStr("student@huleedu.se"),
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
        text_content = text_part.get_payload()

        # Text should contain Swedish characters without HTML tags
        assert "Välkommen Åsa!" in text_content
        assert "språkutveckling" in text_content
        assert "grammatikkontroll" in text_content
        assert "<html>" not in text_content
        assert "<strong>" not in text_content

    async def test_custom_text_content_preservation(
        self,
        provider: SMTPEmailProvider,
        mock_smtp_server: AsyncMock,
        monkeypatch: Any,
    ) -> None:
        """Test custom text content is preserved when provided."""

        # Arrange: Mock SMTP connection
        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        html_content = "<h1>HTML Version: Språktest för Åsa</h1>"
        custom_text = "Textversion: Språktest för Åsa\n\nIngen HTML-formatering här."

        # Act: Send with both HTML and custom text
        result = await provider.send_email(
            to=EmailStr("test@huleedu.se"),
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

        assert text_part.get_payload() == custom_text

    @pytest.mark.parametrize(
        "to_address,from_email,from_name,expected_from_header",
        [
            # Use default sender
            (
                "student@huleedu.se",
                None,
                None,
                "HuleEdu Svenska <noreply@huleedu.se>",
            ),
            # Custom sender with Swedish name
            (
                "lärare@svenskaskolan.se",
                "anna.lärare@huleedu.se",
                "Anna Lindström",
                "Anna Lindström <anna.lärare@huleedu.se>",
            ),
            # Custom sender with special characters
            (
                "test@example.com",
                "björn@huleedu.se",
                "Björn Andersson (HuleEdu)",
                "Björn Andersson (HuleEdu) <björn@huleedu.se>",
            ),
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
        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp_server

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email with sender information
        result = await provider.send_email(
            to=EmailStr(to_address),
            subject="Sender Test",
            html_content="<p>Test content</p>",
            from_email=EmailStr(from_email) if from_email else None,
            from_name=from_name,
        )

        # Assert: Successful send
        assert result.success is True

        # Assert: Correct sender information
        sent_message = mock_smtp_server.send_message.call_args.args[0]
        assert sent_message["From"] == expected_from_header
        assert sent_message["To"] == to_address


class TestSMTPAuthenticationFlow:
    """Tests for SMTP authentication and connection flow."""

    @pytest.fixture
    def provider(self) -> SMTPEmailProvider:
        """SMTP provider for authentication tests."""
        settings = Settings(
            SMTP_HOST="mail.privateemail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="secure_password_123",
            SMTP_USE_TLS=True,
            DEFAULT_FROM_EMAIL="noreply@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu",
        )
        return SMTPEmailProvider(settings)

    async def test_successful_authentication_flow(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
    ) -> None:
        """Test successful SMTP authentication flow."""
        # Arrange: Mock successful SMTP connection and authentication
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(return_value={})

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            # Verify connection parameters
            assert args[0] == "mail.privateemail.com"  # hostname
            assert kwargs.get("port") == 587
            assert kwargs.get("start_tls") is True
            assert kwargs.get("timeout") == 30
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email (triggers authentication)
        result = await provider.send_email(
            to=EmailStr("test@example.com"),
            subject="Auth Test",
            html_content="<p>Test</p>",
        )

        # Assert: Successful result
        assert result.success is True
        assert result.provider_message_id is not None
        assert result.error_message is None

        # Assert: Authentication was attempted with correct credentials
        mock_smtp.login.assert_called_once_with("test@huleedu.se", "secure_password_123")

        # Assert: Message was sent
        mock_smtp.send_message.assert_called_once()

    async def test_authentication_failure_handling(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
    ) -> None:
        """Test authentication failure handling."""
        # Arrange: Mock SMTP authentication failure
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(
            side_effect=aiosmtplib.SMTPAuthenticationError(
                535, "Authentication failed: Invalid username or password"
            )
        )

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Attempt to send email
        result = await provider.send_email(
            to=EmailStr("test@example.com"),
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

    async def test_connection_failure_handling(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
    ) -> None:
        """Test SMTP connection failure handling."""

        # Arrange: Mock SMTP connection failure
        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            raise aiosmtplib.SMTPConnectError("Connection refused")

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Attempt to send email
        result = await provider.send_email(
            to=EmailStr("test@example.com"),
            subject="Connection Test",
            html_content="<p>Test</p>",
        )

        # Assert: Failure result with connection error
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message is not None
        assert "SMTP connection failed" in result.error_message
        assert "Connection refused" in result.error_message


class TestSMTPSuccessScenarios:
    """Tests for successful SMTP email sending scenarios."""

    @pytest.fixture
    def provider(self) -> SMTPEmailProvider:
        """SMTP provider for success scenario tests."""
        settings = Settings(
            SMTP_HOST="mail.privateemail.com",
            SMTP_PORT=587,
            SMTP_USERNAME="sender@huleedu.se",
            SMTP_PASSWORD="password",
            DEFAULT_FROM_EMAIL="noreply@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu System",
        )
        return SMTPEmailProvider(settings)

    async def test_successful_email_send_with_proper_result(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
    ) -> None:
        """Test successful email sending with proper EmailSendResult."""
        # Arrange: Mock successful SMTP operation
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(return_value={})  # No errors

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email
        result = await provider.send_email(
            to=EmailStr("recipient@example.com"),
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
        # (useful for idempotency and tracking)
        expected_hash = hash("recipient@example.com_Success Test_noreply@huleedu.se")
        expected_provider_id = f"smtp_{expected_hash}"
        assert result.provider_message_id == expected_provider_id

    async def test_partial_send_failure_handling(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
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

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email
        result = await provider.send_email(
            to=EmailStr("recipient@example.com"),
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

    @pytest.mark.parametrize(
        "smtp_exception,expected_error_type",
        [
            (
                aiosmtplib.SMTPRecipientsRefused({}),
                "SMTP error",
            ),
            (
                aiosmtplib.SMTPDataError(554, "Message rejected"),
                "SMTP error",
            ),
            (
                aiosmtplib.SMTPResponseException(500, "Internal server error"),
                "SMTP error",
            ),
            (
                asyncio.TimeoutError("Connection timeout"),
                "Unexpected error sending email",
            ),
            (
                ValueError("Invalid email format"),
                "Unexpected error sending email",
            ),
        ],
    )
    async def test_smtp_exception_handling(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
        smtp_exception: Exception,
        expected_error_type: str,
    ) -> None:
        """Test various SMTP and general exception handling."""
        # Arrange: Mock SMTP to raise specific exception
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(side_effect=smtp_exception)

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Attempt to send email
        result = await provider.send_email(
            to=EmailStr("test@example.com"),
            subject="Exception Test",
            html_content="<p>Test</p>",
        )

        # Assert: Proper error handling
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message is not None
        assert expected_error_type in result.error_message


class TestSMTPDomainSpecificEdgeCases:
    """Tests for domain-specific edge cases in email processing."""

    @pytest.fixture
    def provider(self) -> SMTPEmailProvider:
        """SMTP provider for edge case testing."""
        settings = Settings(
            SMTP_HOST="test.smtp.server",
            SMTP_PORT=587,
            SMTP_USERNAME="test@huleedu.se",
            SMTP_PASSWORD="password",
            DEFAULT_FROM_EMAIL="noreply@huleedu.se",
            DEFAULT_FROM_NAME="HuleEdu",
        )
        return SMTPEmailProvider(settings)

    @pytest.mark.parametrize(
        "subject,html_content,text_content,expected_behavior",
        [
            # Empty content edge cases
            (
                "Empty Content Test",
                "",
                "",
                "should_succeed_with_empty_content",
            ),
            (
                "Only HTML",
                "<p>HTML only content with Swedish: Åsa</p>",
                None,
                "should_generate_text_from_html",
            ),
            # Long subject line (>78 chars recommended limit)
            (
                "Detta är en mycket lång rubrik som överskrider den rekommenderade gränsen för e-postämnen på 78 tecken",
                "<p>Long subject test</p>",
                None,
                "should_handle_long_subject",
            ),
            # Swedish characters in subject lines
            (
                "Språktest för Åsa, Erik & Märta - Grammatikkontroll ÅÄÖ",
                "<p>Swedish subject test</p>",
                "Swedish subject test",
                "should_preserve_swedish_subject",
            ),
            # HTML-only vs multipart scenarios
            (
                "HTML Only Test",
                "<html><body><h1>Only HTML</h1><p>No text version</p></body></html>",
                None,
                "should_create_multipart_from_html",
            ),
        ],
    )
    async def test_domain_specific_edge_cases(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
        subject: str,
        html_content: str,
        text_content: str | None,
        expected_behavior: str,
    ) -> None:
        """Test domain-specific edge cases for educational email processing."""
        # Arrange: Mock successful SMTP
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)
        mock_smtp.send_message = AsyncMock(return_value={})

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Send email with edge case parameters
        result = await provider.send_email(
            to=EmailStr("test@example.com"),
            subject=subject,
            html_content=html_content,
            text_content=text_content,
        )

        # Assert: All edge cases should succeed (SMTP provider is tolerant)
        assert result.success is True
        assert result.provider_message_id is not None

        # Assert: Message was properly formatted
        sent_message = mock_smtp.send_message.call_args.args[0]
        assert sent_message["Subject"] == subject

        # Behavior-specific assertions
        if expected_behavior == "should_generate_text_from_html":
            # Should have generated text content from HTML
            parts = list(sent_message.walk())
            text_part = next((p for p in parts if p.get_content_type() == "text/plain"), None)
            assert text_part is not None
            text_payload = text_part.get_payload()
            assert "HTML only content" in text_payload
            assert "Åsa" in text_payload  # Swedish chars preserved
            assert "<p>" not in text_payload  # HTML tags removed

        elif expected_behavior == "should_preserve_swedish_subject":
            # Swedish characters should be preserved in subject
            assert "Språktest" in sent_message["Subject"]
            assert "ÅÄÖ" in sent_message["Subject"]

        elif expected_behavior == "should_handle_long_subject":
            # Long subjects should be handled without truncation
            assert len(sent_message["Subject"]) > 78
            assert "Språktest" in sent_message["Subject"]

    @pytest.mark.parametrize(
        "invalid_email,expected_error_behavior",
        [
            # These will be caught by EmailStr validation before reaching provider
            # But we test provider behavior if invalid data somehow reaches it
            ("not-an-email", "provider_should_attempt_send"),
            ("user@", "provider_should_attempt_send"),
            ("@domain.com", "provider_should_attempt_send"),
            ("user@@domain.com", "provider_should_attempt_send"),
        ],
    )
    async def test_invalid_email_address_handling(
        self,
        provider: SMTPEmailProvider,
        monkeypatch: Any,
        invalid_email: str,
        expected_error_behavior: str,
    ) -> None:
        """Test behavior with invalid email addresses."""
        # Note: EmailStr validation normally prevents this,
        # but we test provider behavior if validation is bypassed

        # Arrange: Mock SMTP to reject invalid addresses
        mock_smtp = AsyncMock()
        mock_smtp.login = AsyncMock(return_value=None)

        # Simulate SMTP server rejecting invalid address
        mock_smtp.send_message = AsyncMock(
            return_value={invalid_email: (550, "Invalid recipient address")}
        )

        async def mock_smtp_context(*args: Any, **kwargs: Any) -> AsyncMock:
            return mock_smtp

        monkeypatch.setattr("aiosmtplib.SMTP", mock_smtp_context)

        # Act: Attempt to send to invalid address (bypass EmailStr validation)
        # In real usage, this would be caught earlier, but we test provider behavior
        result = await provider.send_email(
            to=invalid_email,  # type: ignore[arg-type]
            subject="Invalid Email Test",
            html_content="<p>Test</p>",
        )

        # Assert: Provider detects and reports partial failure
        if expected_error_behavior == "provider_should_attempt_send":
            assert result.success is False
            assert result.error_message is not None
            assert "Partial send failure" in result.error_message
            assert "Invalid recipient address" in result.error_message

    async def test_html_to_text_conversion_with_swedish_content(
        self,
        provider: SMTPEmailProvider,
    ) -> None:
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
                <li>Personlig feedback på svenska</li>
            </ul>
            <div>Med vänliga hälsningar,<br>HuleEdu Teamet</div>
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
        assert "\n\n\n" not in text_content
        assert text_content.strip() == text_content

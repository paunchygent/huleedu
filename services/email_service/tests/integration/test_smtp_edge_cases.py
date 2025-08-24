"""Edge case and error handling tests for SMTP email provider.

Tests comprehensive error scenarios, network failures, configuration edge cases,
and Swedish character handling following Rule 075 methodology with minimal mocking.
Focus on real error conditions and proper EmailSendResult behavior verification.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import aiosmtplib
import pytest

from services.email_service.config import Settings
from services.email_service.implementations.provider_smtp_impl import SMTPEmailProvider
from services.email_service.protocols import EmailSendResult


class TestSMTPEdgeCases:
    """Comprehensive edge case testing for SMTP provider."""

    @pytest.fixture
    def smtp_settings(self) -> Settings:
        """Create SMTP settings for edge case testing."""
        settings = Settings()
        settings.EMAIL_PROVIDER = "smtp"
        settings.SMTP_HOST = "mail.privateemail.com"
        settings.SMTP_PORT = 587
        settings.SMTP_USERNAME = "noreply@hule.education"
        settings.SMTP_PASSWORD = "test_password"
        settings.SMTP_USE_TLS = True
        settings.SMTP_TIMEOUT = 30
        settings.DEFAULT_FROM_EMAIL = "noreply@hule.education"
        settings.DEFAULT_FROM_NAME = "HuleEdu"
        return settings

    @pytest.mark.parametrize(
        "exception_type,expected_error_contains",
        [
            (
                aiosmtplib.SMTPAuthenticationError(535, "Authentication failed"),
                "SMTP authentication failed",
            ),
            (
                aiosmtplib.SMTPConnectError("Connection refused"),
                "SMTP connection failed",
            ),
            (
                aiosmtplib.SMTPException("General SMTP error"),
                "SMTP error",
            ),
            (
                ConnectionError("Network unreachable"),
                "Unexpected error sending email",
            ),
            (
                TimeoutError("Connection timeout"),
                "Unexpected error sending email",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_smtp_error_handling(
        self,
        exception_type: Exception,
        expected_error_contains: str,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test comprehensive SMTP error scenarios with proper EmailSendResult handling."""

        # Configure mock based on exception type for proper error simulation
        if isinstance(exception_type, (aiosmtplib.SMTPConnectError, ConnectionError, TimeoutError)):
            # Connection errors should be raised when context manager is entered
            mock_smtp = AsyncMock()
            mock_smtp.__aenter__.side_effect = exception_type
            mock_smtp.__aexit__.return_value = None
        elif isinstance(exception_type, aiosmtplib.SMTPAuthenticationError):
            # Auth errors should be raised during login
            mock_smtp = AsyncMock()
            mock_smtp.__aenter__.return_value = mock_smtp
            mock_smtp.__aexit__.return_value = None
            mock_smtp.login.side_effect = exception_type
        else:
            # General SMTP errors during send
            mock_smtp = AsyncMock()
            mock_smtp.__aenter__.return_value = mock_smtp
            mock_smtp.__aexit__.return_value = None
            mock_smtp.login.return_value = None
            mock_smtp.send_message.side_effect = exception_type

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        result = await provider.send_email(
            to="test@example.com",
            subject="Test Error Handling",
            html_content="<p>Test content</p>",
        )

        # Verify proper error handling behavior
        assert isinstance(result, EmailSendResult)
        assert result.success is False
        assert result.provider_message_id is None
        assert result.error_message and expected_error_contains in result.error_message

    @pytest.mark.asyncio
    async def test_smtp_partial_send_failures(
        self,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test SMTP partial send failures with proper error reporting."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        # Simulate partial send failure
        mock_smtp.send_message.return_value = {"test@example.com": (550, "Mailbox not found")}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        result = await provider.send_email(
            to="test@example.com",
            subject="Test Partial Failure",
            html_content="<p>Test content</p>",
        )

        assert result.success is False
        assert result.error_message and "Partial send failure" in result.error_message
        assert (
            result.error_message
            and "test@example.com: (550, 'Mailbox not found')" in result.error_message
        )

    @pytest.mark.parametrize(
        "invalid_config,expected_validation",
        [
            ({"SMTP_USERNAME": None}, "EMAIL_SMTP_USERNAME"),
            ({"SMTP_PASSWORD": None}, "EMAIL_SMTP_PASSWORD"),
            ({"SMTP_USERNAME": "", "SMTP_PASSWORD": ""}, "EMAIL_SMTP_USERNAME"),
        ],
    )
    @pytest.mark.asyncio
    async def test_configuration_validation(
        self,
        invalid_config: dict[str, Any],
        expected_validation: str,
        smtp_settings: Settings,
    ) -> None:
        """Test SMTP configuration validation with missing credentials."""

        # Apply invalid configuration
        for key, value in invalid_config.items():
            setattr(smtp_settings, key, value)

        # Test that DI provider creation validates configuration
        from services.email_service.di import ImplementationProvider

        provider_class = ImplementationProvider()

        with pytest.raises(ValueError) as exc_info:
            provider_class.provide_email_provider(smtp_settings)

        assert expected_validation in str(exc_info.value)

    @pytest.mark.parametrize(
        "swedish_subject,expected_encoding",
        [
            ("Välkommen till HuleEdu - Åsa Ödén", "utf-8"),
            ("Återställ lösenord för ÅÄÖ användare", "utf-8"),
            ("Viktig information från läraren - öppna meddelandet", "utf-8"),
            # Very long Swedish subject exceeding RFC 2822 limits
            ("Välkommen till HuleEdu " * 10 + " - Åsa Öberg", "utf-8"),
        ],
    )
    @pytest.mark.asyncio
    async def test_swedish_character_edge_cases(
        self,
        swedish_subject: str,
        expected_encoding: str,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test comprehensive Swedish character handling in edge cases."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        # Test with comprehensive Swedish content
        result = await provider.send_email(
            to="åsa.öberg@skola.se",
            subject=swedish_subject,
            html_content="<p>Hej Åsa! Välkommen till vår svenska utbildningsplattform. "
            "Vi har åäöÅÄÖ tecken i vårt innehåll.</p>",
            text_content="Hej Åsa! Välkommen till vår svenska utbildningsplattform. "
            "Vi har åäöÅÄÖ tecken i vårt innehåll.",
            from_name="Läraren Öberg",
        )

        assert result.success is True

        # Verify message was created with proper encoding
        send_message_call = mock_smtp.send_message.call_args[0][0]
        assert send_message_call.get_charset() == expected_encoding

        # Verify Swedish characters preserved in headers
        assert swedish_subject == send_message_call["Subject"]
        assert "Läraren Öberg" in send_message_call["From"]

        # Verify multipart structure with Swedish content - check decoded payloads
        assert send_message_call.is_multipart()
        parts = list(send_message_call.walk())

        # Find text and HTML parts and check decoded content
        for part in parts:
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                assert "Åsa" in payload
                assert "åäö" in payload or "ÅÄÖ" in payload

    @pytest.mark.parametrize(
        "content_length,expected_success",
        [
            (100, True),  # Normal content
            (10000, True),  # Large content
            (100000, True),  # Very large content
            (1000000, True),  # 1MB content
        ],
    )
    @pytest.mark.asyncio
    async def test_large_content_handling(
        self,
        content_length: int,
        expected_success: bool,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test SMTP handling of various content sizes."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        # Create content with Swedish characters
        swedish_content = "Detta är svenskt innehåll med åäöÅÄÖ tecken. " * (content_length // 50)

        result = await provider.send_email(
            to="test@example.com",
            subject="Test Large Content",
            html_content=f"<p>{swedish_content}</p>",
            text_content=swedish_content,
        )

        assert result.success is expected_success
        if expected_success:
            # Verify message was sent
            mock_smtp.send_message.assert_called_once()

            # Verify content integrity with proper decoding
            send_message_call = mock_smtp.send_message.call_args[0][0]
            parts = list(send_message_call.walk())
            found_swedish_chars = False
            for part in parts:
                if part.get_content_type() in ("text/plain", "text/html"):
                    payload = part.get_payload(decode=True)
                    if isinstance(payload, bytes):
                        payload = payload.decode("utf-8")
                    if "åäöÅÄÖ" in payload:
                        found_swedish_chars = True
                        break
            assert found_swedish_chars

    @pytest.mark.asyncio
    async def test_connection_timeout_handling(
        self,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test SMTP connection timeout scenarios."""

        async def slow_connect(*args: Any, **kwargs: Any) -> None:
            """Simulate slow connection that times out."""
            await asyncio.sleep(0.1)  # Longer than test timeout
            raise asyncio.TimeoutError("Connection timeout")

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.side_effect = slow_connect  # Raise timeout on context entry
        mock_smtp.__aexit__.return_value = None

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        # Set very short timeout for testing
        smtp_settings.SMTP_TIMEOUT = 1
        provider = SMTPEmailProvider(smtp_settings)

        result = await provider.send_email(
            to="test@example.com",
            subject="Test Timeout",
            html_content="<p>Test content</p>",
        )

        assert result.success is False
        assert result.error_message and "Unexpected error sending email" in result.error_message

    # NOTE: Email validation is handled at Pydantic model level (NotificationEmailRequestedV1)
    # The SMTP provider accepts any string - it doesn't validate email addresses
    # So invalid email validation tests are not appropriate at the provider level

    @pytest.mark.asyncio
    async def test_html_to_text_conversion_edge_cases(
        self,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test HTML to text conversion with Swedish content edge cases."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        # Complex HTML with Swedish characters and entities
        complex_html = """
        <html>
        <head><title>Svenska tecken</title></head>
        <body>
            <h1>Välkommen till HuleEdu!</h1>
            <p>Detta är en <strong>viktig</strong> meddelande.</p>
            <p>Specialtecken: &aring;&auml;&ouml; och &Aring;&Auml;&Ouml;</p>
            <ul>
                <li>Första punkten med åäö</li>
                <li>Andra punkten med ÅÄÖ</li>
            </ul>
            <p>Länk: <a href="https://hule.education">Hule Education</a></p>
        </body>
        </html>
        """

        result = await provider.send_email(
            to="test@example.com",
            subject="Test HTML Conversion",
            html_content=complex_html,
            # No text_content provided - should auto-convert
        )

        assert result.success is True

        # Verify multipart message created
        send_message_call = mock_smtp.send_message.call_args[0][0]
        assert send_message_call.is_multipart()

        # Verify both HTML and text parts exist with Swedish characters - check decoded content
        parts = list(send_message_call.walk())
        html_found = text_found = False

        for part in parts:
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                if "Välkommen till HuleEdu" in payload and "åäö" in payload and "ÅÄÖ" in payload:
                    html_found = True
            elif part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")
                if "Välkommen till HuleEdu" in payload and "åäö" in payload and "ÅÄÖ" in payload:
                    text_found = True

        assert html_found and text_found

    @pytest.mark.asyncio
    async def test_mixed_language_content(
        self,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test mixed Swedish/English content handling."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        mixed_content = """
        <h1>Welcome to HuleEdu / Välkommen till HuleEdu</h1>
        <p>Dear Åsa Öberg,</p>
        <p>Your account has been created successfully. / Ditt konto har skapats framgångsrikt.</p>
        <p>Please verify your email address. / Vänligen verifiera din e-postadress.</p>
        <p>Best regards, / Med vänliga hälsningar,</p>
        <p>The HuleEdu Team / HuleEdu Teamet</p>
        """

        result = await provider.send_email(
            to="åsa.öberg@international-school.se",
            subject="Welcome / Välkommen - Account Created / Konto Skapat",
            html_content=mixed_content,
            from_name="HuleEdu International / HuleEdu Internationell",
        )

        assert result.success is True

        # Verify mixed language content preserved - check decoded content
        send_message_call = mock_smtp.send_message.call_args[0][0]
        parts = list(send_message_call.walk())

        # Check content in decoded payloads
        english_found = swedish_found = False
        for part in parts:
            if part.get_content_type() in ("text/plain", "text/html"):
                payload = part.get_payload(decode=True)
                if isinstance(payload, bytes):
                    payload = payload.decode("utf-8")

                # Check English content
                if "Welcome to HuleEdu" in payload and "Best regards" in payload:
                    english_found = True

                # Check Swedish content with special characters
                if (
                    "Välkommen till HuleEdu" in payload
                    and "Med vänliga hälsningar" in payload
                    and "Åsa Öberg" in payload
                ):
                    swedish_found = True

        assert english_found and swedish_found

        # Check mixed subject line
        assert "Welcome / Välkommen" in send_message_call["Subject"]

        # Check mixed sender name
        assert "HuleEdu International / HuleEdu Internationell" in send_message_call["From"]

    @pytest.mark.asyncio
    async def test_empty_content_edge_cases(
        self,
        smtp_settings: Settings,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Test handling of empty or minimal content."""

        mock_smtp = AsyncMock()
        mock_smtp.__aenter__.return_value = mock_smtp
        mock_smtp.__aexit__.return_value = None
        mock_smtp.connect.return_value = None
        mock_smtp.starttls.return_value = None
        mock_smtp.login.return_value = None
        mock_smtp.send_message.return_value = {}

        monkeypatch.setattr("aiosmtplib.SMTP", lambda *args, **kwargs: mock_smtp)

        provider = SMTPEmailProvider(smtp_settings)

        # Test with minimal content
        result = await provider.send_email(
            to="test@example.com",
            subject="",  # Empty subject
            html_content="<p></p>",  # Minimal HTML
        )

        assert result.success is True

        # Verify message was created despite minimal content
        send_message_call = mock_smtp.send_message.call_args[0][0]
        assert send_message_call["Subject"] == ""
        assert send_message_call.is_multipart()

        # Verify UTF-8 encoding still applied
        assert send_message_call.get_charset() == "utf-8"

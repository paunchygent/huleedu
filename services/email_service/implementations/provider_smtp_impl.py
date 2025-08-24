"""SMTP email provider for production email delivery.

This implementation uses aiosmtplib to send emails through SMTP servers,
specifically configured for Namecheap Private Email service with proper
Swedish character support and multipart message handling.
"""

from __future__ import annotations

import re
from email.message import EmailMessage

import aiosmtplib  # type: ignore[import-not-found]
from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.protocols import EmailProvider, EmailSendResult

logger = create_service_logger("email_service.provider_smtp")


class SMTPEmailProvider(EmailProvider):
    """SMTP email provider for production email delivery.

    This implementation sends real emails through SMTP servers using aiosmtplib
    with proper error handling, Swedish character support, and multipart messages.
    """

    def __init__(self, settings: Settings):
        self.settings = settings

    async def send_email(
        self,
        to: EmailStr,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_email: EmailStr | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult:
        """Send email via SMTP with proper multipart support."""

        # Use default sender if not provided
        from_email = from_email or self.settings.DEFAULT_FROM_EMAIL
        from_name = from_name or self.settings.DEFAULT_FROM_NAME

        # Create multipart message
        msg = EmailMessage()

        # Set headers with proper UTF-8 encoding
        msg["From"] = f"{from_name} <{from_email}>"
        msg["To"] = str(to)
        msg["Subject"] = subject

        # Set charset to UTF-8 for Swedish character support
        msg.set_charset("utf-8")

        # Generate plain text from HTML if not provided
        if text_content is None:
            text_content = self._html_to_text(html_content)

        # Set plain text content as primary
        msg.set_content(text_content, charset="utf-8")

        # Add HTML alternative
        msg.add_alternative(html_content, subtype="html", charset="utf-8")

        try:
            # Connect to SMTP server
            async with aiosmtplib.SMTP(
                hostname=self.settings.SMTP_HOST,
                port=self.settings.SMTP_PORT,
                start_tls=self.settings.SMTP_USE_TLS,
                timeout=self.settings.SMTP_TIMEOUT,
            ) as smtp:
                # Authenticate with SMTP server
                if self.settings.SMTP_USERNAME is None or self.settings.SMTP_PASSWORD is None:
                    raise ValueError("SMTP username and password are required for authentication")

                await smtp.login(
                    self.settings.SMTP_USERNAME,
                    self.settings.SMTP_PASSWORD,
                )

                # Send the message
                send_errors = await smtp.send_message(msg)

                if send_errors:
                    # aiosmtplib returns both errors AND success info in send_errors
                    # Check if it's actually an error (non-empty dict) or success info (empty dict + success message)
                    if isinstance(send_errors, tuple) and len(send_errors) == 2:
                        error_dict, message = send_errors
                        if error_dict:  # Non-empty dict means actual errors
                            error_details = "; ".join(
                                f"{addr}: {error}" for addr, error in error_dict.items()
                            )
                            logger.error(f"SMTP partial send failure to {to}: {error_details}")
                            return EmailSendResult(
                                success=False,
                                provider_message_id=None,
                                error_message=f"Partial send failure: {error_details}",
                            )
                        else:
                            # Empty dict + message means success - this is normal SMTP server response
                            logger.info(f"SMTP server response: {message}")
                    else:
                        # Handle other send_errors formats
                        if isinstance(send_errors, dict) and send_errors:
                            error_details = "; ".join(
                                f"{addr}: {error}" for addr, error in send_errors.items()
                            )
                            logger.error(f"SMTP partial send failure to {to}: {error_details}")
                            return EmailSendResult(
                                success=False,
                                provider_message_id=None,
                                error_message=f"Partial send failure: {error_details}",
                            )
                        else:
                            # Unexpected format but non-empty, treat as error
                            logger.error(f"SMTP unexpected send errors to {to}: {send_errors}")
                            return EmailSendResult(
                                success=False,
                                provider_message_id=None,
                                error_message=f"Unexpected send errors: {send_errors}",
                            )

                # Generate provider message ID for tracking
                provider_message_id = f"smtp_{hash(f'{to}_{subject}_{from_email}')}"

                logger.info(
                    "Email sent successfully via SMTP",
                    extra={
                        "to": str(to),
                        "from_email": str(from_email),
                        "subject": subject,
                        "provider_message_id": provider_message_id,
                        "smtp_host": self.settings.SMTP_HOST,
                    },
                )

                return EmailSendResult(
                    success=True,
                    provider_message_id=provider_message_id,
                    error_message=None,
                )

        except aiosmtplib.SMTPAuthenticationError as e:
            error_msg = f"SMTP authentication failed: {e}"
            logger.error(error_msg, exc_info=True)
            return EmailSendResult(
                success=False,
                provider_message_id=None,
                error_message=error_msg,
            )

        except aiosmtplib.SMTPConnectError as e:
            error_msg = f"SMTP connection failed: {e}"
            logger.error(error_msg, exc_info=True)
            return EmailSendResult(
                success=False,
                provider_message_id=None,
                error_message=error_msg,
            )

        except aiosmtplib.SMTPException as e:
            error_msg = f"SMTP error: {e}"
            logger.error(f"SMTP send failed to {to}: {error_msg}", exc_info=True)
            return EmailSendResult(
                success=False,
                provider_message_id=None,
                error_message=error_msg,
            )

        except Exception as e:
            error_msg = f"Unexpected error sending email: {e}"
            logger.error(f"Unexpected SMTP error to {to}: {error_msg}", exc_info=True)
            return EmailSendResult(
                success=False,
                provider_message_id=None,
                error_message=error_msg,
            )

    def get_provider_name(self) -> str:
        """Return the provider name for tracking purposes."""
        return "smtp"

    def _html_to_text(self, html: str) -> str:
        """Convert HTML to plain text for email fallback.

        This is a simple implementation that strips HTML tags and handles
        basic formatting for plain text email clients.
        """
        # Remove HTML tags
        clean_text = re.sub(r"<[^>]+>", "", html)

        # Replace common HTML entities
        clean_text = clean_text.replace("&nbsp;", " ")
        clean_text = clean_text.replace("&lt;", "<")
        clean_text = clean_text.replace("&gt;", ">")
        clean_text = clean_text.replace("&amp;", "&")
        clean_text = clean_text.replace("&quot;", '"')
        clean_text = clean_text.replace("&#39;", "'")

        # Clean up whitespace
        clean_text = re.sub(r"\s+", " ", clean_text.strip())

        return clean_text

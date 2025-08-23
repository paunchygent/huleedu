"""Mock email provider for development and testing.

This implementation simulates email sending without actually sending emails.
Useful for development and testing environments.
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any

from huleedu_service_libs.logging_utils import create_service_logger
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.protocols import EmailProvider, EmailSendResult

logger = create_service_logger("email_service.provider_mock")


class MockEmailProvider(EmailProvider):
    """Mock email provider that simulates sending emails.

    This implementation logs email details and simulates success/failure
    scenarios for testing and development purposes.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self._sent_emails: list[dict[str, Any]] = []  # Store sent emails for inspection

    async def send_email(
        self,
        to: EmailStr,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_email: EmailStr | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult:
        """Simulate sending an email with configurable success/failure."""

        # Use default sender if not provided
        from_email = from_email or self.settings.DEFAULT_FROM_EMAIL
        from_name = from_name or self.settings.DEFAULT_FROM_NAME

        # Simulate network delay
        await asyncio.sleep(random.uniform(0.1, 0.5))

        # Generate a mock provider message ID
        mock_message_id = (
            f"mock_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{random.randint(1000, 9999)}"
        )

        # Store email details for inspection
        email_details = {
            "to": str(to),
            "from_email": str(from_email),
            "from_name": from_name,
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
            "sent_at": datetime.utcnow(),
            "provider_message_id": mock_message_id,
        }
        self._sent_emails.append(email_details)

        # Simulate failures based on configured rate (default 0% for deterministic tests)
        if random.random() < self.settings.MOCK_PROVIDER_FAILURE_RATE:
            error_message = "Mock provider: Simulated delivery failure"
            logger.warning(f"Mock email send failed: {error_message}")
            return EmailSendResult(
                success=False,
                provider_message_id=None,
                error_message=error_message,
            )

        # Log successful send
        logger.info(
            "Mock email sent successfully",
            extra={
                "to": str(to),
                "subject": subject,
                "from_email": str(from_email),
                "provider_message_id": mock_message_id,
            },
        )

        return EmailSendResult(
            success=True,
            provider_message_id=mock_message_id,
            error_message=None,
        )

    def get_provider_name(self) -> str:
        """Return the provider name for tracking purposes."""
        return "mock"

    def get_sent_emails(self) -> list[dict]:
        """Get list of sent emails for testing/inspection."""
        return self._sent_emails.copy()

    def clear_sent_emails(self) -> None:
        """Clear the sent emails list for testing."""
        self._sent_emails.clear()

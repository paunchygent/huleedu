"""Protocol definitions for Email Service dependency injection.

This module defines behavioral contracts used by the DI container to provide
implementations following the Repository and Strategy patterns.
"""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple, Protocol

from pydantic import BaseModel, EmailStr


class EmailSendResult(NamedTuple):
    """Result of sending an email through a provider."""
    
    success: bool
    provider_message_id: str | None = None
    error_message: str | None = None


class RenderedTemplate(NamedTuple):
    """Result of rendering an email template."""
    
    subject: str
    html_content: str
    text_content: str | None = None


class EmailRecord(BaseModel):
    """Email record for database persistence."""
    
    message_id: str
    to_address: EmailStr
    from_address: EmailStr
    from_name: str
    subject: str
    template_id: str
    category: str
    variables: dict[str, str]
    correlation_id: str
    html_content: str | None = None
    text_content: str | None = None
    provider: str | None = None
    provider_message_id: str | None = None
    status: str = "pending"
    created_at: datetime | None = None
    sent_at: datetime | None = None
    failed_at: datetime | None = None
    failure_reason: str | None = None


class EmailProvider(Protocol):
    """Protocol for email service providers (SendGrid, SES, etc.)."""
    
    async def send_email(
        self,
        to: EmailStr,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_email: EmailStr | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult:
        """Send an email through the provider.
        
        Args:
            to: Recipient email address
            subject: Email subject line
            html_content: HTML email content
            text_content: Plain text email content (optional)
            from_email: Sender email address
            from_name: Sender display name
            
        Returns:
            EmailSendResult with success status and provider details
        """
        ...
    
    def get_provider_name(self) -> str:
        """Get the provider name for tracking purposes."""
        ...


class TemplateRenderer(Protocol):
    """Protocol for email template rendering engines."""
    
    async def render(
        self,
        template_id: str,
        variables: dict[str, str],
    ) -> RenderedTemplate:
        """Render an email template with variables.
        
        Args:
            template_id: Identifier for the template to render
            variables: Variables to substitute in the template
            
        Returns:
            RenderedTemplate with subject and content
            
        Raises:
            TemplateNotFoundError: If template doesn't exist
            TemplateRenderError: If template rendering fails
        """
        ...
    
    async def template_exists(self, template_id: str) -> bool:
        """Check if a template exists.
        
        Args:
            template_id: Template identifier to check
            
        Returns:
            True if template exists, False otherwise
        """
        ...


class EmailRepository(Protocol):
    """Protocol for email record persistence."""
    
    async def create_email_record(self, record: EmailRecord) -> None:
        """Create a new email record.
        
        Args:
            record: EmailRecord to persist
        """
        ...
    
    async def update_status(
        self,
        message_id: str,
        status: str,
        provider_message_id: str | None = None,
        provider_response: str | None = None,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Update email record status and metadata.
        
        Args:
            message_id: Email message ID
            status: New status (sent, failed, etc.)
            provider_message_id: Provider's message ID
            provider_response: Provider's response details
            sent_at: Timestamp when email was sent
            failed_at: Timestamp when email failed
            failure_reason: Reason for failure
        """
        ...
    
    async def get_by_message_id(self, message_id: str) -> EmailRecord | None:
        """Get email record by message ID.
        
        Args:
            message_id: Email message ID
            
        Returns:
            EmailRecord if found, None otherwise
        """
        ...
    
    async def get_by_correlation_id(self, correlation_id: str) -> list[EmailRecord]:
        """Get email records by correlation ID.
        
        Args:
            correlation_id: Correlation ID for request tracking
            
        Returns:
            List of EmailRecord objects
        """
        ...
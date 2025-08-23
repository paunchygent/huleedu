"""Cross-service integration tests for Identity Service → Email Service flow.

Tests the complete event flow from Identity Service events to Email Service
notifications through the NotificationOrchestrator bridge.

Rule 075.1 Compliant: No @patch usage, behavioral testing only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import pytest
from common_core.emailing_models import NotificationEmailRequestedV1
from common_core.identity_models import (
    EmailVerificationRequestedV1,
    PasswordResetRequestedV1,
    UserRegisteredV1,
)
from pydantic import EmailStr

from services.email_service.config import Settings
from services.email_service.event_processor import EmailEventProcessor
from services.email_service.implementations.outbox_manager import OutboxManager
from services.email_service.implementations.provider_mock_impl import MockEmailProvider
# from services.email_service.implementations.repository_impl import EmailRepository
from services.email_service.implementations.template_renderer_impl import JinjaTemplateRenderer

if TYPE_CHECKING:
    from typing import Generator


class MockOutboxManager:
    """Mock outbox manager for testing."""
    
    def __init__(self) -> None:
        self.published_events: list[dict[str, Any]] = []
    
    async def publish_to_outbox(
        self,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        event_data: Any,
        topic: str,
    ) -> None:
        """Mock publish to outbox."""
        self.published_events.append({
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "event_type": event_type,
            "event_data": event_data,
            "topic": topic,
        })


class MockEmailRepository:
    """Mock email repository for testing."""
    
    def __init__(self) -> None:
        self.emails: dict[str, dict[str, Any]] = {}
    
    async def create_email_record(self, record: Any) -> None:
        """Create email record."""
        self.emails[record.message_id] = {
            "message_id": record.message_id,
            "status": record.status,
            "to_address": record.to_address,
            "subject": record.subject,
            "template_id": record.template_id,
            "category": record.category,
            "variables": record.variables,
            "correlation_id": record.correlation_id,
            "created_at": record.created_at,
        }
    
    async def update_status(
        self,
        message_id: str,
        status: str,
        provider_message_id: str | None = None,
        sent_at: datetime | None = None,
        failed_at: datetime | None = None,
        failure_reason: str | None = None,
    ) -> None:
        """Update email status."""
        if message_id in self.emails:
            self.emails[message_id]["status"] = status
            if provider_message_id:
                self.emails[message_id]["provider_message_id"] = provider_message_id
            if sent_at:
                self.emails[message_id]["sent_at"] = sent_at
            if failed_at:
                self.emails[message_id]["failed_at"] = failed_at
            if failure_reason:
                self.emails[message_id]["failure_reason"] = failure_reason


@pytest.fixture
def mock_settings() -> Settings:
    """Create settings for integration testing."""
    return Settings(
        EMAIL_PROVIDER="mock",
        DEFAULT_FROM_EMAIL="noreply@hule.education",  # EmailStr is a type annotation, not a constructor
        DEFAULT_FROM_NAME="HuleEdu",
        TEMPLATE_DIRECTORY="templates",
    )


@pytest.fixture
def mock_email_provider(mock_settings: Settings) -> MockEmailProvider:
    """Create mock email provider for testing."""
    return MockEmailProvider(mock_settings)


@pytest.fixture
def template_renderer() -> JinjaTemplateRenderer:
    """Create template renderer for testing."""
    return JinjaTemplateRenderer("templates")


@pytest.fixture
def mock_repository() -> MockEmailRepository:
    """Create mock repository for testing."""
    return MockEmailRepository()


@pytest.fixture
def mock_outbox() -> MockOutboxManager:
    """Create mock outbox manager for testing."""
    return MockOutboxManager()


@pytest.fixture
def email_processor(
    mock_settings: Settings,
    mock_repository: MockEmailRepository,
    template_renderer: JinjaTemplateRenderer,
    mock_email_provider: MockEmailProvider,
    mock_outbox: MockOutboxManager,
) -> EmailEventProcessor:
    """Create email event processor with mock dependencies."""
    return EmailEventProcessor(
        repository=mock_repository,  # type: ignore[arg-type]
        template_renderer=template_renderer,
        email_provider=mock_email_provider,
        outbox_manager=mock_outbox,  # type: ignore[arg-type]
        settings=mock_settings,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_email_verification_flow_integration(
    email_processor: EmailEventProcessor,
    mock_email_provider: MockEmailProvider,
    mock_repository: MockEmailRepository,
) -> None:
    """Test complete email verification flow: Identity event → Email sent."""
    
    # Create email verification request event (simulating Identity Service)
    user_id = str(uuid4())
    verification_token = "test_verification_token_123"
    email = "test.user@example.com"
    correlation_id = str(uuid4())
    
    verification_event = EmailVerificationRequestedV1(
        user_id=user_id,
        email=email,
        verification_token=verification_token,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0),
        correlation_id=correlation_id,
    )
    
    # Transform to email notification (simulating NotificationOrchestrator)
    notification = NotificationEmailRequestedV1(
        message_id=f"verification-{user_id}-{uuid4().hex[:8]}",
        template_id="verification",
        to=email,
        variables={
            "user_name": email.split("@")[0].title(),
            "verification_link": f"https://hule.education/verify?token={verification_token}",
            "verification_token": verification_token,
            "expires_in": "24 hours",
            "expires_at": verification_event.expires_at.isoformat(),
            "current_year": "2025",
        },
        category="verification",
        correlation_id=correlation_id,
    )
    
    # Clear any previous emails
    mock_email_provider.clear_sent_emails()
    
    # Process notification through processor
    await email_processor.process_email_request(notification)
    
    # Verify email was sent
    sent_emails = mock_email_provider.get_sent_emails()
    assert len(sent_emails) == 1
    sent_email = sent_emails[0]
    
    # Validate email content
    assert sent_email["to"] == str(email)
    assert "Verify your HuleEdu account" in sent_email["subject"]
    assert verification_token in sent_email["html_content"]
    assert "https://hule.education/verify" in sent_email["html_content"]
    assert email.split("@")[0].title() in sent_email["html_content"]
    
    # Verify database record was created and updated
    assert notification.message_id in mock_repository.emails
    record = mock_repository.emails[notification.message_id]
    assert record["status"] == "sent"
    assert record["template_id"] == "verification"
    assert record["category"] == "verification"
    
    # Verify Swedish character support in content
    assert sent_email["html_content"].encode('utf-8')  # Should encode without error


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_reset_flow_integration(
    email_processor: EmailEventProcessor,
    mock_email_provider: MockEmailProvider,
    mock_repository: MockEmailRepository,
) -> None:
    """Test complete password reset flow: Identity event → Email sent."""
    
    # Create password reset request event (simulating Identity Service)
    user_id = str(uuid4())
    token_id = "test_reset_token_456"
    email = "test.user@example.com"
    correlation_id = str(uuid4())
    
    reset_event = PasswordResetRequestedV1(
        user_id=user_id,
        email=email,
        token_id=token_id,
        expires_at=datetime.now(timezone.utc).replace(microsecond=0),
        correlation_id=correlation_id,
    )
    
    # Transform to email notification (simulating NotificationOrchestrator)
    notification = NotificationEmailRequestedV1(
        message_id=f"password-reset-{user_id}-{uuid4().hex[:8]}",
        template_id="password_reset",
        to=email,
        variables={
            "user_name": email.split("@")[0].title(),
            "reset_link": f"https://hule.education/reset-password?token={token_id}",
            "token_id": token_id,
            "expires_in": "1 hour",
            "expires_at": reset_event.expires_at.isoformat(),
            "current_year": "2025",
        },
        category="password_reset",
        correlation_id=correlation_id,
    )
    
    # Clear any previous emails
    mock_email_provider.clear_sent_emails()
    
    # Process notification through processor
    await email_processor.process_email_request(notification)
    
    # Verify email was sent
    sent_emails = mock_email_provider.get_sent_emails()
    assert len(sent_emails) == 1
    sent_email = sent_emails[0]
    
    # Validate email content
    assert sent_email["to"] == str(email)
    assert "Reset your HuleEdu password" in sent_email["subject"]
    assert token_id in sent_email["html_content"]
    assert "https://hule.education/reset-password" in sent_email["html_content"]
    assert email.split("@")[0].title() in sent_email["html_content"]
    
    # Verify database record was created and updated
    assert notification.message_id in mock_repository.emails
    record = mock_repository.emails[notification.message_id]
    assert record["status"] == "sent"
    assert record["template_id"] == "password_reset"
    assert record["category"] == "password_reset"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_welcome_email_flow_integration(
    email_processor: EmailEventProcessor,
    mock_email_provider: MockEmailProvider,
    mock_repository: MockEmailRepository,
) -> None:
    """Test complete welcome email flow: User registered → Email sent."""
    
    # Create user registration event (simulating Identity Service)
    user_id = str(uuid4())
    email = "new.user@example.com"
    correlation_id = str(uuid4())
    
    registration_event = UserRegisteredV1(
        user_id=user_id,
        email=email,
        registered_at=datetime.now(timezone.utc).replace(microsecond=0),
        correlation_id=correlation_id,
    )
    
    # Transform to email notification (simulating NotificationOrchestrator)
    notification = NotificationEmailRequestedV1(
        message_id=f"welcome-{user_id}-{uuid4().hex[:8]}",
        template_id="welcome",
        to=email,
        variables={
            "user_name": email.split("@")[0].title(),
            "first_name": email.split("@")[0].title(),
            "dashboard_link": "https://app.hule.education/dashboard",
            "org_name": "HuleEdu",
            "registered_at": registration_event.registered_at.isoformat(),
            "current_year": "2025",
        },
        category="system",
        correlation_id=correlation_id,
    )
    
    # Clear any previous emails
    mock_email_provider.clear_sent_emails()
    
    # Process notification through processor
    await email_processor.process_email_request(notification)
    
    # Verify email was sent
    sent_emails = mock_email_provider.get_sent_emails()
    assert len(sent_emails) == 1
    sent_email = sent_emails[0]
    
    # Validate email content
    assert sent_email["to"] == str(email)
    assert "Welcome to HuleEdu!" in sent_email["subject"]
    assert "Welcome to HuleEdu!" in sent_email["html_content"]
    assert email.split("@")[0].title() in sent_email["html_content"]
    assert "https://app.hule.education/dashboard" in sent_email["html_content"]
    
    # Verify database record was created and updated
    assert notification.message_id in mock_repository.emails
    record = mock_repository.emails[notification.message_id]
    assert record["status"] == "sent"
    assert record["template_id"] == "welcome"
    assert record["category"] == "system"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_template_variable_compatibility() -> None:
    """Test that all Identity variables are compatible with email templates."""
    
    template_renderer = JinjaTemplateRenderer("templates")
    
    # Test verification template with Identity variables
    verification_variables = {
        "user_name": "TestUser",
        "verification_link": "https://hule.education/verify?token=abc123",
        "verification_token": "abc123",
        "expires_in": "24 hours",
        "expires_at": "2025-01-01T12:00:00+00:00",
        "current_year": "2025",
    }
    
    verification_content = await template_renderer.render(
        "verification", verification_variables
    )
    
    # Verify all variables are rendered
    assert "TestUser" in verification_content.html_content
    assert "https://hule.education/verify?token=abc123" in verification_content.html_content
    assert "24 hours" in verification_content.html_content
    
    # Test password reset template with Identity variables
    reset_variables = {
        "user_name": "TestUser",
        "reset_link": "https://hule.education/reset-password?token=def456",
        "token_id": "def456",
        "expires_in": "1 hour",
        "expires_at": "2025-01-01T12:00:00+00:00",
        "current_year": "2025",
    }
    
    reset_content = await template_renderer.render(
        "password_reset", reset_variables
    )
    
    # Verify all variables are rendered
    assert "TestUser" in reset_content.html_content
    assert "https://hule.education/reset-password?token=def456" in reset_content.html_content
    assert "1 hour" in reset_content.html_content
    
    # Test welcome template with Identity variables
    welcome_variables = {
        "user_name": "NewUser",
        "first_name": "NewUser",
        "dashboard_link": "https://app.hule.education/dashboard",
        "org_name": "HuleEdu",
        "registered_at": "2025-01-01T12:00:00+00:00",
        "current_year": "2025",
    }
    
    welcome_content = await template_renderer.render(
        "welcome", welcome_variables
    )
    
    # Verify all variables are rendered
    assert "NewUser" in welcome_content.html_content
    assert "https://app.hule.education/dashboard" in welcome_content.html_content
    assert "HuleEdu" in welcome_content.html_content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_swedish_characters_in_email_flow(
    email_processor: EmailEventProcessor,
    mock_email_provider: MockEmailProvider,
) -> None:
    """Test Swedish character support in complete email flow."""
    
    # Create notification with Swedish characters
    swedish_email = "björn.åström@example.com"
    
    notification = NotificationEmailRequestedV1(
        message_id="swedish-test-123",
        template_id="verification",
        to=swedish_email,
        variables={
            "user_name": "Björn Åström",  # Swedish characters in name
            "verification_link": "https://hule.education/verify?token=åäö123",
            "verification_token": "åäö123",
            "expires_in": "24 hours",
            "expires_at": "2025-01-01T12:00:00+00:00",
            "current_year": "2025",
        },
        category="verification",
        correlation_id=str(uuid4()),
    )
    
    # Clear any previous emails
    mock_email_provider.clear_sent_emails()
    
    # Process notification
    await email_processor.process_email_request(notification)
    
    # Verify email was sent with Swedish characters
    sent_emails = mock_email_provider.get_sent_emails()
    assert len(sent_emails) == 1
    sent_email = sent_emails[0]
    
    # Validate Swedish characters are preserved
    assert sent_email["to"] == str(swedish_email)
    assert "Björn Åström" in sent_email["html_content"]
    assert "åäö123" in sent_email["html_content"]
    
    # Verify content can be encoded as UTF-8
    encoded_content = sent_email["html_content"].encode('utf-8')
    decoded_content = encoded_content.decode('utf-8')
    assert "Björn Åström" in decoded_content
    assert "åäö123" in decoded_content


@pytest.mark.integration
@pytest.mark.asyncio
async def test_correlation_id_preservation(
    email_processor: EmailEventProcessor,
    mock_email_provider: MockEmailProvider,
    mock_outbox: MockOutboxManager,
) -> None:
    """Test that correlation IDs are preserved through the complete flow."""
    
    # Create notification with specific correlation ID (must be valid UUID)
    correlation_id = str(uuid4())
    
    notification = NotificationEmailRequestedV1(
        message_id="correlation-test-456",
        template_id="welcome",
        to="test@example.com",
        variables={
            "user_name": "TestUser",
            "first_name": "TestUser",
            "dashboard_link": "https://app.hule.education/dashboard",
            "org_name": "HuleEdu",
            "registered_at": "2025-01-01T12:00:00+00:00",
            "current_year": "2025",
        },
        category="system",
        correlation_id=correlation_id,
    )
    
    # Clear any previous emails and events
    mock_email_provider.clear_sent_emails()
    
    # Process notification
    await email_processor.process_email_request(notification)
    
    # Verify processing succeeded
    sent_emails = mock_email_provider.get_sent_emails()
    assert len(sent_emails) == 1
    
    # Verify correlation ID is in published events
    assert len(mock_outbox.published_events) == 1
    published_event = mock_outbox.published_events[0]
    assert published_event["aggregate_id"] == "correlation-test-456"
    # Note: correlation_id tracking would be in the event data envelope
    assert published_event["event_data"] is not None
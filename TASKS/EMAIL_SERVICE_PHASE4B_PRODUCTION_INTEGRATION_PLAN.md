# Email Service Phase 4B: Production Integration & Service Boundary Alignment

**Status**: Active Implementation  
**Phase**: 4B - Production Email Provider & Identity Service Integration  
**Priority**: Critical - Email Service Integration Dependency  

## ULTRATHINK: Service Integration Context

The Email Service has achieved complete test coverage (296/296 tests passing) but has a critical service boundary misalignment preventing actual email delivery. The Identity Service publishes events that the Email Service cannot consume, creating a complete disconnect in the user communication flow.

**Critical Gap Discovered**: Identity Service events never reach Email Service due to topic mismatch.

## Current Service Status (Post Phase 4A)

✅ **Phase 4A Complete**: Comprehensive test coverage implemented
- Unit Tests: 142/142 passing ✅
- Contract Tests: 118/118 passing ✅  
- Integration Tests: 36/36 passing ✅
- Total: 296/296 tests passing (100%) ✅

❌ **Missing**: Service boundary alignment and production email provider

## Phase 4B Implementation Plan

### Part 1: Service Boundary Alignment (CRITICAL PRIORITY)

**Problem**: Complete event flow disconnect
- Identity Service publishes: `huleedu.identity.email.verification.requested.v1` (EmailVerificationRequestedV1)
- Identity Service publishes: `huleedu.identity.password.reset.requested.v1` (PasswordResetRequestedV1)
- Email Service consumes: `huleedu.email.notification.requested.v1` (NotificationEmailRequestedV1)

**Solution**: Event Transformer in Identity Service

#### 1.1 Create Notification Orchestrator

**File**: `services/identity_service/notification_orchestrator.py`

```python
"""Event transformer for Identity Service to Email Service communication.

Transforms identity-specific events into generic email notification requests
that the Email Service can consume.
"""

class NotificationOrchestrator:
    """Transforms Identity events to Email notification events."""
    
    async def handle_email_verification_requested(self, event: EmailVerificationRequestedV1) -> None:
        """Transform email verification to notification request."""
        notification = NotificationEmailRequestedV1(
            message_id=f"verification-{event.user_id}-{uuid4().hex[:8]}",
            template_id="verification",
            to=event.email,
            variables={
                "user_id": event.user_id,
                "verification_token": event.verification_token,
                "verification_link": f"https://hule.education/verify?token={event.verification_token}",
                "expires_at": event.expires_at.isoformat(),
            },
            category="verification",
            correlation_id=event.correlation_id,
        )
        # Publish to EMAIL_NOTIFICATION_REQUESTED topic
        
    async def handle_password_reset_requested(self, event: PasswordResetRequestedV1) -> None:
        """Transform password reset to notification request."""
        notification = NotificationEmailRequestedV1(
            message_id=f"password-reset-{event.user_id}-{uuid4().hex[:8]}",
            template_id="password_reset",
            to=event.email,
            variables={
                "user_id": event.user_id,
                "token_id": event.token_id,
                "reset_link": f"https://hule.education/reset-password?token={event.token_id}",
                "expires_at": event.expires_at.isoformat(),
            },
            category="password_reset",
            correlation_id=event.correlation_id,
        )
        # Publish to EMAIL_NOTIFICATION_REQUESTED topic
        
    async def handle_user_registered(self, event: UserRegisteredV1) -> None:
        """Transform user registration to welcome notification."""
        notification = NotificationEmailRequestedV1(
            message_id=f"welcome-{event.user_id}-{uuid4().hex[:8]}",
            template_id="welcome",
            to=event.email,
            variables={
                "user_id": event.user_id,
                "user_name": event.email.split("@")[0].title(),  # Extract name from email
                "org_name": "HuleEdu",
                "registered_at": event.registered_at.isoformat(),
            },
            category="system",
            correlation_id=event.correlation_id,
        )
        # Publish to EMAIL_NOTIFICATION_REQUESTED topic
```

#### 1.2 Integrate into Identity Service

**Files to Modify**:
1. `services/identity_service/di.py` - Add NotificationOrchestrator to DI container
2. `services/identity_service/kafka_consumer.py` - Add consumer for own events
3. Create internal event routing for published events

### Part 2: Production SMTP Email Provider

**Namecheap Private Email Integration**

#### 2.1 SMTP Provider Implementation

**File**: `services/email_service/implementations/provider_smtp_impl.py`

```python
"""SMTP email provider implementation for Namecheap Private Email.

Uses aiosmtplib for async SMTP communication with proper error handling,
Swedish character support, and STARTTLS security.
"""

import logging
from email.message import EmailMessage
from typing import Optional
from aiosmtplib import SMTP
from pydantic import EmailStr

from services.email_service.protocols import EmailProvider, EmailSendResult

logger = logging.getLogger(__name__)

class SMTPEmailProvider(EmailProvider):
    """SMTP email provider for Namecheap Private Email service."""
    
    def __init__(self, settings: Settings) -> None:
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
        """Send email via SMTP with Namecheap Private Email settings."""
        
        msg = EmailMessage()
        # Use authenticated sender (info@hule.education)
        sender_email = from_email or self.settings.DEFAULT_FROM_EMAIL
        sender_name = from_name or self.settings.DEFAULT_FROM_NAME
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = to
        msg["Subject"] = subject
        
        # Multi-part message for HTML + text
        if text_content:
            msg.set_content(text_content)
        else:
            # Generate plain text from HTML
            msg.set_content(self._strip_html_tags(html_content))
            
        msg.add_alternative(html_content, subtype='html')
        
        try:
            async with SMTP(
                hostname=self.settings.SMTP_HOST,      # mail.privateemail.com
                port=self.settings.SMTP_PORT,          # 587
                start_tls=True,                         # STARTTLS enabled
                timeout=self.settings.SMTP_TIMEOUT     # 30 seconds
            ) as smtp:
                await smtp.connect()
                await smtp.starttls()
                await smtp.login(
                    self.settings.SMTP_USERNAME,        # info@hule.education
                    self.settings.SMTP_PASSWORD
                )
                await smtp.send_message(msg)
                
            logger.info(f"Email sent successfully via SMTP to {to}")
            return EmailSendResult(
                success=True,
                provider_message_id=f"smtp-{hash(f'{to}-{subject}')}"  # Generate ID
            )
            
        except Exception as e:
            logger.error(f"SMTP email failed to {to}: {e}")
            return EmailSendResult(
                success=False,
                error_message=str(e)
            )
    
    def get_provider_name(self) -> str:
        return "smtp"
        
    def _strip_html_tags(self, html: str) -> str:
        """Convert HTML to plain text for fallback."""
        import re
        clean = re.compile('<.*?>')
        return re.sub(clean, '', html)
```

#### 2.2 Configuration Updates

**File**: `services/email_service/config.py`

Add SMTP configuration fields:

```python
# SMTP Configuration (Namecheap Private Email)
SMTP_HOST: str = "mail.privateemail.com"
SMTP_PORT: int = 587
SMTP_USERNAME: str | None = None        # info@hule.education
SMTP_PASSWORD: str | None = None        # Mailbox password
SMTP_USE_TLS: bool = True
SMTP_TIMEOUT: int = 30

# Default sender settings (must be authenticated email or alias)
DEFAULT_FROM_EMAIL: str = "info@hule.education"
DEFAULT_FROM_NAME: str = "HuleEdu"
```

### Part 3: Provider Selection Logic

#### 3.1 Update DI Container

**File**: `services/email_service/di.py`

```python
@provide(scope=Scope.APP)
async def provide_email_provider(settings: Settings) -> EmailProvider:
    """Provide email provider based on configuration."""
    
    if settings.EMAIL_PROVIDER == "smtp":
        # Validate SMTP configuration
        if not settings.SMTP_USERNAME or not settings.SMTP_PASSWORD:
            raise ValueError(
                "SMTP provider requires EMAIL_SMTP_USERNAME and EMAIL_SMTP_PASSWORD"
            )
        
        logger.info(f"Using SMTP email provider: {settings.SMTP_HOST}:{settings.SMTP_PORT}")
        return SMTPEmailProvider(settings)
        
    else:
        # Default to mock for development
        logger.info("Using mock email provider")
        return MockEmailProvider()
```

### Part 4: Environment Configuration

#### 4.1 Development Configuration

**.env (Development)**:
```env
# Use mock provider for development
EMAIL_PROVIDER=mock
```

#### 4.2 Production Configuration

**.env (Production)**:
```env
# SMTP Provider Configuration
EMAIL_PROVIDER=smtp
EMAIL_SMTP_HOST=mail.privateemail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=info@hule.education
EMAIL_SMTP_PASSWORD=<mailbox_password>
EMAIL_SMTP_USE_TLS=true
EMAIL_SMTP_TIMEOUT=30

# Default sender (must match SMTP username or be configured alias)
EMAIL_DEFAULT_FROM_EMAIL=info@hule.education
EMAIL_DEFAULT_FROM_NAME=HuleEdu
```

**Note**: For `noreply@hule.education` address:
1. Add as alias to `info@hule.education` mailbox in Namecheap control panel
2. Update config: `EMAIL_DEFAULT_FROM_EMAIL=noreply@hule.education`

### Part 5: Template Updates

Ensure email templates support Identity Service variables:

#### 5.1 Verification Template
**File**: `services/email_service/templates/verification.html.j2`

Required variables:
- `{{verification_link}}` - Full URL with token
- `{{user_name}}` - User identifier
- `{{expires_at}}` - Token expiration

#### 5.2 Password Reset Template  
**File**: `services/email_service/templates/password_reset.html.j2`

Required variables:
- `{{reset_link}}` - Full URL with token
- `{{user_name}}` - User identifier
- `{{expires_at}}` - Token expiration

#### 5.3 Welcome Template
**File**: `services/email_service/templates/welcome.html.j2`

Required variables:
- `{{user_name}}` - User display name
- `{{org_name}}` - Organization name
- `{{registered_at}}` - Registration timestamp

### Part 6: Integration Testing

#### 6.1 SMTP Provider Testing

**File**: `services/email_service/tests/integration/test_smtp_provider.py`

```python
"""Integration tests for SMTP email provider."""

@pytest.mark.integration
@pytest.mark.asyncio
async def test_smtp_swedish_character_support():
    """Test SMTP provider with Swedish characters (åäöÅÄÖ)."""
    provider = SMTPEmailProvider(test_settings)
    
    result = await provider.send_email(
        to="test@example.com",
        subject="Välkommen till HuleEdu - ÅÄÖ Test",
        html_content="<p>Hej! Detta meddelande innehåller åäö och ÅÄÖ tecken.</p>",
        text_content="Hej! Detta meddelande innehåller åäö och ÅÄÖ tecken."
    )
    
    assert result.success
    assert result.provider_message_id is not None
    
@pytest.mark.integration
@pytest.mark.asyncio  
async def test_smtp_html_and_text_multipart():
    """Test SMTP sends both HTML and text versions."""
    # Implementation test for multipart messages
```

#### 6.2 Identity-Email Integration Testing

**File**: `tests/cross_service/test_identity_email_integration.py`

```python
"""Cross-service integration tests for Identity → Email flow."""

@pytest.mark.integration
@pytest.mark.asyncio
async def test_user_verification_email_flow():
    """Test complete flow: EmailVerificationRequested → Email sent."""
    # Test identity event triggers email notification
    
@pytest.mark.integration  
@pytest.mark.asyncio
async def test_password_reset_email_flow():
    """Test complete flow: PasswordResetRequested → Email sent."""
    # Test password reset event triggers email notification
    
@pytest.mark.integration
@pytest.mark.asyncio
async def test_welcome_email_flow():
    """Test complete flow: UserRegistered → Welcome email sent."""
    # Test registration event triggers welcome email
```

## Implementation File Summary

### Files to Create:
1. `services/identity_service/notification_orchestrator.py` - Event transformer
2. `services/email_service/implementations/provider_smtp_impl.py` - SMTP provider
3. `services/email_service/tests/integration/test_smtp_provider.py` - SMTP tests
4. `tests/cross_service/test_identity_email_integration.py` - Cross-service tests

### Files to Modify:
1. `services/identity_service/di.py` - Add notification orchestrator to DI
2. `services/identity_service/kafka_consumer.py` - Consume own events for transformation
3. `services/email_service/config.py` - Add SMTP configuration fields
4. `services/email_service/di.py` - Provider selection logic (smtp vs mock)
5. `services/email_service/templates/verification.html.j2` - Identity variables
6. `services/email_service/templates/password_reset.html.j2` - Identity variables  
7. `services/email_service/templates/welcome.html.j2` - Identity variables

## Success Criteria

✅ **Service Boundary Alignment**: Identity events trigger email notifications  
✅ **SMTP Provider**: Functional with Namecheap Private Email  
✅ **Configuration**: Mock for dev, SMTP for production  
✅ **Swedish Character Support**: ÅÄÖ characters render correctly  
✅ **Email Authentication**: Proper SPF/DKIM/DMARC alignment  
✅ **Template Integration**: Identity variables properly rendered  
✅ **Integration Testing**: Complete flow validation  
✅ **Zero Over-Engineering**: Only mock and SMTP providers  

## Dependencies

- **aiosmtplib**: Async SMTP client library
- **Namecheap Private Email**: SMTP service at mail.privateemail.com:587
- **Identity Service**: Must publish transformed events to EMAIL_NOTIFICATION_REQUESTED topic

## Post-Implementation Notes

After Phase 4B completion:
1. **User Registration**: Users receive welcome emails automatically
2. **Email Verification**: Users receive verification links via email  
3. **Password Reset**: Users receive password reset links via email
4. **Production Ready**: Email Service fully functional in production environment
5. **Scalability**: Can add additional providers (SendGrid, etc.) later without code changes

This completes the Email Service integration making it a fully functional, production-ready microservice in the HuleEdu ecosystem.

---

**Implementation Status**: Ready to begin  
**Estimated Effort**: 4-6 hours development + testing  
**Risk Level**: Low (using established patterns and existing SMTP service)
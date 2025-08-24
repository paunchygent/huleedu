# Email Service

## Service Identity
- **Port**: 8082 (API), 9098 (metrics)
- **Purpose**: Transactional email delivery via Kafka events with provider abstraction
- **Stack**: Quart, PostgreSQL, aiosmtplib, Jinja2, Kafka
- **Pattern**: Kafka consumer + HTTP dev API

## Architecture

```
app.py                  # Quart app setup with Kafka consumer
api/
  health_routes.py      # /healthz, /metrics
  dev_routes.py         # /v1/emails/dev/send, /v1/emails/dev/templates
protocols.py            # EmailProvider, TemplateRenderer, EmailRepository protocols
di.py                   # Dishka providers
implementations/        # Concrete implementations
  provider_mock_impl.py # Mock email provider (testing)
  provider_smtp_impl.py # SMTP provider (Namecheap Private Email)
  template_renderer_impl.py # Jinja2 template renderer
  repository_impl.py    # PostgreSQL email record persistence
  outbox_manager.py     # Transactional outbox pattern
event_processor.py      # Kafka event handler
kafka_consumer.py       # aiokafka consumer lifecycle
templates/              # Jinja2 email templates
  verification.html.j2  # Email verification with token
  welcome.html.j2       # User welcome email
  password_reset.html.j2 # Password reset with token
models_db.py           # SQLAlchemy models
config.py              # Environment configuration
```

## API Endpoints

**Base**: `/v1/emails` (dev only)

- `POST /dev/send`: Send test email with template rendering (development only)
- `GET /dev/templates`: List available email templates (development only)

## Database Schema

- `EmailRecord`: Email tracking (message_id, to_address, template_id, status, provider_message_id, correlation_id, variables)
- `EventOutbox`: Transactional outbox pattern for reliable event publishing
- `EmailTemplate` (future): Template metadata storage

## Events

**Consumed**: `NotificationEmailRequestedV1` from Identity Service via NotificationOrchestrator

**Published**: `EmailSentV1`, `EmailDeliveryFailedV1` via transactional outbox pattern

**Channels**: Kafka topic `huleedu.events.email.notification.v1`

## Provider Pattern

**Runtime Provider Switching**:
```python
EMAIL_EMAIL_PROVIDER=mock|smtp

# Mock Provider (default development)
EMAIL_EMAIL_PROVIDER=mock
EMAIL_MOCK_PROVIDER_FAILURE_RATE=0.0

# SMTP Provider (Namecheap Private Email)
EMAIL_EMAIL_PROVIDER=smtp
EMAIL_SMTP_HOST=mail.privateemail.com
EMAIL_SMTP_PORT=587
EMAIL_SMTP_USERNAME=noreply@hule.education
EMAIL_SMTP_PASSWORD=<private_email_password>
```

## Template System

**Jinja2 Templates**:
```python
# Subject extraction from HTML comments
<!-- subject: Reset your HuleEdu password -->

# Variable substitution with fallbacks
{{ user_name|default('there') }}
{{ expires_in|default('1 hour') }}
{{ current_year|default('2025') }}
```

**Template Variables**:
- **verification**: `user_name`, `verification_link`, `verification_token`, `expires_in`, `expires_at`
- **welcome**: `user_name`, `first_name`, `dashboard_link`, `org_name`, `registered_at`
- **password_reset**: `user_name`, `reset_link`, `token_id`, `expires_in`, `expires_at`

## Key Patterns

**Provider Abstraction**:
```python
class EmailProvider(Protocol):
    async def send_email(
        self, to: str, subject: str, html_content: str, 
        text_content: str | None = None, 
        from_email: str | None = None, from_name: str | None = None
    ) -> EmailSendResult: ...
```

**Template Rendering**:
```python
rendered = await template_renderer.render("verification", {"user_name": "John", ...})
# Returns RenderedTemplate(subject="...", html_content="...", text_content=None)
```

**Event-Driven Processing**:
```python
# Kafka consumer processes NotificationEmailRequestedV1
async def handle_notification_email_requested(event: NotificationEmailRequestedV1):
    # 1. Render template with variables
    # 2. Send via provider
    # 3. Store EmailRecord
    # 4. Publish success/failure event via outbox
```

## Configuration

Environment prefix: `EMAIL_`
- `EMAIL_PROVIDER`: Provider type (`mock` | `smtp`)
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`: SMTP credentials
- `DEFAULT_FROM_EMAIL`, `DEFAULT_FROM_NAME`: Default sender info
- `TEMPLATE_PATH`: Template directory path
- `MAX_RETRY_ATTEMPTS`, `RETRY_DELAY_SECONDS`: Retry configuration

## Development

```bash
# Run service with mock provider
pdm run dev dev email_service

# Run with SMTP provider
EMAIL_EMAIL_PROVIDER=smtp pdm run dev dev email_service

# Test email delivery
curl -X POST localhost:8082/v1/emails/dev/send \
  -H "Content-Type: application/json" \
  -d '{"to": "test@example.com", "template_id": "verification", "variables": {"user_name": "Test", "verification_link": "https://example.com"}}'

# Monitor logs
pdm run logs email_service

# Database access
source .env && docker exec huleedu_email_db psql -U $HULEEDU_DB_USER -d huleedu_email -c "\dt"
```
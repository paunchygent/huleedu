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

## Error Handling

Uses `libs/huleedu_service_libs/error_handling` for structured error responses.

### ErrorCode Usage

- **Base ErrorCode**: Service uses base `ErrorCode` from `common_core.error_enums` for generic errors:
  - `VALIDATION_ERROR` - Invalid template variables or email address
  - `EXTERNAL_SERVICE_ERROR` - SMTP provider failures
  - `PROCESSING_ERROR` - Template rendering failures
  - `TIMEOUT` - Email delivery timeout

- No service-specific ErrorCode enum (uses base errors only)

### Error Propagation

- **Event Processing**: Kafka consumer catches exceptions, publishes `EmailDeliveryFailedV1` via outbox
- **HTTP Endpoints**: Raise `HuleEduError` with correlation_id and ErrorCode (dev routes only)
- **Provider Failures**: Captured in EmailRecord status, published as failure events
- **Transactional Outbox**: Ensures failure events published reliably

### Error Response Structure

Dev API errors follow standard structure:

```python
from huleedu_service_libs.error_handling import HuleEduError
from common_core.error_enums import ErrorCode

raise HuleEduError(
    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
    message="SMTP provider unavailable",
    correlation_id=correlation_context.uuid
)
```

Event failures published via `EmailDeliveryFailedV1`:

```python
failure_event = EmailDeliveryFailedV1(
    message_id=message_id,
    to_address=to_address,
    error_code=ErrorCode.EXTERNAL_SERVICE_ERROR,
    error_message="SMTP connection timeout",
    correlation_id=correlation_id
)
```

Reference: `libs/common_core/docs/error-patterns.md`

## Testing

### Test Structure

```
tests/
├── unit/                          # Unit tests with mocked dependencies
│   ├── test_email_provider.py
│   ├── test_template_renderer.py
│   ├── test_event_processor.py
│   ├── test_repository_basics.py
│   ├── test_outbox_manager.py
│   └── ...
├── integration/                   # Integration tests with testcontainers
│   ├── test_email_workflow.py
│   ├── test_smtp_integration.py
│   ├── test_kafka_integration.py
│   ├── test_database_operations.py
│   ├── test_outbox_publishing.py
│   └── ...
└── contract/                      # Event and model contract tests
    ├── test_notification_email_contracts.py
    ├── test_email_sent_contracts.py
    ├── test_email_delivery_failed_contracts.py
    ├── test_email_record_model_contracts.py
    └── ...
```

### Running Tests

```bash
# All tests
pdm run pytest-root services/email_service/tests/ -v

# Unit tests only
pdm run pytest-root services/email_service/tests/unit/ -v

# Integration tests (requires testcontainers)
pdm run pytest-root services/email_service/tests/integration/ -v -m integration

# Contract tests
pdm run pytest-root services/email_service/tests/contract/ -v

# Skip SMTP integration tests (requires real SMTP credentials)
pdm run pytest-root services/email_service/tests/ -v -m "not smtp"
```

### Common Test Markers

- `@pytest.mark.asyncio` - Async unit tests
- `@pytest.mark.integration` - Integration tests requiring external dependencies
- `@pytest.mark.contract` - Event and model contract validation tests
- `@pytest.mark.smtp` - SMTP provider integration tests (requires real credentials)

### Test Patterns

- **Protocol-based mocking**: Use `AsyncMock(spec=ProtocolName)` for dependencies
- **Mock provider**: Use `MockEmailProvider` for testing without SMTP
- **Testcontainers**: PostgreSQL containers for integration tests
- **Template fixtures**: Load test templates from `tests/fixtures/templates/`
- **Explicit fixtures**: Import test utilities explicitly (no conftest.py)

Reference: `.claude/rules/075-test-creation-methodology.mdc`

## Migration Workflow

### Creating Migrations

From service directory:

```bash
cd services/email_service/

# Generate migration from model changes
alembic revision --autogenerate -m "description_of_change"

# Review generated migration in alembic/versions/
# Edit if needed (constraints, indexes, data migrations)

# Apply migration
alembic upgrade head
```

### Migration Standards

- **Naming**: `YYYYMMDD_HHMM_short_description.py`
- **Outbox alignment**: Use shared `EventOutbox` model from `huleedu_service_libs.outbox.models`
- **Email tables**: EmailRecord, EmailTemplate (future)
- **Indexes**: Add indexes for query patterns (correlation_id, to_address, status, created_at)
- **Verification**: Run `alembic history --verbose` after creating migrations

### Existing Migrations

- `20250823_1528_ce41648d3fde_initial_email_service_schema.py` - Initial schema (EmailRecord, EventOutbox)
- `20250823_1545_32be4d7e70d0_replace_email_outbox_events_with_.py` - Outbox standardization

### Critical Notes

- Email service owns EmailRecord and EmailTemplate tables
- Outbox table owned by shared library
- Never modify pushed migrations - create new migration to fix issues
- Test migrations against testcontainer database before pushing

Reference: `.claude/rules/085-database-migration-standards.md`
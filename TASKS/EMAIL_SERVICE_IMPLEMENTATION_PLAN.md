# Email Service Implementation - Phase 1: Core Scaffolding

## Understanding the Dominant Pattern

After analyzing the codebase, the dominant pattern is:
- **Integrated Services**: Kafka consumption is integrated directly in `app.py` using Quart's lifecycle hooks
- **NO separate worker_main.py**: Only Essay Lifecycle Service uses that pattern
- **Single app.py manages both HTTP and Kafka**: Using `@app.before_serving`/`@app.after_serving`
- **Monorepo with single lockfile**: Services use workspace dependencies, not individual lock files

## Phase 1 Tasks - Core Email Service Scaffolding

### 1. Service Directory Structure

```
services/email_service/
├── app.py                          # Main application - manages HTTP + Kafka
├── kafka_consumer.py               # Kafka consumer logic
├── event_processor.py              # Core email processing orchestration
├── startup_setup.py                # Centralized initialization
├── config.py                       # SecureServiceSettings
├── metrics.py                      # Prometheus metrics
├── protocols.py                    # EmailProvider, TemplateRenderer, Repository
├── di.py                           # Dishka providers (APP/REQUEST scopes)
├── models_db.py                    # SQLAlchemy models for email tracking
├── api/
│   ├── health_routes.py            # Mandatory /healthz endpoint
│   └── dev_routes.py               # Development-only endpoints
├── implementations/
│   ├── provider_mock_impl.py       # Mock email provider for dev
│   ├── template_renderer_impl.py   # Jinja2 template renderer
│   ├── repository_impl.py          # Email record repository
│   └── event_publisher_impl.py     # Outbox publisher
├── templates/                      # Email templates directory
│   ├── verification.html
│   ├── password_reset.html
│   └── ... other templates
├── alembic/                        # Database migrations
│   └── versions/
├── tests/
├── Dockerfile
├── Dockerfile.dev
├── alembic.ini
├── pyproject.toml
└── README.md
```

### 2. Core Implementation Components

#### 2.1 app.py - Integrated Application

Following CJ Assessment Service pattern:
- `HuleEduApp` with guaranteed infrastructure
- Register `health_bp` and `dev_routes` blueprints
- `@app.before_serving`:
  - Initialize services via `startup_setup.py`
  - Get `KafkaConsumer` from DI container
  - Start `EventRelayWorker` for outbox
  - Create consumer background task
- `@app.after_serving`:
  - Stop `EventRelayWorker`
  - Stop Kafka consumer
  - Cancel consumer task

#### 2.2 config.py - Configuration

```python
class Settings(SecureServiceSettings):
    model_config = SettingsConfigDict(env_prefix="EMAIL_", extra="ignore")
    SERVICE_NAME: str = "email_service"
    
    # Email provider settings
    EMAIL_PROVIDER: Literal["mock", "sendgrid", "ses"] = "mock"
    SENDGRID_API_KEY: str | None = None
    AWS_REGION: str = "us-east-1"
    
    # Template settings
    TEMPLATE_PATH: str = "templates"
    DEFAULT_FROM_EMAIL: str = "noreply@huleedu.com"
    DEFAULT_FROM_NAME: str = "HuleEdu"
    
    # Database settings (inherited from SecureServiceSettings)
    @property
    def database_url(self) -> str:
        # Standard pattern for service databases
```

#### 2.3 protocols.py - Behavioral Contracts

```python
class EmailProvider(Protocol):
    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> EmailSendResult
    
class TemplateRenderer(Protocol):
    async def render(
        self,
        template_id: str,
        variables: dict[str, str],
    ) -> RenderedTemplate
    
class EmailRepository(Protocol):
    async def create_email_record(self, record: EmailRecord) -> None
    async def update_status(
        self,
        message_id: str,
        status: EmailStatus,
        provider_response: str | None = None,
    ) -> None
    async def get_by_message_id(self, message_id: str) -> EmailRecord | None
```

#### 2.4 models_db.py - Database Models

```python
# SQLAlchemy models following patterns
class EmailRecord(Base):
    __tablename__ = "email_records"
    
    message_id = Column(String, primary_key=True)
    to_address = Column(String, nullable=False, index=True)
    from_address = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    template_id = Column(String, nullable=False)
    category = Column(String, nullable=False)  # verification, password_reset, etc.
    status = Column(Enum(EmailStatus), nullable=False, default=EmailStatus.PENDING)
    provider = Column(String, nullable=True)
    provider_message_id = Column(String, nullable=True)
    variables = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    sent_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    failure_reason = Column(String, nullable=True)
    correlation_id = Column(String, nullable=False, index=True)
    
    # Indexes for common queries
    __table_args__ = (
        Index("ix_email_records_status_created", "status", "created_at"),
    )

# Outbox table with topic column (per Rule 022)
class EmailOutboxEvent(Base):
    __tablename__ = "email_outbox_events"
    # Standard outbox columns + topic column
```

#### 2.5 kafka_consumer.py

```python
class EmailKafkaConsumer:
    """Kafka consumer for email service following CJ Assessment pattern."""
    
    def __init__(
        self,
        kafka_bus: KafkaBus,
        event_processor: EmailEventProcessor,
        redis_client: RedisClient,
        settings: Settings,
    ):
        self.topics = [topic_name(ProcessingEvent.EMAIL_NOTIFICATION_REQUESTED)]
        
    @idempotent_consumer(redis_client=redis_client, config=idempotency_config)
    async def handle_message(self, msg: ConsumerRecord) -> None:
        envelope = EventEnvelope[NotificationEmailRequestedV1].model_validate_json(msg.value)
        await self.event_processor.process_email_request(envelope.data)
    
    async def start_consumer(self) -> None:
        # Consumer loop with manual commits
```

#### 2.6 event_processor.py

```python
class EmailEventProcessor:
    """Orchestrates email processing using DI-injected dependencies."""
    
    async def process_email_request(
        self,
        request: NotificationEmailRequestedV1
    ) -> None:
        # 1. Create email record in DB
        # 2. Render template
        # 3. Send via provider
        # 4. Update status in DB
        # 5. Publish outcome event (EmailSentV1 or EmailDeliveryFailedV1)
```

#### 2.7 pyproject.toml

```toml
[project]
name = "huleedu-email-service"
version = "0.1.0"
description = "HuleEdu Email Service"
authors = [
    { name = "Olof Larsson", email = "paunchygent@gmail.com" },
]
requires-python = ">=3.11"
dependencies = [
    "aiokafka",
    "aiohttp",
    "python-dotenv",
    "huleedu-common-core",
    "huleedu-service-libs",
    "pydantic",
    "pydantic-settings",
    "prometheus-client",
    "dishka",
    "quart",
    "quart-dishka",
    "hypercorn",
    "SQLAlchemy[asyncio]",
    "aiosqlite",
    "asyncpg",
    "alembic",
    "jinja2",  # For email templates
    "python-multipart",  # For file uploads if needed
]

[build-system]
requires = ["pdm-backend"]
build-backend = "pdm.backend"

[tool.pdm]
distribution = false

[tool.pdm.dev-dependencies]
test = [
    "pytest",
    "pytest-asyncio",
    "pytest-mock",
    "pytest-cov",
]

[tool.pdm.resolution.overrides]
huleedu-common-core = "file:///app/libs/common_core"
huleedu-service-libs = "file:///app/libs/huleedu_service_libs"

[tool.pdm.scripts]
start = "python app.py"
migrate-upgrade = "alembic upgrade head"
migrate-downgrade = "alembic downgrade -1"
migrate-revision = "alembic revision --autogenerate"
```

### 3. Implementation Checklist

- [ ] Create service directory structure
- [ ] Implement `app.py` with integrated Kafka consumer (following CJ Assessment pattern)
- [ ] Create `config.py` inheriting from `SecureServiceSettings`
- [ ] Define `protocols.py` for DI contracts
- [ ] Implement `di.py` with Dishka providers
- [ ] Create SQLAlchemy models in `models_db.py`
- [ ] Implement `kafka_consumer.py` with idempotent consumer
- [ ] Create `event_processor.py` for orchestration
- [ ] Implement mock email provider for development
- [ ] Create basic Jinja2 template renderer
- [ ] Setup Alembic migrations
- [ ] Create `Dockerfile` and `Dockerfile.dev`
- [ ] Add service to `docker-compose.yml`
- [ ] Implement health and dev routes
- [ ] Add metrics collection
- [ ] Create initial email templates

## Key Patterns to Follow

1. **NO worker_main.py** - Everything managed in `app.py`
2. **Guaranteed Infrastructure** - `app.database_engine` and `app.container` set immediately
3. **Lifecycle Hooks** - `@app.before_serving`/`@app.after_serving` for Kafka consumer
4. **Outbox Pattern** - `EventRelayWorker` for reliable event publishing
5. **Idempotent Consumer** - Using `@idempotent_consumer` decorator
6. **Structured Errors** - `HuleEduError` factories from service libs
7. **Single DI Container** - Shared between HTTP and Kafka components
8. **Monorepo Dependencies** - Workspace deps with PDM overrides

## Implementation Status & Next Phases

### ✅ Phase 1 & 2: Core Service Architecture (COMPLETE)
- [x] Service directory structure with integrated Kafka consumer
- [x] DI container with corrected APP/REQUEST scoping
- [x] Mock email provider and Jinja2 template rendering
- [x] Database models with comprehensive audit trails
- [x] Docker integration with hot-reload development support
- [x] Health and development API endpoints
- [x] EventRelayWorker for outbox pattern integration

### ✅ Phase 3: Observability & Resilience (COMPLETE)
- [x] Prometheus metrics system (15+ business intelligence metrics)
- [x] Event publishing architecture (EmailSentV1/EmailDeliveryFailedV1)
- [x] Professional email templates (verification, password reset, welcome)
- [x] Circuit breaker resilience pattern for Kafka publisher
- [x] Database schema standardization (standard event_outbox table)
- [x] **CRITICAL FIX**: Outbox table migration successfully applied

### 🚧 Phase 4A: Comprehensive Testing (CURRENT TASK)
- [ ] Unit test coverage for all components (event processor, kafka consumer, etc.)
- [ ] Contract tests for event schemas and database models
- [ ] Integration tests for component interactions  
- [ ] E2E tests for complete email processing workflows
- [ ] Parallel test execution following Rule 075 methodology
- [ ] Test structure mirroring identity_service patterns

### Phase 4B: Advanced Email Provider Implementation (FUTURE)

#### ULTRATHINK: Production-Ready Email Infrastructure

**DKIM Implementation with Namecheap Configuration:**

```python
# Configuration settings to add to config.py
EMAIL_PROVIDER: Literal["mock", "sendgrid", "ses", "namecheap"] = "mock"
EMAIL_DOMAIN: str = "hule.education"
EMAIL_FROM_ADDRESS: str = "info@hule.education"

# DKIM settings (Namecheap-specific)
DKIM_ENABLED: bool = True
DKIM_SELECTOR: str = "default"  # Matches DNS record: default._domainkey
DKIM_PRIVATE_KEY_PATH: str = "secrets/dkim_private.pem"  # Gitignored RSA private key

# SMTP settings for Namecheap Private Email
SMTP_HOST: str = "mail.privateemail.com"
SMTP_PORT: int = 587
SMTP_USERNAME: str = "info@hule.education"  # Catch-all inbox
SMTP_PASSWORD: str | None = None  # From secure environment variables
```

**DNS Configuration (Already Set by User):**
- DKIM TXT Record: `default._domainkey.hule.education`
- RSA Public Key: Already configured in DNS
- SPF Record: For domain authorization
- DMARC Policy: For email authentication

**Security Implementation:**
```bash
# secrets/ directory structure (gitignored)
secrets/
└── dkim_private.pem  # RSA private key for DKIM signing

# Environment variables (.env)
EMAIL_PROVIDER=namecheap
SMTP_PASSWORD=<secure-password-from-secrets-manager>
DKIM_PRIVATE_KEY_PATH=secrets/dkim_private.pem

# Production environment overrides
HULEEDU_ENVIRONMENT=production
EMAIL_FROM_ADDRESS=info@hule.education
EMAIL_DOMAIN=hule.education
```

#### Production Email Providers

**SendGrid Provider Implementation:**
- [ ] SendGrid API client with template support
- [ ] Template synchronization with SendGrid dynamic templates
- [ ] Webhook handlers for delivery events, bounces, spam reports
- [ ] Rate limiting: 100 emails/second (free tier), 1000/second (paid)
- [ ] Configuration: `SENDGRID_API_KEY`, `SENDGRID_TEMPLATE_PREFIX`

**AWS SES Provider Implementation:**
- [ ] AWS SDK integration with IAM role authentication
- [ ] SES template management and rendering
- [ ] SNS webhook integration for delivery notifications
- [ ] Rate limiting based on SES sending limits (configurable)
- [ ] Configuration: `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

**Namecheap Private Email Provider Implementation:**
- [ ] SMTP client with DKIM signing using `dkimpy` library
- [ ] RSA private key loading and secure management
- [ ] Email composition with proper headers and DKIM signatures
- [ ] SMTP connection pooling and authentication
- [ ] Configuration: DKIM settings + SMTP credentials above

#### Advanced Email Features

**Retry Logic with Exponential Backoff:**
```python
# Retry configuration
MAX_RETRY_ATTEMPTS: int = 3
INITIAL_RETRY_DELAY: int = 30  # seconds
BACKOFF_MULTIPLIER: float = 2.0
MAX_RETRY_DELAY: int = 300  # 5 minutes

# Provider-specific retry strategies
PROVIDER_RETRY_CONFIG = {
    "namecheap": {"transient_errors": ["SMTP timeout", "Connection refused"]},
    "sendgrid": {"transient_errors": ["Rate limit exceeded", "Service unavailable"]},
    "ses": {"transient_errors": ["Throttling", "Service unavailable"]}
}
```

**Rate Limiting Implementation:**
- [ ] Per-provider rate limiting with Redis-backed sliding window
- [ ] Configurable limits: emails/second, emails/hour, emails/day  
- [ ] Circuit breaker integration for rate limit violations
- [ ] Metrics for rate limiting effectiveness and quota utilization

**Webhook Handlers for Provider Events:**
- [ ] SendGrid webhook endpoint: `/webhooks/sendgrid` (delivery, bounce, spam)
- [ ] AWS SES SNS webhook endpoint: `/webhooks/ses` (delivery, bounce, complaint)
- [ ] Webhook signature verification for security
- [ ] Event processing: update email_records status based on provider feedback
- [ ] Retry failed deliveries based on provider-specific error codes

#### Email Queue Management
- [ ] High-volume email processing with batch operations
- [ ] Priority queues for different email categories (urgent, normal, bulk)
- [ ] Dead letter queue for permanently failed emails
- [ ] Queue monitoring and alerting via Prometheus metrics

**Implementation Priority:**
1. **Namecheap Provider** (immediate need with existing DKIM setup)
2. **SendGrid Provider** (scalable production option)
3. **Rate Limiting & Retry Logic** (production reliability)
4. **Webhook Handlers** (delivery feedback loop)
5. **AWS SES Provider** (enterprise backup option)

### Phase 5: Production Operations (FUTURE)
- [ ] Performance metrics and dashboards
- [ ] Distributed tracing integration  
- [ ] Email delivery analytics
- [ ] Advanced template features (layouts, partials, A/B testing)
- [ ] Email reputation monitoring and management

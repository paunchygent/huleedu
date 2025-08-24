# Identity, Entitlements, and Email Services — Scaffolding and Contracts

Purpose-built scaffolding and contracts to complete the backend skeleton before frontend work. Aligned with repository rules (EDA, DI, Protocols, HTTP/Worker split) and keeps the frontend thin.

## Scope

- Identity (User) Service: authentication, user lifecycle, roles/tenancy, JWT/JWKS
- Entitlements Service: plans, quotas, rate-limits, credits, usage metering, ACL for read access
- Email Service: transactional mail, provider adapters, templating, delivery webhooks
- Event contracts (Pydantic) for all interactions, topic naming, and gateway integration

---

## Architectural Alignment

- Pattern: Event-driven microservices, DDD, async Python; per-service PostgreSQL DBs
- Frameworks: Internal services (Identity, Entitlements, Email) use Quart; API Gateway is FastAPI
- DI: `typing.Protocol` contracts in `protocols.py`, Dishka providers in `di.py`, with `APP`/`REQUEST` scopes
- Services:
  - **Integrated Pattern**: `app.py` manages both HTTP and Kafka consumer lifecycle via `@app.before_serving/@app.after_serving`
  - **HTTP-only Pattern**: HuleEduApp with `startup_setup.py` managing Kafka consumer lifecycle (Identity Service)
  - **Worker-only Pattern**: `worker_main.py` entry point with no HTTP API (NLP Service)
  - **Kafka Components**: `kafka_consumer.py` (consumer class), `event_processor.py` (business orchestration)
  - **Outbox**: Use `huleedu_service_libs.outbox.EventRelayWorker` for reliable event publishing
    - Started alongside Kafka consumers in service lifecycle
    - Do not inject/pass Kafka bus into business logic; publish only via outbox
- Events: `EventEnvelope[T]` (schema_version=int, default 1), publish via `topic_name(ProcessingEvent.X)`
- Persistence: SQLAlchemy async, Alembic migrations (per service), repository‑managed sessions (Rule 042)
  - Follow Rule 085: `.env` autoload; no hardcoded DB URLs; share DB session with outbox for atomic writes

---

## Common Contracts (Pydantic)

Place contracts under `libs/common_core/src/common_core/` as separate domain modules (flat layout). Do not create a `models/` subpackage. Namespaces shown below; adjust imports as needed.

```python
# libs/common_core/src/common_core/identity_models.py
from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime
from typing import Literal, Optional, List

class UserRegisteredV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    email: EmailStr
    registered_at: datetime
    correlation_id: str

class EmailVerificationRequestedV1(BaseModel):
    user_id: str
    email: EmailStr
    token_id: str
    expires_at: datetime
    correlation_id: str

class EmailVerifiedV1(BaseModel):
    user_id: str
    verified_at: datetime
    correlation_id: str

class PasswordResetRequestedV1(BaseModel):
    user_id: str
    email: EmailStr
    token_id: str
    expires_at: datetime
    correlation_id: str

class LoginSucceededV1(BaseModel):
    user_id: str
    org_id: Optional[str] = None
    timestamp: datetime
    correlation_id: str

class LoginFailedV1(BaseModel):
    email: EmailStr
    reason: Literal["invalid_credentials", "locked", "unverified", "other"]
    timestamp: datetime
    correlation_id: str

class JwksPublicKeyV1(BaseModel):
    kid: str
    kty: str
    n: str
    e: str
    alg: Literal["RS256"] = "RS256"
    use: Literal["sig"] = "sig"

class JwksResponseV1(BaseModel):
    keys: List[JwksPublicKeyV1]
```

```python
# libs/common_core/src/common_core/emailing_models.py
from __future__ import annotations
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Dict, Optional, Literal

class NotificationEmailRequestedV1(BaseModel):
    message_id: str
    template_id: str
    to: EmailStr
    variables: Dict[str, str] = {}
    category: Literal["verification", "password_reset", "receipt", "teacher_notification", "system"]
    correlation_id: str

class EmailSentV1(BaseModel):
    message_id: str
    provider: str
    sent_at: datetime
    correlation_id: str

class EmailDeliveryFailedV1(BaseModel):
    message_id: str
    provider: str
    failed_at: datetime
    reason: str
    correlation_id: str
```

```python
# libs/common_core/src/common_core/entitlements_models.py
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List
from datetime import datetime

SubjectType = Literal["org", "user"]

class SubjectRefV1(BaseModel):
    type: SubjectType
    id: str  # uuid

class EntitlementDefinitionV1(BaseModel):
    feature: str  # e.g., "batch_process", "ai_tool_usage", "essay_assessed"
    limit_per_window: Optional[int] = None  # None means unlimited
    window_seconds: Optional[int] = None    # e.g., per 60s or per 30 days (2592000)
    cost_per_unit: Optional[float] = None   # for metered billing/pay-as-you-go

class PlanV1(BaseModel):
    plan_id: str
    name: str
    entitlements: List[EntitlementDefinitionV1]

class SubscriptionActivatedV1(BaseModel):
    subject: SubjectRefV1
    plan_id: str
    activated_at: datetime
    correlation_id: str

class SubscriptionChangedV1(BaseModel):
    subject: SubjectRefV1
    old_plan_id: Optional[str] = None
    new_plan_id: str
    changed_at: datetime
    correlation_id: str

class SubscriptionCanceledV1(BaseModel):
    subject: SubjectRefV1
    plan_id: str
    canceled_at: datetime
    correlation_id: str

class UsageAuthorizedV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1
    authorization_id: str
    expires_at: Optional[datetime] = None
    correlation_id: str

class UsageRecordedV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1
    period_start: datetime
    period_end: datetime
    correlation_id: str

class CreditBalanceChangedV1(BaseModel):
    subject: SubjectRefV1
    delta: int
    new_balance: int
    reason: str
    correlation_id: str

class RateLimitExceededV1(BaseModel):
    subject: SubjectRefV1
    metric: str
    limit: int
    window_seconds: int
    correlation_id: str

class ResourceAccessGrantedV1(BaseModel):
    resource_id: str
    subject: SubjectRefV1 | None = None
    email_hash: Optional[str] = None  # hashed student email for privacy
    rights: List[str] = ["read"]
    expires_at: Optional[datetime] = None
    correlation_id: str
```

---

## Event Topics & Enums

Use `ProcessingEvent` + `topic_name()` from `common_core.event_enums`. Extend the enum and mapping with the following entries and always publish via `topic_name(ProcessingEvent.X)`:

Identity events:

- `IDENTITY_USER_REGISTERED` → `huleedu.identity.user.registered.v1`
- `IDENTITY_EMAIL_VERIFICATION_REQUESTED` → `huleedu.identity.email.verification.requested.v1`
- `IDENTITY_EMAIL_VERIFIED` → `huleedu.identity.email.verified.v1`
- `IDENTITY_PASSWORD_RESET_REQUESTED` → `huleedu.identity.password.reset.requested.v1`
- `IDENTITY_LOGIN_SUCCEEDED` → `huleedu.identity.login.succeeded.v1`
- `IDENTITY_LOGIN_FAILED` → `huleedu.identity.login.failed.v1`

Email events:

- `EMAIL_NOTIFICATION_REQUESTED` → `huleedu.email.notification.requested.v1`
- `EMAIL_SENT` → `huleedu.email.sent.v1`
- `EMAIL_DELIVERY_FAILED` → `huleedu.email.delivery_failed.v1`

Entitlements events:

- `ENTITLEMENTS_SUBSCRIPTION_ACTIVATED` → `huleedu.entitlements.subscription.activated.v1`
- `ENTITLEMENTS_SUBSCRIPTION_CHANGED` → `huleedu.entitlements.subscription.changed.v1`
- `ENTITLEMENTS_SUBSCRIPTION_CANCELED` → `huleedu.entitlements.subscription.canceled.v1`
- `ENTITLEMENTS_USAGE_AUTHORIZED` → `huleedu.entitlements.usage.authorized.v1`
- `ENTITLEMENTS_USAGE_RECORDED` → `huleedu.entitlements.usage.recorded.v1`
- `ENTITLEMENTS_CREDIT_BALANCE_CHANGED` → `huleedu.entitlements.credit.balance.changed.v1`
- `ENTITLEMENTS_RATE_LIMIT_EXCEEDED` → `huleedu.entitlements.rate_limit.exceeded.v1`
- `ENTITLEMENTS_RESOURCE_ACCESS_GRANTED` → `huleedu.entitlements.resource.access.granted.v1`

Example usage:

```python
from common_core.event_enums import ProcessingEvent, topic_name
from common_core.events.envelope import EventEnvelope
from common_core.identity_models import UserRegisteredV1

payload = UserRegisteredV1(...)
envelope = EventEnvelope[UserRegisteredV1](
    event_type=topic_name(ProcessingEvent.IDENTITY_USER_REGISTERED),
    source_service="identity_service",
    data=payload,
)
```

---

## Identity Service — HTTP + Kafka Consumer Scaffold

Directory skeleton (HuleEduApp with integrated Kafka consumer):

```
services/identity_service/
  app.py                      # HuleEduApp with blueprint registration
  startup_setup.py            # DI init, Kafka consumer lifecycle, EventRelayWorker
  config.py                   # Pydantic settings
  protocols.py                # UserRepo, TokenIssuer, PasswordHasher, SessionRepo
  di.py                       # Providers (APP/REQUEST scopes)
  models_db.py                # SQLAlchemy models
  kafka_consumer.py           # IdentityKafkaConsumer for internal events
  notification_orchestrator.py # Bridges Identity events to Email Service
  api/
    auth_routes.py            # register/login/refresh/logout/verify/reset/me
    registration_routes.py    # User registration
    verification_routes.py    # Email verification
    password_routes.py        # Password reset/change
    profile_routes.py         # User profile management
    session_routes.py         # Session management
    well_known_routes.py      # JWKS/OpenID endpoints
    health_routes.py          # /healthz, /metrics
  implementations/
    user_repository_impl.py
    session_repository_impl.py
    password_hasher_impl.py   # Argon2id
    token_issuer_impl.py      # HS256 (dev), RS256 + JWKS (prod)
    outbox_manager.py         # Outbox publisher
  alembic/
  README.md
  tests/
```

Key patterns:

**Integrated Kafka Consumer Lifecycle**:

```python
# services/identity_service/startup_setup.py
@app.before_serving
async def startup() -> None:
    # Start outbox relay worker
    relay_worker = await request_container.get(EventRelayWorker)
    await relay_worker.start()
    
    # Start IdentityKafkaConsumer for internal event processing
    identity_kafka_consumer = await request_container.get(IdentityKafkaConsumer)
    consumer_task = asyncio.create_task(identity_kafka_consumer.start_consumer())
    
@app.after_serving
async def cleanup() -> None:
    # Stop consumer and relay worker
    await identity_kafka_consumer.stop_consumer()
    await relay_worker.stop()
```

**NotificationOrchestrator Bridge Pattern**:

```python
# services/identity_service/notification_orchestrator.py
class NotificationOrchestrator:
    async def handle_user_registered(self, event: UserRegisteredV1) -> None:
        # Transform to NotificationEmailRequestedV1
        notification = NotificationEmailRequestedV1(
            message_id=f"welcome-{event.user_id}-{uuid4().hex[:8]}",
            template_id="welcome",
            to=event.email,
            variables={"user_name": event.email.split("@")[0].title()}
        )
        # Publish via outbox
        await self.outbox_manager.publish_to_outbox(...)
```

Pydantic request/response schemas:

```python
# services/identity_service/api/schemas.py
from __future__ import annotations
from pydantic import BaseModel, EmailStr
from typing import Optional, List

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    org_id: Optional[str] = None

class RegisterResponse(BaseModel):
    user_id: str
    email: EmailStr
    org_id: Optional[str] = None
    email_verification_required: bool = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int

class MeResponse(BaseModel):
    user_id: str
    email: EmailStr
    org_id: Optional[str] = None
    roles: List[str] = []
    email_verified: bool = False
```

Router outline (Quart):

```python
# services/identity_service/api/auth_routes.py
from __future__ import annotations
from quart import Blueprint, request, jsonify
from quart_dishka import inject
from dishka import FromDishka

from .schemas import RegisterRequest, RegisterResponse, LoginRequest, TokenPair, MeResponse
from ..protocols import UserRepo, SessionRepo, PasswordHasher, TokenIssuer

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")

@bp.post("/register")
@inject
async def register(user_repo: FromDishka[UserRepo], hasher: FromDishka[PasswordHasher]):
    payload = RegisterRequest(**(await request.get_json()))
    user = await user_repo.create_user(payload.email, payload.org_id, hasher.hash(payload.password))
    # enqueue outbox event: IDENTITY_USER_REGISTERED
    return jsonify(RegisterResponse(**user).model_dump(mode="json")), 201

@bp.post("/login")
@inject
async def login(user_repo: FromDishka[UserRepo], tokens: FromDishka[TokenIssuer]):
    payload = LoginRequest(**(await request.get_json()))
    user = await user_repo.get_user_by_email(payload.email)
    # verify password, build roles/org context, emit login events
    pair = TokenPair(access_token=tokens.issue_access_token(user["id"], user.get("org_id"), user.get("roles", [])),
                     refresh_token=tokens.issue_refresh_token(user["id"])[0],
                     expires_in=3600)
    return jsonify(pair.model_dump(mode="json"))

@bp.get("/me")
async def me():
    # validate bearer via gateway in production; dev helper can be retained under /dev
    return jsonify(MeResponse(user_id="user_x", email="u@example.com").model_dump(mode="json"))
```

JWKS endpoint (RS256 in prod):

```
GET /.well-known/jwks.json → JwksResponseV1
```

- Set `kid` on tokens and expose matching key in JWKS; gateway caches by `kid`

---

## Entitlements Service — HTTP + Kafka Consumer Scaffold

Integrated service with Quart HTTP decision endpoints and Kafka consumer for metering and ACL events.

```
services/entitlements_service/
  app.py                       # Integrated Quart + Kafka lifecycle (like Email Service)
  startup_setup.py             # DI init, Kafka consumer lifecycle, EventRelayWorker
  config.py                    # Pydantic settings
  protocols.py                 # repositories + cache + policy loader interfaces
  di.py                        # Providers
  models_db.py                 # plans, subscriptions, counters, credits, acl
  kafka_consumer.py            # EntitlementsKafkaConsumer class
  event_processor.py           # update counters/credits/acl; emit events
  api/
    health_routes.py           # /healthz, /metrics
    decisions_routes.py        # /v1/entitlements/* endpoints
  implementations/
    repositories_impl.py
    cache_impl.py
    policy_loader_impl.py
    outbox_manager.py
  policies/manifest.example.yaml
  alembic/
  README.md
  tests/
```

HTTP endpoints (Gateway-facing):

- `POST /v1/entitlements/decision`
  - Input: `{ subject: {type,id}, metric, amount?: int }`
  - Output: `{ allowed: bool, reason?: str, limit_value?: int, window_seconds?: int, remaining?: int }`
- `POST /v1/entitlements/authorize`
  - Input: `{ subject, metric, amount?: int }`
  - Output: `{ authorization_id, expires_at? }`
- `GET /v1/entitlements/effective?subject_type=&subject_id=`
  - Output: `PlanV1 + overrides` (debug/dev)
- `GET /v1/usage/{subject_type}/{subject_id}`
  - Output: `{ counters: { metric: { period_start, period_end, count }[] } }`
- `POST /v1/acl/check`
  - Input: `{ resource_id, subject? , email_hash? }`
  - Output: `{ allowed: bool }`

Schemas:

```python
# services/entitlements_service/api/schemas.py
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from common_core.entitlements_models import SubjectRefV1

class DecisionRequest(BaseModel):
    subject: SubjectRefV1
    metric: str
    amount: int = 1

class DecisionResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    limit_value: Optional[int] = None
    window_seconds: Optional[int] = None
    remaining: Optional[int] = None

class AuthorizeRequest(DecisionRequest):
    pass

class AuthorizeResponse(BaseModel):
    authorization_id: str
    expires_at: Optional[str] = None

class AclCheckRequest(BaseModel):
    resource_id: str
    subject: Optional[SubjectRefV1] = None
    email_hash: Optional[str] = None

class AclCheckResponse(BaseModel):
    allowed: bool
```

Worker responsibilities:

- Consume `ENTITLEMENTS_USAGE_AUTHORIZED` and `ENTITLEMENTS_USAGE_RECORDED` to update counters
- Emit `ENTITLEMENTS_RATE_LIMIT_EXCEEDED`, `ENTITLEMENTS_CREDIT_BALANCE_CHANGED` as needed
- Maintain ACL grants on `ENTITLEMENTS_RESOURCE_ACCESS_GRANTED`

DB tables (Alembic):

- `plans`, `plan_entitlements(plan_id, feature, limit, window_seconds, cost)`
- `subscriptions(subject_type, subject_id, plan_id, status)`
- `entitlement_overrides(subject_type, subject_id, feature, limit, window_seconds)`
- `usage_counters(subject_type, subject_id, metric, period_start, period_end, count)`
- `credits_ledger(subject_type, subject_id, balance, updated_at)`
- `resource_acl(resource_id, subject_type, subject_id, email_hash, rights, expires_at)`
- Indexes on `{subject_type, subject_id}`

---

## Email Service — Integrated HTTP + Kafka Consumer Scaffold

**ALREADY IMPLEMENTED** - Primary interaction via Kafka events with dev HTTP endpoints.

```
services/email_service/
  app.py                       # Integrated Quart + Kafka lifecycle (@app.before_serving)
  startup_setup.py             # Service initialization
  config.py                    # Pydantic settings (provider, SMTP config)
  protocols.py                 # EmailProvider, TemplateRenderer, EmailRepository
  di.py                        # Providers
  kafka_consumer.py            # EmailKafkaConsumer class
  event_processor.py           # orchestrate send + emit events
  api/
    health_routes.py           # /healthz, /metrics
    dev_routes.py              # /v1/emails/dev/send (dev only)
  implementations/
    provider_mock_impl.py      # Mock provider (testing)
    provider_smtp_impl.py      # SMTP provider (Namecheap Private Email)
    template_renderer_impl.py  # Jinja2 template engine
    repository_impl.py         # PostgreSQL persistence
    outbox_manager.py          # Transactional outbox
  templates/
    verification.html.j2       # Email verification template
    welcome.html.j2            # User welcome template
    password_reset.html.j2     # Password reset template
  models_db.py                 # SQLAlchemy models
  alembic/
  README.md
  tests/
```

**Integrated Kafka Consumer Pattern**:

```python
# services/email_service/app.py
@app.before_serving
async def startup() -> None:
    # Start EventRelayWorker for outbox pattern
    app.relay_worker = await request_container.get(EventRelayWorker)
    await app.relay_worker.start()
    
    # Start Kafka consumer as background task
    app.kafka_consumer = await request_container.get(EmailKafkaConsumer)
    app.consumer_task = asyncio.create_task(app.kafka_consumer.start_consumer())

@app.after_serving
async def cleanup() -> None:
    # Stop EventRelayWorker and Kafka consumer
    await app.relay_worker.stop()
    await app.kafka_consumer.stop_consumer()
```

Events:

- Consume: `EMAIL_NOTIFICATION_REQUESTED`
- Emit: `EMAIL_SENT`, `EMAIL_DELIVERY_FAILED` via outbox pattern

Dev endpoint:

```
POST /v1/emails/dev/send { to, template_id, variables }
```

---

## API Gateway Integration

- Authentication: In development, HS256 may be used; in production, validate RS256 JWTs against Identity Service JWKS (`/.well-known/jwks.json`). Cache by `kid` and validate `exp`. Keep API Gateway as the sole public interface.
- Entitlements guard: Gateway performs preflight checks via Entitlements (`decision`/`authorize`) on expensive endpoints (class creation, batch orchestration, AI/NLP tools). On denial, return structured errors with correlation IDs (Rule 048).
- ACL enforcement: Before proxying sensitive Result Aggregator queries, call Entitlements `acl/check` using subject and resource identifiers.
- Correlation IDs: Propagate `X-Correlation-ID` across gateway→service calls and event publications.

---

## Endpoint Policy Manifest (example)

Store a manifest file (YAML/JSON) loaded by Entitlements Service to resolve policies per endpoint.

```yaml
# services/entitlements_service/policies/manifest.example.yaml
- endpoint: POST /v1/batches
  scope: org
  metric: batch_create
  rate_limit:
    value: 60
    window_seconds: 60

- endpoint: POST /v1/batches/{id}/process
  scope: org
  metric: batch_process
  rate_limit:
    value: 120
    window_seconds: 60

- endpoint: POST /v1/ai/tools/*
  scope: user
  metric: ai_tool_usage
  rate_limit:
    value: 240
    window_seconds: 60

- endpoint: GET /v1/assessments/{id}
  scope: resource
  acl_required: true
```

---

## Phased Implementation Plan

1) **Identity Service** ✅ **COMPLETED**

- HuleEduApp with integrated Kafka consumer lifecycle via `startup_setup.py`
- NotificationOrchestrator bridges Identity events to Email Service
- All authentication endpoints, JWKS, event publishing via outbox
- IdentityKafkaConsumer processes own events for email orchestration

2) **Email Service** ✅ **COMPLETED**

- Integrated `app.py` with Kafka consumer lifecycle via `@app.before_serving`
- Provider abstraction: mock/SMTP with Namecheap Private Email
- Jinja2 templates with subject extraction and variable fallbacks
- Transactional delivery with outbox pattern

3) Entitlements Service (Week 1)

- Follow Email Service integrated pattern: `app.py` manages HTTP + Kafka lifecycle
- Plans + subscriptions + decision engine + Redis cache
- EntitlementsKafkaConsumer for usage/credit/ACL event processing
- Endpoints: decision, authorize, effective, usage
- EventRelayWorker for reliable event publishing

4) Gateway Enforcement (Week 3)

- JWT validation via JWKS; correlation IDs everywhere
- Preflight entitlements checks on expensive routes; structured error responses
- Basic UI impact: none (frontend keeps thin clients)

5) Extensions (Week 4+)

- Credits ledger + pay-as-you-go
- ACL-backed student read access + email-based grants
- MFA/SSO for Identity; more granular roles/scopes

---

## Acceptance Criteria

- Services scaffolded with DI and protocols consistent with repo standards
- Pydantic contracts added to `common_core` with flat module layout and referenced by services
- New identity/entitlements/email events added to `ProcessingEvent` + `_TOPIC_MAPPING`, used via `topic_name()`
- Identity issues tokens and emits events (outbox); JWKS available
- Entitlements provides decision/authorize and records usage; caches limits
- Email consumes notification events and records delivery outcomes
- API Gateway validates JWTs and enforces decisions/ACL on protected endpoints
- All new endpoints documented and testable with mocks

---

## Testing Strategy

- Unit: domain services with in-memory repos; protocol-based fakes
- Integration: service routers + DB (sqlite/pg) + Kafka test producers/consumers (or fakes)
- Contract: validate request/response and event schemas with Pydantic from common_core
- Load: rate-limit behavior with Redis; cache invalidation correctness

---

## Notes

- Keep claims minimal: compute entitlements server-side; do not embed entitlements in JWT
- Use correlation IDs in all requests/events; return them in error responses
- Dev: retain `/dev/auth/test-token` and mock endpoints to accelerate frontend

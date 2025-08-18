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
  - HTTP services: `app.py` < 150 LoC; routes in `api/` per Rule 015
  - Workers: `worker_main.py` (lifecycle/DI), `kafka_consumer.py` (consume loop), `event_processor.py` (business orchestration)
  - Outbox: Use `huleedu_service_libs.outbox` for business‑critical events
    - Do not inject/pass Kafka bus into business logic; publish only via outbox
    - Include `topic` column + partial index on `(published_at, topic, created_at)` where `published_at IS NULL`
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

## Identity Service — HTTP Scaffold

Directory skeleton (Quart HTTP service):

```
services/identity_service/
  app.py                      # <150 LoC; DI init, blueprint registration, middleware
  startup_setup.py            # DB migration, metrics, tracing setup
  config.py                   # Pydantic settings
  metrics.py                  # Prometheus counters/histograms
  protocols.py                # PasswordHasher, TokenIssuer, UserRepo, SessionRepo
  di.py                       # Providers (APP/REQUEST scopes)
  models_db.py                # SQLAlchemy models
  api/
    auth_routes.py            # register/login/refresh/logout/verify/reset/me
  implementations/
    user_repository_postgres_impl.py
    session_repository_postgres_impl.py
    password_hasher_impl.py   # Argon2id
    token_issuer_impl.py      # HS256 (dev), RS256 + JWKS (prod)
    event_publisher_impl.py   # Outbox publisher
  alembic/
  README.md
  tests/
```

Key protocols:

```python
# services/identity_service/protocols.py
from __future__ import annotations
from typing import Protocol, Optional

class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...
    def verify(self, hash: str, password: str) -> bool: ...

class TokenIssuer(Protocol):
    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str: ...
    def issue_refresh_token(self, user_id: str) -> tuple[str, str]: ...  # token, jti
    def verify(self, token: str) -> dict: ...

class UserRepo(Protocol):
    async def create_user(self, email: str, org_id: str | None, password_hash: str) -> dict: ...
    async def get_user_by_email(self, email: str) -> Optional[dict]: ...
    async def set_email_verified(self, user_id: str) -> None: ...

class SessionRepo(Protocol):
    async def store_refresh(self, user_id: str, jti: str, exp_ts: int) -> None: ...
    async def revoke_refresh(self, jti: str) -> None: ...
    async def is_refresh_valid(self, jti: str) -> bool: ...
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

## Entitlements Service — HTTP + Worker Scaffold

Single service with Quart HTTP decision endpoints and Kafka worker for metering and ACL events.

```
services/entitlements_service/
  app.py                       # HTTP: decisions, effective entitlements, usage reads
  startup_setup.py             # DB init, metrics, tracing
  config.py                    # Pydantic settings
  metrics.py                   # Metrics
  protocols.py                 # repositories + cache + policy loader interfaces
  di.py                        # Providers
  models_db.py                 # plans, subscriptions, counters, credits, acl
  api/
    decisions_routes.py        # /v1/entitlements/* endpoints
  implementations/
    repositories_postgres_impl.py
    cache_redis_impl.py
    policy_loader_impl.py
    event_publisher_impl.py
  worker_main.py               # DI + lifecycle
  kafka_consumer.py            # consume loop
  event_processor.py           # update counters/credits/acl; emit events
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

## Email Service — Worker + Dev HTTP Scaffold

Primary interaction via events; include a minimal dev/test Quart HTTP layer.

```
services/email_service/
  app.py                       # optional dev/test endpoints only
  config.py                    # Pydantic settings (provider, API keys)
  metrics.py                   # Metrics
  protocols.py                 # Provider, template renderer, repository
  di.py                        # Providers
  api/
    dev_routes.py              # /v1/emails/dev/send (dev only)
  implementations/
    provider_sendgrid_impl.py | provider_ses_impl.py
    template_renderer_jinja2.py
    event_publisher_impl.py
  worker_main.py               # DI + lifecycle
  kafka_consumer.py            # consume loop
  event_processor.py           # orchestrate send + emit events
  README.md
  tests/
```

Events:
- Consume: `EMAIL_NOTIFICATION_REQUESTED`
- Emit: `EMAIL_SENT`, `EMAIL_DELIVERY_FAILED`

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

1) Identity Minimal (Week 1)
- Password hashing (Argon2id), HS256 in dev, RS256 + JWKS in prod
- Endpoints: register, login, me, verify email (token exchange), request/reset password
- Emit identity events via outbox; add Alembic migrations
  - PDM: avoid version pinning; use Docker overrides for local libs

2) Entitlements Core (Week 2)
- Plans + subscriptions + decision engine + Redis cache
- Endpoints: decision, authorize, effective, usage; worker: usage recording
- Integrate simple policy manifest; basic rate limiting

3) Email Core (Week 2)
- Provider adapter (SES or SendGrid), Jinja2 templates, message status tracking
- Worker consumes email requested events; dev HTTP endpoint
- Webhook handlers (stretch): delivery, bounce, complaint → status updates

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

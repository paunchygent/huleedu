# Identity, Entitlements, and Email Services — Scaffolding and Contracts

Purpose-built scaffolding and contracts to complete the backend skeleton before frontend work. Aligned with repository rules (EDA, DI, Protocols, HTTP/Worker split) and keeps the frontend thin.

## Scope

- Identity (User) Service: authentication, user lifecycle, roles/tenancy, JWT/JWKS
- Entitlements Service: plans, quotas, rate-limits, credits, usage metering, ACL for read access
- Email Service: transactional mail, provider adapters, templating, delivery webhooks
- Event contracts (Pydantic) for all interactions, topic naming, and gateway integration

---

## Architectural Alignment

- Pattern: Event-driven microservices, DDD, async Python (Quart/FastAPI equivalent patterns), per-service DBs
- DI: `typing.Protocol` interfaces in `protocols.py`, providers in `di.py`, `APP`/`REQUEST` scopes
- Services:
  - HTTP services: `app.py` < 150 LoC; routers in `api/`
  - Workers: `worker_main.py` (lifecycle/DI), `event_processor.py` (core logic)
- Events: `EventEnvelope` (existing), Kafka topics via `topic_name()`
- Persistence: SQLAlchemy async, Alembic migrations (per service)

---

## Common Contracts (Pydantic)

Place under `libs/common_core/src/common_core/models/` as separate modules. Namespaces shown below; adjust imports as needed.

```python
# libs/common_core/src/common_core/models/identity.py
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
# libs/common_core/src/common_core/models/emailing.py
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
# libs/common_core/src/common_core/models/entitlements.py
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

## Kafka Topics

- identity.user_registered.v1
- identity.email_verification_requested.v1
- identity.email_verified.v1
- identity.password_reset_requested.v1
- identity.login_succeeded.v1
- identity.login_failed.v1
- email.notification_requested.v1
- email.sent.v1
- email.delivery_failed.v1
- entitlements.subscription_activated.v1
- entitlements.subscription_changed.v1
- entitlements.subscription_canceled.v1
- entitlements.usage_authorized.v1
- entitlements.usage_recorded.v1
- entitlements.credit_balance_changed.v1
- entitlements.rate_limit_exceeded.v1
- entitlements.resource_access_granted.v1

Use `topic_name(service="identity", name="user_registered", version=1)` style helper.

---

## Identity Service — HTTP Scaffold

Directory skeleton (HTTP service):

```
services/identity_service/
  app.py                     # <150 LoC, DI init, router include
  api/
    auth.py                  # register/login/refresh/logout/verify/reset/me
  domain/
    repositories.py          # SQLAlchemy repos
    services.py              # domain services (registration, sessions)
    schemas.py               # Pydantic request/response models
  infra/
    db.py                    # engine/session
    models.py                # SQLAlchemy models
    security.py              # Argon2id, JWT issue/verify
  protocols.py               # PasswordHasher, TokenIssuer, UserRepo, SessionRepo
  di.py                      # Providers (APP/REQUEST scopes)
  migrations/                # Alembic
  README.md
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
# services/identity_service/domain/schemas.py
from __future__ import annotations
from pydantic import BaseModel, EmailStr, Field
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

Router outline (Quart/FastAPI-like):

```python
# services/identity_service/api/auth.py
from __future__ import annotations
from quart import Blueprint, request, jsonify
from .containers import get_services  # DI helper
from ..domain.schemas import RegisterRequest, RegisterResponse, LoginRequest, TokenPair, MeResponse

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")

@bp.post("/register")
async def register():
    svc = get_services().identity
    payload = RegisterRequest(**(await request.get_json()))
    user = await svc.register(payload)
    return jsonify(RegisterResponse(**user).model_dump()), 201

@bp.post("/login")
async def login():
    svc = get_services().identity
    payload = LoginRequest(**(await request.get_json()))
    tokens = await svc.login(payload)
    return jsonify(TokenPair(**tokens).model_dump())

@bp.get("/me")
async def me():
    svc = get_services().identity
    user = await svc.me(request)
    return jsonify(MeResponse(**user).model_dump())
```

JWKS endpoint (RS256 in prod):

```
GET /.well-known/jwks.json → JwksResponseV1
```

---

## Entitlements Service — HTTP + Worker Scaffold

Single service with HTTP decision endpoints and worker for metering events.

```
services/entitlements_service/
  app.py                      # HTTP: decisions, subjects, usage read
  api/
    decisions.py              # /v1/entitlements/* endpoints
  domain/
    policies.py               # endpoint→policy mapping loader
    services.py               # decision engine, rate limit, credits
    schemas.py                # Pydantic I/O models
  infra/
    db.py, models.py          # plans, subscriptions, usage, credits, acl
    cache.py                  # Redis cache for decisions/limits
  worker_main.py              # DI + consumer loop
  event_processor.py          # consume usage/record events, update counters
  protocols.py                # repositories + cache interfaces
  di.py                       # providers
  migrations/
  README.md
```

HTTP endpoints (Gateway-facing):

- `POST /v1/entitlements/decision`
  - Input: `{ subject: {type,id}, metric, amount?: int }`
  - Output: `{ allowed: bool, reason?: str, limit?: {value, window_seconds}, remaining?: int }`
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
# services/entitlements_service/domain/schemas.py
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from common_core.models.entitlements import SubjectRefV1

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
- Consume `UsageAuthorizedV1` and `UsageRecordedV1` to update counters
- Emit `RateLimitExceededV1`, `CreditBalanceChangedV1` as needed
- Maintain ACL grants on `ResourceAccessGrantedV1`

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

Primary interaction via events, with optional dev/test HTTP.

```
services/email_service/
  app.py                      # optional dev/test endpoints only
  api/
    dev.py                    # /v1/emails/dev/send (dev only)
  domain/
    templates.py              # Jinja2 renderer
    services.py               # orchestrates provider send + events
  infra/
    providers/
      base.py                 # MailProvider protocol
      ses.py | sendgrid.py    # adapters
    db.py, models.py          # messages, template versions, events
  worker_main.py
  event_processor.py          # consume NotificationEmailRequestedV1 → send → emit EmailSent/Failed
  protocols.py                # MailProvider, TemplateRepo, MessageRepo
  di.py
  migrations/
  README.md
```

Provider protocol:

```python
# services/email_service/infra/providers/base.py
from __future__ import annotations
from typing import Protocol, Mapping

class MailProvider(Protocol):
    async def send(self, to: str, subject: str, html: str, text: str | None = None, headers: Mapping[str, str] = {}) -> str: ...
```

Dev endpoint:

```
POST /v1/emails/dev/send { to, template_id, variables }
```

---

## API Gateway Integration Checklist

- Identity
  - Validate JWT via RS256 JWKS (`/.well-known/jwks.json`), cache keys
  - Expose `/v1/auth/*` by proxying to Identity service or via direct router composition
  - Include `X-Org-Id`, `X-User-Id`, `X-Correlation-Id` on outgoing requests
- Entitlements
  - For protected endpoints, call `POST /v1/entitlements/decision` then optionally `/authorize`
  - Cache decision for short TTL (e.g., 30–60s) per `{subject, metric}` key
  - On denial, return structured error with correlation ID
- Email
  - Emit `NotificationEmailRequestedV1` for transactional messages (verification/reset/receipts)

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
- Password hashing (Argon2id), HS256 in dev, RS256+JWKS in prod
- Endpoints: register, login, me, verify email (token exchange), request/reset password
- Emit identity events; add Alembic migrations

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
- Pydantic contracts added to common_core and referenced by services
- Identity issues tokens and emits events; JWKS available
- Entitlements provides decision/authorize and records usage; caches limits
- Email consumes notification events and records delivery outcomes
- API Gateway validates JWTs and enforces decisions on protected endpoints
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


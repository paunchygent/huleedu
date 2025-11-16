# Identity Service

## Service Identity
- **Port**: 5003
- **Purpose**: Authentication, user management, session control
- **Stack**: HuleEduApp, PostgreSQL, Redis, Kafka

## Architecture

```
app.py                  # HuleEduApp setup
api/
  health_routes.py      # /healthz, /metrics
  auth_routes.py        # Login, logout, refresh, introspect, revoke
  registration_routes.py # User registration
  verification_routes.py # Email verification
  password_routes.py    # Password reset/change
  profile_routes.py     # User profile management
  session_routes.py     # Session management
  well_known_routes.py  # JWKS/OpenID endpoints
protocols.py            # UserRepo, TokenIssuer, RateLimiter protocols
di.py                   # Dishka providers
implementations/        # Concrete implementations
models_db.py           # SQLAlchemy models
```

## API Endpoints

**Base**: `/v1/auth`

- `POST /register`: User registration with profile creation
- `POST /login`: Authenticate user, return JWT tokens
- `POST /logout`: Invalidate refresh token, revoke session
- `POST /refresh`: Exchange refresh token for new access token
- `POST /introspect`: Validate token status (inter-service)
- `POST /revoke`: Revoke specific token by JTI (RFC 7009)
- `POST /request-email-verification`: Request email verification
- `POST /verify-email`: Verify email with token
- `POST /request-password-reset`: Request password reset
- `POST /reset-password`: Reset password with token
- `GET /me`: Get user profile
- `PUT /me`: Update user profile
- `GET /sessions`: List active sessions
- `POST /sessions/revoke`: Revoke specific session
- `POST /sessions/revoke-all`: Revoke all sessions

**OpenID/JWKS**: `/.well-known/jwks.json`, `/.well-known/openid_configuration`

## Database Schema

- `User`: Core user account (email, password_hash, roles, failed_login_attempts, locked_until)
- `UserProfile`: Profile data (person_name, created_at, updated_at)
- `RefreshSession`: JWT refresh token sessions (jti, user_id, expires_at, revoked_at)
- `UserSession`: Active user sessions (session_id, user_id, device_info, last_accessed_at)
- `EmailVerificationToken`: Email verification tokens (token_hash, user_id, expires_at, used_at)
- `PasswordResetToken`: Password reset tokens (token_hash, user_id, expires_at, used_at)
- `AuditLog`: Security audit trail (user_id, action, details, ip_address, user_agent)
- `EventOutbox`: Transactional outbox pattern for events

## Events

**Published**: `UserRegisteredV1`, `LoginSucceededV1`, `LoginFailedV1`, `EmailVerificationRequestedV1`, `EmailVerifiedV1`, `PasswordResetRequestedV1`, `PasswordResetCompletedV1`, `TokenRevokedV1`

**Channels**: Kafka via transactional outbox pattern

**Consumed**: None (stateless authentication service)

## Security Features

**JWT Implementation**:
```python
# Development: HS256 with shared secret
JWT_DEV_SECRET: SecretStr = "dev-secret-change-me"

# Production: RS256 with key rotation
JWT_RS256_PRIVATE_KEY_PATH: Path to private key
JWT_RS256_PUBLIC_JWKS_KID: Key ID for JWKS
```

**Rate Limiting**: Redis-based sliding window
- Login: 5 attempts/minute
- Password reset: 3 requests/hour
- Registration: 10 registrations/hour

**Account Lockout**: 5 failed attempts → 15 minute lockout

**Token Management**:
- Access tokens: 1 hour expiry (stateless)
- Refresh tokens: Session-based with JTI tracking
- Introspection endpoint for inter-service validation
- RFC 7009 compliant revocation

## Key Patterns

**HuleEduApp Integration**:
```python
app = HuleEduApp(__name__)
app.container = container
app.database_engine = engine
```

**Protocol-Based DI**:
```python
class TokenIssuer(Protocol):
    def issue_access_token(self, user_id: str, org_id: str | None, roles: list[str]) -> str: ...
    def issue_refresh_token(self, user_id: str) -> tuple[str, str]: ...  # token, jti
    def verify(self, token: str) -> dict: ...
```

**Rate Limiting**:
```python
# Rate limit key format
key = f"login:ip:{client_ip}"
allowed, remaining = await rate_limiter.check_rate_limit(key, limit=5, window_seconds=60)
```

**Transactional Outbox**:
```python
await event_publisher.publish_user_registered(user_data, correlation_id)
# → EventOutbox → Kafka via outbox pattern
```

## Configuration

Environment prefix: `IDENTITY_`
- `JWT_DEV_SECRET`: Development JWT signing secret
- `JWT_RS256_PRIVATE_KEY_PATH`: Production private key path
- `JWT_ACCESS_TOKEN_EXPIRES_SECONDS`: Access token TTL (default: 3600)
- `JWT_ISSUER`: Canonical issuer for all Identity-minted tokens (default: `huleedu-identity-service`)
- `JWT_AUDIENCE`: Canonical platform audience for access tokens (default: `huleedu-platform`)
- `REDIS_URL`: Redis connection for rate limiting/sessions
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka for event publishing

Token claims
- Access tokens: include `sub`, `exp`, `iat`, `iss`, `aud`, plus domain claims (`org`, `roles`).
- Refresh tokens: include `sub`, `exp`, `iat`, `jti`, `typ=refresh`, `iss` — intentionally no `aud`.

## Development

```bash
# Run service
pdm run -p services/identity_service dev

# Tests
pdm run pytest services/identity_service/tests/

# Type check
pdm run mypy services/identity_service/
```

## Error Handling

Identity Service uses the shared `libs/huleedu_service_libs/error_handling` helpers so every failure returns a deterministic
payload that downstream services (API Gateway, BOS, admin tools) can reason about. Every route catches `HuleEduError` and
serializes the embedded `error_detail` (message, `error_code`, `operation`, correlation_id, optional `status_code`) while
unexpected exceptions are logged and surfaced as generic 500 responses per `.claude/rules/048-structured-error-handling-standards.mdc`.

### ErrorCode Usage

- **Service-specific domain codes** come from `common_core.error_enums.IdentityErrorCode` and cover:
  - Authentication failures: `INVALID_CREDENTIALS`, `ACCOUNT_LOCKED`, `USER_NOT_FOUND`, `USER_ALREADY_EXISTS`.
  - Token lifecycle issues: `TOKEN_INVALID`, `TOKEN_EXPIRED`, `REFRESH_TOKEN_INVALID`, `REFRESH_TOKEN_EXPIRED`.
  - Email verification: `VERIFICATION_TOKEN_INVALID`, `VERIFICATION_TOKEN_EXPIRED`, `EMAIL_ALREADY_VERIFIED`.
  - Password reset: `RESET_TOKEN_INVALID`, `RESET_TOKEN_EXPIRED`, `PASSWORD_RESET_NOT_REQUESTED`.
- **Platform-wide base codes** from `common_core.error_enums.ErrorCode` are reused for shared semantics:
  - `VALIDATION_ERROR` – schema or payload validation failures (`raise_validation_error`).
  - `RESOURCE_NOT_FOUND` – profile/session lookups (`raise_resource_not_found`).
  - `PROCESSING_ERROR` – database persistence problems via `raise_processing_error`.
  - `RATE_LIMITED` – emitted by `raise_rate_limit_error` when Redis-backed checks block a caller.

### Propagation Pattern

1. **Domain handlers** (authentication, registration, verification, password reset, session management, profiles) are the only
   layer that knows business rules. They raise `HuleEduError` with the correct error code and operation label, ensuring logs and
   metrics can attribute failures.
2. **HTTP routes** wrap handlers in try/except, log `error_detail` (correlation_id, code, message) via
   `huleedu_service_libs.logging_utils.create_service_logger`, and convert the detail into a JSON `{ "error": { ... } }`
   envelope so API Gateway contracts stay stable.
3. **Background workflows** (transactional outbox relay, Kafka consumer, verification/password jobs) propagate the same
   exceptions upward; `raise_processing_error` includes database context which is logged by `notification_orchestrator.py`.
4. **Tests** assert that every handler/route surfaces the expected code to prevent regression; see
   `tests/contracts/test_api_response_contracts.py` for the canonical error schema snapshot aligned with
   `libs/common_core/docs/error-patterns.md`.

### Example

```python
from huleedu_service_libs.error_handling import HuleEduError, raise_validation_error
from huleedu_service_libs.error_handling.factories import raise_rate_limit_error
from common_core.error_enums import IdentityErrorCode

if not await self._rate_limiter.check_rate_limit(ip_key, 5, 60):
    raise_rate_limit_error(operation="login", correlation_id=correlation_id)

user = await self._user_repo.get_by_email(login_request.email)
if user is None:
    raise HuleEduError(
        error_code=IdentityErrorCode.USER_NOT_FOUND,
        message="User does not exist",
        operation="login",
        correlation_id=correlation_id,
    )

raise_validation_error(
    message="Profile first_name is required",
    operation="update_profile",
    correlation_id=correlation_id,
)
```

## Testing

Testing follows `.claude/rules/075-test-creation-methodology.mdc` and keeps unit/integration boundaries explicit—no implicit
`conftest` fixtures outside of their scope.

### Layout

```
tests/
├── unit/                    # Pure logic + HTTP route tests with AsyncMock dependencies
│   ├── test_authentication_handler_unit.py
│   ├── test_auth_routes_unit.py
│   ├── test_password_reset_handler_unit.py
│   ├── test_profile_handler_unit.py
│   ├── test_session_routes_unit.py
│   ├── test_outbox_manager_unit.py
│   └── … (rate limiter, repositories, metrics, JWKS)
├── integration/             # Testcontainers PostgreSQL + real repositories/handlers
│   ├── test_email_verification_integration.py
│   ├── test_password_reset_integration.py
│   ├── test_auth_flow_integration.py
│   └── test_event_publishing_integration.py (verifies transactional outbox + Redis wakeups)
└── contracts/
    └── test_api_response_contracts.py  # Snapshot of HuleEduError payload shape
```

### Execution

```bash
# All tests
pdm run pytest-root services/identity_service/tests/ -v

# Targeted suites
pdm run pytest-root services/identity_service/tests/unit/ -k login
pdm run pytest-root services/identity_service/tests/integration/ -m integration
pdm run pytest-root services/identity_service/tests/contracts/ -v

# Coverage or type checks
pdm run pytest-root services/identity_service/tests/ --cov=services/identity_service --cov-report=term-missing
pdm run typecheck-all  # validates Protocol compliance across handlers
```

### Conventions & Fixtures

- `@pytest.mark.asyncio` wraps every async unit test to keep event loop handling explicit.
- Integration tests set `@pytest.mark.integration` and require Docker/Testcontainers; they spin up PostgreSQL 15 containers,
  run Alembic models via `Base.metadata.create_all`, and use real repositories.
- Quart route tests build `QuartTestClient` instances through `quart_dishka` so dependency injection mirrors production.
- Redis/Kafka interactions are mocked with `AsyncMock(spec=Protocol)` and validated via call assertions to ensure wakeups and
  rate limiter increments fire.
- Contract tests instantiate `HuleEduError` via helper factories to guarantee `error_detail` stays compatible with
  `libs/common_core/docs/error-patterns.md`.

## Migration Workflow

Identity Service ships with Alembic in `services/identity_service/alembic`. The configuration reads the same `Settings`
class used in production so migrations automatically honor the uppercase `DATABASE_URL` built via
`SecureServiceSettings.build_database_url()`.

### Creating a Migration

```bash
cd services/identity_service

# Ensure environment variables are loaded (.env) and point to the correct database.
# For local Docker Compose databases set ENV_TYPE=docker so the host/port switch to container values.

pdm run alembic -c alembic.ini revision --autogenerate -m "add_mfa_tables"
# Review alembic/versions/<timestamp>_add_mfa_tables.py per Rule 085 (indexes, constraints, data migrations)
pdm run alembic -c alembic.ini upgrade head
```

### Standards

- File naming follows `YYYYMMDD_HHMM_<slug>.py` (enforced via alembic.ini `file_template`).
- Model sources live in `models_db.py`; update models first, then autogenerate.
- Use `IDENTITY_DATABASE_URL`/`IDENTITY_SERVICE_DB_*` env vars only when overriding the default builder—never hard-code
  credentials inside migrations.
- Always run `alembic history --verbose` before/after upgrades to confirm the chain.
- Integration tests that hit the database (`tests/integration/*`) double as migration smoke tests when pointed at a fresh schema.
- Never edit committed migrations; create a corrective follow-up revision if changes are needed.

### Existing Revisions

- `20240818_0001_initial_identity_schema.py` – Base tables (users, sessions, verification/password tokens, audit log).
- `20250818_2215_adc8538fe76d_add_user_profiles_table.py` – Split `UserProfile` from `User`.
- `20250821_1316_5c38467d2203_add_security_and_session_management_.py` – Lockout metadata + refresh sessions table.
- `20250822_1510_79f0cd9fc513_fix_missing_uuid_default_for_users_id_.py` – UUID defaults remediation.
- `20250822_1556_275f264d0c64_fix_missing_uuid_defaults_for_token_.py` – Token UUID defaults.
- `b467d39e123b_add_email_verification_tokens_table.py` – Adds verification token persistence.
- `c9ba97ebc0f1_add_password_reset_tokens_table.py` – Password reset token storage.

Reference: `.claude/rules/085-database-migration-standards.md` for full checklist (idempotent upgrades, data backfills, and
promotion gating).

## CLI Tools

Identity Service currently exposes functionality exclusively through its HTTP API and Kafka events. There is no Typer/Click
command surface yet; administrative automation (user seeding, forced revocations, rate-limit resets) is performed via the
domain handlers invoked by API Gateway. If a CLI is added in the future it should follow the monorepo-standard Typer layout
described in `.claude/rules/090-documentation-standards.mdc`.

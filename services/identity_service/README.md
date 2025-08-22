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
- `REDIS_URL`: Redis connection for rate limiting/sessions
- `KAFKA_BOOTSTRAP_SERVERS`: Kafka for event publishing

## Development

```bash
# Run service
pdm run -p services/identity_service dev

# Tests
pdm run pytest services/identity_service/tests/

# Type check
pdm run mypy services/identity_service/
```
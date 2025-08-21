# Identity Service Missing Features & Architectural Fixes

## Executive Summary
The Identity Service is 65% complete with core authentication working but missing critical production features and has architectural violations that must be addressed.

## Critical Missing Features (Priority: URGENT)

### 1. Health Check Endpoint ❌
**Violation**: Rule 041 - Microservice Health Standards
**Required Path**: `/healthz`
**Implementation**:
- Create `api/health_routes.py`
- Check database connectivity
- Verify Kafka connection
- Return standardized health response

### 2. Refresh Token Endpoint ❌
**Required Path**: `/v1/auth/refresh`
**Functionality**:
- Exchange refresh token for new access token
- Validate refresh token JTI against session store
- Issue new access token with same claims
- Optional: Rotate refresh token

### 3. Logout/Signout Endpoint ❌
**Required Path**: `/v1/auth/logout`
**Functionality**:
- Invalidate refresh token
- Remove session from database
- Publish logout event
- Clear client-side tokens

### 4. Token Revocation Endpoint ❌
**Required Path**: `/v1/auth/revoke`
**Functionality**:
- Revoke specific tokens by JTI
- Support batch revocation
- Immediate effect on validation

## Architectural Violations (Priority: HIGH)

### 1. Not Using HuleEduApp Base Class ❌
**Current**: Plain Quart application
**Required**: Inherit from HuleEduApp
**Files to Update**:
- `app.py` - Migrate to HuleEduApp pattern
- Import from `huleedu_service_libs.app_base`

### 2. No Metrics Implementation ❌
**Required**: Prometheus metrics (Rule 071)
**Metrics Needed**:
- Authentication attempts/successes/failures
- Token issuance rate
- Password reset requests
- Response time histograms
- Active sessions gauge

### 3. Incomplete Error Handling ❌
**Required**: Rule 048 - Structured Error Handling
**Current Issues**:
- Inconsistent error responses
- Missing error factory usage in some endpoints
- No centralized error handler

## Security Enhancements (Priority: HIGH)

### 1. Rate Limiting ❌
**Required For**:
- Login attempts (5 per minute)
- Password reset requests (3 per hour)
- Registration (10 per hour)
**Implementation**: Use Redis-based rate limiter

### 2. Account Lockout ❌
**After**: 5 failed login attempts
**Duration**: 15 minutes
**Storage**: Database field for lockout timestamp

### 3. Token Introspection ❌
**Endpoint**: `/v1/auth/introspect`
**Purpose**: Validate token status for other services

### 4. Audit Logging ❌
**Events to Log**:
- All authentication attempts
- Password changes
- Permission changes
- Token revocations

## Implementation Details

### Health Check Implementation
```python
# api/health_routes.py
from quart import Blueprint, jsonify
from huleedu_service_libs.health import HealthStatus, create_health_response

bp = Blueprint("health", __name__)

@bp.get("/healthz")
async def health_check(db_session, kafka_producer):
    checks = {
        "database": await check_database(db_session),
        "kafka": await check_kafka(kafka_producer),
    }
    status = HealthStatus.HEALTHY if all(checks.values()) else HealthStatus.UNHEALTHY
    return create_health_response(status, checks)
```

### Refresh Token Endpoint
```python
# api/auth_routes.py
@bp.post("/refresh")
@inject
async def refresh_token(
    sessions: FromDishka[SessionRepo],
    tokens: FromDishka[TokenIssuer],
) -> Response:
    # Extract refresh token from request
    # Validate against session store
    # Issue new access token
    # Optional: Rotate refresh token
```

### Logout Endpoint
```python
# api/auth_routes.py
@bp.post("/logout")
@inject
async def logout(
    sessions: FromDishka[SessionRepo],
    event_publisher: FromDishka[IdentityEventPublisherProtocol],
) -> Response:
    # Extract token from Authorization header
    # Invalidate refresh token in session store
    # Publish logout event
    # Return success response
```

### HuleEduApp Migration
```python
# app.py
from huleedu_service_libs.app_base import HuleEduApp
from huleedu_service_libs.metrics import setup_metrics

app = HuleEduApp(__name__, "identity_service")
setup_metrics(app)

# Add health check blueprint
from services.identity_service.api import health_routes
app.register_blueprint(health_routes.bp)
```

## Database Schema Changes

### User Table Additions
```sql
ALTER TABLE users ADD COLUMN failed_login_attempts INT DEFAULT 0;
ALTER TABLE users ADD COLUMN locked_until TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP NULL;
ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP NULL;
```

### Audit Log Table
```sql
CREATE TABLE audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    action VARCHAR(50) NOT NULL,
    details JSONB,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Event Schema Additions

### New Events
1. **UserLoggedOutV1**
   - user_id
   - session_id
   - timestamp

2. **TokenRevokedV1**
   - token_jti
   - user_id
   - reason
   - timestamp

3. **AccountLockedV1**
   - user_id
   - reason
   - locked_until
   - timestamp

## Environment Variables

### New Required Variables
```bash
# Rate limiting
IDENTITY_RATE_LIMIT_ENABLED=true
IDENTITY_RATE_LIMIT_REDIS_URL=redis://localhost:6379

# Security
IDENTITY_MAX_LOGIN_ATTEMPTS=5
IDENTITY_LOCKOUT_DURATION_MINUTES=15
IDENTITY_PASSWORD_MIN_LENGTH=8
IDENTITY_PASSWORD_REQUIRE_SPECIAL=true

# Token settings
IDENTITY_ACCESS_TOKEN_EXPIRY_SECONDS=3600
IDENTITY_REFRESH_TOKEN_EXPIRY_SECONDS=86400
IDENTITY_REFRESH_TOKEN_ROTATION=true
```

## Migration Plan

### Phase 1: Critical Fixes (Week 1)
1. Add health check endpoint
2. Implement refresh token endpoint
3. Add logout endpoint
4. Migrate to HuleEduApp

### Phase 2: Security (Week 2)
1. Implement rate limiting
2. Add account lockout
3. Enhance audit logging
4. Add token introspection

### Phase 3: Observability (Week 3)
1. Add Prometheus metrics
2. Implement distributed tracing
3. Enhance error handling
4. Add performance monitoring

## Testing Requirements

### New Test Coverage Needed
- Health check endpoint tests
- Refresh token flow tests
- Logout functionality tests
- Rate limiting tests
- Account lockout tests
- Metrics collection tests
- Audit logging tests

## Acceptance Criteria

### Must Have (MVP)
- ✅ Health check endpoint responds correctly
- ✅ Refresh tokens can be exchanged
- ✅ Users can logout
- ✅ Service uses HuleEduApp
- ✅ Basic metrics exposed

### Should Have
- ✅ Rate limiting active
- ✅ Account lockout working
- ✅ Audit logs captured
- ✅ Token introspection available

### Nice to Have
- ✅ 2FA/MFA support
- ✅ OAuth2/OIDC providers
- ✅ Session management UI
- ✅ Password policy configuration

## Risk Assessment

### High Risk
- **No logout mechanism**: Sessions cannot be terminated
- **No refresh endpoint**: Forces frequent re-authentication
- **Missing health checks**: Cannot monitor service health
- **No rate limiting**: Vulnerable to brute force attacks

### Medium Risk
- **No audit logging**: Cannot track security events
- **No account lockout**: No protection against attacks
- **Missing metrics**: Cannot monitor performance

### Low Risk
- **No 2FA**: Reduced security for sensitive accounts
- **No OAuth**: Limited authentication options

## Dependencies

### External Services
- Redis (for rate limiting)
- Kafka (for event publishing)
- PostgreSQL (for data persistence)

### Internal Libraries
- huleedu_service_libs.app_base
- huleedu_service_libs.metrics
- huleedu_service_libs.health
- huleedu_service_libs.error_handling

## Estimated Effort

### Development Time
- Health check endpoint: 2 hours
- Refresh token endpoint: 4 hours
- Logout endpoint: 3 hours
- HuleEduApp migration: 2 hours
- Rate limiting: 6 hours
- Account lockout: 4 hours
- Metrics implementation: 4 hours
- Audit logging: 6 hours

**Total**: ~31 hours

### Testing Time
- Unit tests: 15 hours
- Integration tests: 10 hours
- E2E tests: 5 hours

**Total**: ~30 hours

**Grand Total**: ~61 hours (8-10 days)

---
*This document outlines all missing features and fixes required for production readiness*
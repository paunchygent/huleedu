# Identity Service Test Completion Task

## ULTRATHINK Analysis & Implementation Plan

### Service Assessment Summary
- **Completion Status**: 65% - Core authentication functional, missing critical production features
- **Test Coverage**: ~5% - Only 3 test files exist (profile-related)
- **Critical Gaps**: No health check, refresh token endpoint, logout, metrics
- **Architectural Violations**: Not using HuleEduApp, missing required endpoints

### Pre-Implementation Requirements (Rule 075)
1. ✅ Rule Compliance: Reviewed all mandatory architectural rules
2. ✅ Service Architecture: Identity service is HTTP service (Quart-based)
3. ✅ Domain Analysis: User authentication/security bounded context
4. ✅ Pattern Study: Analyzed existing service patterns
5. ⬜ Typecheck Validation: Run `pdm run typecheck-all` before each session
6. ✅ Behavior Analysis: Identified core behaviors and edge cases

### Battle-Tested Pattern Sources
- **HTTP Service Testing**: `/services/file_service/tests/api/`
- **Protocol-based DI Testing**: `/services/essay_lifecycle_service/tests/unit/`
- **Event Publishing Testing**: `/services/batch_conductor_service/tests/unit/`
- **Integration Testing**: `/services/class_management_service/tests/integration/`

## Test Coverage Gap Analysis

### Components with ZERO Tests (0% Coverage)

#### 1. API Routes (`api/auth_routes.py`)
- `/v1/auth/register` - User registration
- `/v1/auth/login` - User authentication
- `/v1/auth/me` - Current user info
- `/v1/auth/request-email-verification` - Email verification request
- `/v1/auth/verify-email` - Email verification completion
- `/v1/auth/request-password-reset` - Password reset request
- `/v1/auth/reset-password` - Password reset completion

#### 2. Well-Known Routes (`api/well_known_routes.py`)
- `/.well-known/jwks.json` - JWKS endpoint for token validation

#### 3. Implementations (11 classes total)
- `password_hasher_impl.py` - Argon2id password hashing
- `token_issuer_impl.py` - Development JWT issuer
- `token_issuer_rs256_impl.py` - Production RS256 JWT issuer
- `session_repository_postgres_impl.py` - Session management
- `user_repository_postgres_impl.py` - User data access
- `user_repository_sqlalchemy_impl.py` - SQLAlchemy user repo
- `event_publisher_impl.py` - Domain event publishing
- `jwks_store.py` - JWKS key management
- `outbox_manager.py` - Transactional outbox pattern

#### 4. Core Components
- `di.py` - Dependency injection container setup
- `config.py` - Service configuration
- `app.py` - Application initialization
- `startup_setup.py` - Startup/shutdown lifecycle

### Components with Partial Tests (30% Coverage)
- Profile functionality: 3 test files
  - `test_profile_handler_unit.py`
  - `test_profile_repository_unit.py`
  - `test_profile_routes_integration.py`

## Implementation Sessions

### SESSION 1: Authentication Foundation Tests
**Target**: 5 test files, ~400 LoC total
**Focus**: Core authentication endpoints and password hashing

#### Files to Create:
1. **test_auth_routes_register_unit.py** (~100 LoC)
   - User registration validation
   - Duplicate email handling
   - Event publishing verification
   - Swedish character support (åäöÅÄÖ)
   - Error response formatting

2. **test_auth_routes_login_unit.py** (~100 LoC)
   - Valid credentials authentication
   - Invalid email/password handling
   - Token pair generation
   - Session storage verification
   - Event publishing on success/failure

3. **test_password_hasher_unit.py** (~80 LoC)
   - Argon2id hash generation
   - Hash verification (correct/incorrect)
   - Empty password handling
   - Unicode password support
   - Hash format validation

4. **test_token_issuer_unit.py** (~100 LoC)
   - Access token generation
   - Refresh token generation
   - Token expiry validation
   - Claims verification
   - JTI uniqueness

5. **test_schemas_validation_unit.py** (~50 LoC)
   - Request schema validation
   - Response schema validation
   - Field constraints
   - Optional field handling

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/unit/test_auth* -v`

---

### SESSION 2: Repository & Data Access Tests
**Target**: 4 test files, ~450 LoC total
**Focus**: Data persistence and retrieval

#### Files to Create:
1. **test_user_repository_unit.py** (~150 LoC)
   - User creation
   - Get by email/ID
   - Duplicate email handling
   - Transaction rollback scenarios
   - Swedish character handling in names

2. **test_session_repository_unit.py** (~100 LoC)
   - Refresh token storage
   - Session retrieval
   - Session expiry handling
   - Session invalidation
   - Concurrent session management

3. **test_user_repository_sqlalchemy_unit.py** (~100 LoC)
   - SQLAlchemy-specific operations
   - Query optimization verification
   - Relationship loading
   - Batch operations

4. **test_database_models_unit.py** (~100 LoC)
   - Model field validation
   - Relationship constraints
   - Default values
   - Timestamp handling

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/unit/test_*repository* -v`

---

### SESSION 3: Security Flow Tests
**Target**: 4 test files, ~400 LoC total
**Focus**: Password reset and email verification

#### Files to Create:
1. **test_auth_routes_password_reset_unit.py** (~150 LoC)
   - Request reset (email non-disclosure)
   - Token generation and storage
   - Token expiry (1 hour)
   - Password update with valid token
   - Invalid/expired token handling

2. **test_auth_routes_email_verification_unit.py** (~100 LoC)
   - Verification request
   - Token generation
   - Email verification completion
   - Token reuse prevention
   - Expired token handling

3. **test_auth_routes_me_unit.py** (~50 LoC)
   - Current user retrieval
   - Token validation
   - Missing/invalid token handling

4. **test_well_known_routes_unit.py** (~100 LoC)
   - JWKS endpoint response
   - Key rotation support
   - Cache headers
   - Content-type validation

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/unit/test_auth_routes_* -v`

---

### SESSION 4: Event & Infrastructure Tests
**Target**: 5 test files, ~450 LoC total
**Focus**: Event publishing and system infrastructure

#### Files to Create:
1. **test_event_publisher_unit.py** (~150 LoC)
   - User registered event
   - Login succeeded/failed events
   - Password reset events
   - Event envelope construction
   - Correlation ID propagation

2. **test_outbox_manager_unit.py** (~100 LoC)
   - Transactional outbox pattern
   - Event persistence
   - Retry mechanism
   - Failed event handling
   - Batch processing

3. **test_jwks_store_unit.py** (~50 LoC)
   - Key generation
   - Key rotation
   - Public key export
   - Key ID management

4. **test_di_container_unit.py** (~100 LoC)
   - Provider configuration
   - Scope management
   - Dependency resolution
   - Mock injection for tests

5. **test_config_unit.py** (~50 LoC)
   - Environment variable loading
   - Default values
   - Validation rules
   - Secret masking

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/unit/test_event* test_di* test_config* -v`

---

### SESSION 5: Integration Tests
**Target**: 5 test files, ~500 LoC total
**Focus**: Component integration with real database

#### Files to Create:
1. **test_auth_flow_integration.py** (~150 LoC)
   - Complete registration → login flow
   - Token lifecycle
   - Profile creation
   - Event publishing verification

2. **test_password_reset_integration.py** (~100 LoC)
   - Request → verify → reset flow
   - Database state verification
   - Event emission
   - Token cleanup

3. **test_email_verification_integration.py** (~100 LoC)
   - Request → verify flow
   - User state updates
   - Token invalidation
   - Event publishing

4. **test_token_management_integration.py** (~100 LoC)
   - Token issuance → validation
   - Session management
   - Concurrent sessions
   - Token expiry handling

5. **test_event_publishing_integration.py** (~50 LoC)
   - Outbox pattern verification
   - Event ordering
   - Retry mechanism
   - Failure handling

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/integration/ -v`

---

### SESSION 6: Contract & E2E Tests
**Target**: 4 test files, ~350 LoC total
**Focus**: API contracts and end-to-end scenarios

#### Files to Create:
1. **test_identity_event_contracts.py** (~100 LoC)
   - UserRegisteredV1 schema
   - LoginSucceededV1 schema
   - PasswordResetRequestedV1 schema
   - Event envelope format

2. **test_api_response_contracts.py** (~100 LoC)
   - RegisterResponse schema
   - TokenPair schema
   - Error response format
   - HTTP status codes

3. **test_jwt_token_contracts.py** (~100 LoC)
   - JWT structure validation
   - Required claims
   - Signature verification
   - Expiry validation

4. **test_auth_e2e.py** (~50 LoC)
   - Full user journey
   - Cross-service event flow
   - Performance boundaries
   - Swedish locale support

**Validation**: `pdm run typecheck-all && pdm run pytest services/identity_service/tests/ -v`

---

## Critical Success Metrics

### Per Session Requirements
- ✅ 100% test pass rate before proceeding
- ✅ Zero type errors from `typecheck-all`
- ✅ Root cause analysis for any failures
- ✅ Behavioral verification (not implementation testing)
- ✅ Test files under 500 LoC limit

### Anti-Patterns to Avoid
- ❌ Testing log messages or internal mechanics
- ❌ Simplifying tests to make them pass
- ❌ Large monolithic test files
- ❌ Skipping domain-specific edge cases
- ❌ Mocking at wrong abstraction levels

### Domain-Specific Test Cases
- Swedish characters in names (åäöÅÄÖ)
- Email format validation
- Password complexity requirements
- Token expiry boundaries
- Concurrent session handling
- Security non-disclosure patterns

## Test Execution Commands

```bash
# Run all identity service tests
pdm run pytest services/identity_service/tests/ -v

# Run specific test category
pdm run pytest services/identity_service/tests/unit/ -v
pdm run pytest services/identity_service/tests/integration/ -v

# Run with coverage
pdm run pytest services/identity_service/tests/ --cov=services/identity_service --cov-report=term-missing

# Type checking
pdm run typecheck-all

# Run specific test file
pdm run pytest services/identity_service/tests/unit/test_auth_routes_login_unit.py -v
```

## Progress Tracking

### Session 1: ⬜ Authentication Foundation (0/5 files)
### Session 2: ⬜ Repository & Data Access (0/4 files)
### Session 3: ⬜ Security Flows (0/4 files)
### Session 4: ⬜ Event & Infrastructure (0/5 files)
### Session 5: ⬜ Integration Tests (0/5 files)
### Session 6: ⬜ Contract & E2E (0/4 files)

**Total Progress**: 3/30 test files completed (~10%)

## Next Steps
1. Begin Session 1 with `test_password_hasher_unit.py` (simplest)
2. Use battle-tested patterns from existing services
3. Validate with typecheck-all after each file
4. Update progress tracking after each session
5. Document any discovered issues for bug fixes

---
*This task follows Rule 075: Test Creation Methodology with ULTRATHINK protocol*
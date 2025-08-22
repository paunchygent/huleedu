Identity Service Session 7: E2E Test Implementation

## Session Context

You are continuing the Identity Service test completion initiative. Previous sessions have completed:
- Session 1-3: All 23 unit test files (511 tests passing)
- Session 4: Bug fixes and infrastructure setup
- Session 5: All 3 contract test files (43 tests passing)
- Session 6: Code quality - Enum refactoring (LoginFailureReason)

## Your Mission for Session 7

Create comprehensive end-to-end tests for the Identity Service that validate complete user journeys with real infrastructure.

## Pre-Session Checklist

1. Run `pdm run typecheck-all` to ensure clean starting state
2. Start Docker services: `pdm run dev dev identity_service`
3. Verify services are running: `docker ps | grep huleedu`
4. Read task document: `TASKS/IDENTITY_SERVICE_TEST_COMPLETION.md` (Session 7 Planning section)

## CRITICAL ARCHITECTURAL REQUIREMENTS

### 1. Test Placement - IMPORTANT CHANGE!

**Location**: `/tests/functional/test_identity_service_e2e.py` (NOT in services/identity_service/tests/)

This follows the established monorepo pattern where ALL E2E tests are at root level.

### 2. Required Test Scenarios

**Test Class**: `TestIdentityServiceE2E`

1. **Complete User Lifecycle**: Registration → Email Verification → Login → Session → Logout
2. **Token Management Flow**: Login → Refresh → Revoke → Expiry  
3. **Password Reset Journey**: Request → Verify → Reset → Login
4. **Security and Rate Limiting**: Failed Attempts → Lockout → Recovery

### 3. Infrastructure Approach - USE DOCKER COMPOSE

**DO NOT use testcontainers!** Use the running Docker Compose services:
- Identity Service (Port 8100)
- PostgreSQL (huleedu_identity_db)
- Redis (Port 6379)
- Kafka (Port 9093)

### 4. MANDATORY Test Utilities - USE EXISTING!

**DO NOT create identity_e2e_utils.py!** Use these existing utilities:

- `tests/utils/service_test_manager.py` - ServiceTestManager for HTTP interactions
- `tests/utils/kafka_test_manager.py` - KafkaTestManager for event verification
- `tests/utils/auth_manager.py` - AuthTestManager for JWT handling
- `tests/utils/database_manager.py` - For database verification if needed

### 5. Critical Patterns to Follow

1. **Setup Kafka consumers BEFORE triggering actions** (avoid race conditions)
2. **Use correlation IDs consistently** for event tracking
3. **Verify both HTTP responses AND async events**
4. **Use clean_distributed_state fixture** for test isolation
5. **Test Swedish characters** (åäöÅÄÖ) in all text fields
6. **Follow patterns from** `test_e2e_comprehensive_real_batch_guest_flow.py`

### 6. Event Verification

Monitor these Kafka topics using KafkaTestManager:
- huleedu.identity.user.registered.v1
- huleedu.identity.login.succeeded.v1
- huleedu.identity.login.failed.v1
- huleedu.identity.email.verified.v1
- huleedu.identity.password.reset.requested.v1
- huleedu.identity.password.reset.completed.v1

### 7. Database Verification

For PostgreSQL state checks:
- Access via existing database connection from Docker services
- Use raw SQL queries or SQLAlchemy models as appropriate
- Database name: `huleedu_identity`

## Success Criteria

- All 4 test scenarios pass with Docker Compose infrastructure
- Events published in correct order with correct payloads
- Database state verified after each operation
- Redis session/rate limit state verified
- Token validation works across service boundaries
- Swedish character handling works correctly
- Tests use ONLY existing utilities (no new utility files)

## Commands to Use

### Start Services

```bash
# Start full stack INCLUDING Identity Service
pdm run dev dev identity_service

# Verify services are running
docker ps | grep huleedu
```

### Run E2E Tests

```bash
# Run the Identity E2E test from repository root
pdm run pytest tests/functional/test_identity_service_e2e.py -v

# With markers
pdm run pytest tests/functional/ -k "identity" -m "e2e" -v
```

### Verify Results

```bash
# Check all tests pass
pdm run test-all

# Type checking
pdm run typecheck-all
```

## Reference Files - MUST STUDY

These are your templates - follow their patterns exactly:
- `tests/functional/test_e2e_comprehensive_real_batch_guest_flow.py` - E2E pattern
- `tests/functional/test_e2e_full_batch_pipeline.py` - Event verification pattern
- `tests/utils/service_test_manager.py` - HTTP interaction pattern
- `tests/utils/kafka_test_manager.py` - Kafka consumer pattern

## Important Implementation Notes

1. **Location is critical**: Test MUST be in `/tests/functional/` not in service directory
2. **Use existing utilities**: DO NOT create new utility files
3. **Docker Compose only**: NO testcontainers - use running services
4. **Follow existing patterns**: Study the reference files carefully
5. **Resource management**: Use fixtures for proper cleanup

## Begin Implementation

Start by:
1. Study `test_e2e_comprehensive_real_batch_guest_flow.py` for the pattern
2. Create `/tests/functional/test_identity_service_e2e.py`
3. Import and use existing utilities from `tests/utils/`
4. Implement all 4 test scenarios following established patterns
# Entitlements Service Test Coverage Implementation Plan

## Executive Summary

**Purpose**: Implement comprehensive test coverage for entitlements service to achieve 85% coverage following HuleEdu's parallel test creation methodology and architectural standards.

**Current Status**: Core units and routes are covered; mypy clean across repo; BOS preflight + Gateway 402 tests added
**Target**: ≥85% coverage with integration across AGW, BOS, Entitlements and end-to-end functional validation

**Integration**: Validates core credit management, org-first identity attribution, ResourceConsumptionV1 processing, and event-driven patterns per Rule 020.17.

## Session Progress Update (2025-09-06)

### ✅ **Phase 0: Service Health Restoration - COMPLETE**
- Entitlements service restarted successfully
- Health check endpoint returns 200 (healthy)
- Kafka consumer reconnected and processing events
- Docker container status: huleedu_entitlements_service (healthy)

### 📊 **Current Test Coverage Analysis**
```
Current Coverage: 33% (648 total statements, 433 missed)

Critical Gaps:
- app.py: 0% (89 statements missed)
- config.py: 0% (29 statements missed)  
- di.py: 0% (90 statements missed)
- models_db.py: 0% (57 statements missed)
- metrics.py: 0% (22 statements missed)
- credit_manager_impl.py: 52% (59 statements missed)
- kafka_consumer.py: 55% (30 statements missed)
- repository_impl.py: Not tested (estimated 0%)
- event_publisher_impl.py: Not tested (estimated 0%)
- rate_limiter_impl.py: Not tested (estimated 0%)
- policy_loader_impl.py: Not tested (estimated 0%)
```

### 🔧 **Issues to Resolve / Align**
- Entitlements API currently supports single-metric checks; BOS preflight can produce multi-resource requirements (cj_comparison + ai_feedback_generation)
  - Option A (preferred): Add `POST /v1/entitlements/check-credits/bulk` with `{ requirements: { metric: quantity } }`
  - Option B: BOS loops single checks per metric and aggregates results
- Add BOS preflight route tests (done) and expand to include Swedish identity cases and org-first attribution

## Test Creation Strategy: Parallel Methodology (Rule 075.1)

### **Phase 0: Foundation & Fast Wins**
**Status**: In Progress
- Keep repo-wide type checks at zero errors (done)
- Targeted unit tests added:
  - BOS: preflight route (allowed/denied/invalid) — done
  - AGW: preflight denial returns 402 — done
  - Entitlements: route tests and DI provision tests — present and typed

### **Phase 1: Core Business Logic** (Batch 1)
**Status**: Planned
**Coverage Target**: +15–20%

Launch 3 parallel test-engineer agents:
1. **test_repository_impl.py** (0% → 90%)
   - EntitlementsRepositoryImpl database operations
   - Credit balance operations, audit trails, transactions
   - Swedish character handling (åäöÅÄÖ) in user/org IDs
   - Idempotency and constraint violations
   
2. **test_event_publisher_impl.py** (0% → 90%)
   - EventPublisherImpl outbox pattern implementation
   - Event serialization and reliability guarantees
   - CreditBalanceChangedV1, RateLimitExceededV1, UsageRecordedV1
   - Error scenarios and retry mechanisms
   
3. **test_rate_limiter_impl.py** (0% → 90%)
   - RateLimiterImpl sliding window calculations
   - Redis operations and caching behavior
   - Concurrent request handling and race conditions
   - Threshold enforcement and limit exceeded scenarios

### **Phase 2: Service Infrastructure** (Batch 2)
**Status**: Planned
**Coverage Target**: +15–20%

Launch 3 parallel test-engineer agents:
1. **test_policy_loader_impl.py** (0% → 90%)
   - PolicyLoaderImpl YAML loading and validation
   - Redis caching behavior and invalidation
   - Cost calculations for different metrics
   - Configuration error handling
   
2. **test_health_routes.py** (new file)
   - Health endpoint DB + Kafka component checks
   - Component state monitoring and failure detection
   - Health check failure scenarios and recovery
   - Integration with EntitlementsKafkaConsumer status
   
3. **test_entitlements_routes.py** (new file)
   - API endpoints: check_credits, consume_credits, get_balance
   - Request/response validation and serialization
   - Authentication and authorization patterns
   - Error handling and status codes

### **Phase 3: Integration Layer** (Batch 3)
**Status**: Planned
**Coverage Target**: +15%

Launch 3 parallel test-engineer agents:
1. **test_di_setup.py** (0% → 85%)
   - Dishka provider configurations and scopes
   - APP vs REQUEST scope management
   - Component wiring and dependency resolution
   - Mock injection for testing scenarios
   
2. **test_config.py** (0% → 90%)
   - Environment variable loading and validation
   - Configuration defaults and precedence rules
   - Database URL construction and validation
   - Redis connection string handling
   
3. **test_startup_setup.py** (new file)
   - Service initialization and startup sequence
   - EntitlementsKafkaConsumer lifecycle management
   - Graceful shutdown handling and cleanup
   - Component initialization order and dependencies

### **Phase 4: Data Models & App** (Batch 4)
**Status**: Planned
**Coverage Target**: reach ≥85%

Launch 2 parallel test-engineer agents:
1. **test_models_db.py** (0% → 85%)
   - SQLAlchemy model validation and constraints
   - ConsumptionRecord, CreditBalance model behavior
   - Relationship mappings and foreign keys
   - Database constraint enforcement
   
2. **test_app.py** (0% → 75%)
   - Quart application setup and configuration
   - Blueprint registration and routing
   - Middleware configuration and error handlers
   - CORS and security headers

## Quality Gates & Validation (Per Rule 075.1)

### **User's Test Quality Standards**
- **MANDATORY**: Modern test framework without conftest files
- **EXPLICIT IMPORTS**: Use utils that are imported in tests explicitly
- **SERVICE EMULATION**: Tests must emulate real services, not mock implementations
- **NO SLOPPY VIBE-CODING**: Everything according to established patterns and architecture
- **FORBIDDEN**: Improvisation and makeshift solutions

### **Rule 075 Test Quality Requirements**

#### **Forbidden Practices** 
- **FORBIDDEN**: Creating large monolithic test files (>500 LoC hard limit)
- **FORBIDDEN**: Testing implementation details instead of behavior
- **FORBIDDEN**: Skipping `typecheck-all` validation
- **FORBIDDEN**: Accepting test failures without root cause analysis
- **FORBIDDEN**: Using `try/except pass` blocks hiding issues
- **FORBIDDEN**: Simplifying tests to make them pass
- **FORBIDDEN**: Mocking at wrong abstraction levels
- **FORBIDDEN**: Ignoring domain-specific edge cases (Swedish characters for HuleEdu)

#### **Mandatory Patterns**
- **MUST**: Use `@pytest.mark.parametrize` for comprehensive coverage
- **MUST**: Test actual behavior and side effects, not implementation details
- **MUST**: Include Swedish characters (åäöÅÄÖ) in identity-related tests
- **MUST**: Write clear, business-focused test descriptions
- **MUST**: Use protocol-based mocking with AsyncMock(spec=Protocol)
- **MUST**: Override Dishka providers to inject mocks (no @patch usage)

### **Mandatory Post-Batch Protocol**
1. **Test Execution**: `pdm run pytest [batch_files] -v` → 100% pass rate required
2. **Architect Review**: Launch lead-architect-planner agent for quality validation
3. **Type Safety**: `pdm run typecheck-all` → zero errors required
4. **DI Compliance**: `grep -r "@patch|mock\.patch"` → zero results required
5. **Rule 075 Compliance**: <500 LoC per file, behavioral testing focus

### **Implementation Bug Protocol**
- Tests may reveal implementation bugs vs test issues
- Priority: Fix implementation first, validate tests second
- Use architect agent for root cause analysis before fixes
- Re-run tests after implementation fixes

## Key Testing Requirements (Rule 020.17 Compliance)

### **Identity Threading Tests**
- Org-first, user-fallback credit attribution logic
- ResourceConsumptionV1 processing with identity validation
- Swedish character handling in all identity scenarios

### **Event Contract Tests**
- ResourceConsumptionV1 serialization/deserialization
- EventEnvelope integration with metadata
- Cross-service event compatibility validation

### **Error Scenario Coverage**
- Network failures and connection timeouts
- Database constraints and transaction rollbacks
- Insufficient credit and rate limit scenarios
- Malformed event handling and validation errors

### **Idempotency Testing**
- Duplicate ResourceConsumptionV1 event handling
- Event-id based deduplication validation
- No double-charging on retry scenarios

## Expected Coverage Progression

```
Phase 0: 33% → 35% (fix broken test)
Phase 1: 35% → 50% (core implementations - 3 files)
Phase 2: 50% → 65% (service layer - 3 files)  
Phase 3: 65% → 78% (infrastructure - 3 files)
Phase 4: 78% → 85%+ (models & app - 2 files)
```

## Success Criteria

### **Coverage Metrics**
- ✅ 85% overall code coverage achieved
- ✅ All critical implementation classes >85% coverage
- ✅ All tests pass (100% pass rate)
- ✅ Zero mypy errors on `pdm run typecheck-all`

### **Architectural Compliance**
- ✅ Rule 075 behavioral testing patterns followed
- ✅ No @patch usage (proper DI mocking)
- ✅ Swedish character edge cases tested where applicable
- ✅ Protocol-based testing for all dependencies

### **Integration Validation (Targeted Next Steps)**
- BOS preflight end-to-end via AGW
  - Test: AGW preflight → 402 returns structured denial (Swedish IDs, org-first)
  - Test: AGW preflight → 202; then BOS publishes command
- Runtime denial path
  - Simulate credits changed after preflight → BOS publishes `PipelineDeniedV1`; WebSocket notification projected
- Resource consumption path
  - CJ/other services publish `ResourceConsumptionV1` → Entitlements consumes and emits `CreditBalanceChangedV1`
  - Verify outbox relay publishes to Kafka
- Idempotency and tracing
  - Duplicate events ignored; correlation IDs propagated across boundaries (headers + envelopes)

## Execution & Tooling

- Use `pdm run pytest-root` to target service suites:
  - `pdm run pytest-root services/api_gateway_service/tests`
  - `pdm run pytest-root services/batch_orchestrator_service/tests`
  - `pdm run pytest-root services/entitlements_service/tests`
- Functional E2E harness (root tests/functional):
  - Add scenarios covering: preflight 402 path, happy-path 202 + pipeline finish, runtime denial, and consumption
  - Reuse common JWT utilities and identity fixtures; include Swedish characters in identities
  - Ensure org-first attribution in assertions and that correlation IDs are consistent
  - Validate WebSocket projection by consuming TeacherNotificationRequestedV1 (or via API where applicable)

---

**This plan is up to date with BOS preflight + AGW 402 handling and defines concrete next steps for cross-service integration and functional E2E tests.**

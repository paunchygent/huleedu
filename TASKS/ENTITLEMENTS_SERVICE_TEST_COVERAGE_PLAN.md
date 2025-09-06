# Entitlements Service Test Coverage Implementation Plan

## Executive Summary

**Purpose**: Implement comprehensive test coverage for entitlements service to achieve 85% coverage following HuleEdu's parallel test creation methodology and architectural standards.

**Current Status**: Service is healthy (recently restarted), 88 tests pass, 1 fails, 33% coverage
**Target**: 85% coverage with full architectural compliance and test reliability

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

### 🔧 **Issues to Fix**
- `test_event_validation_error_handling` fails due to incorrect ResourceConsumptionV1 schema usage
- Need tests for all implementation classes following Rule 075 standards

## Test Creation Strategy: Parallel Methodology (Rule 075.1)

### **Phase 0: Fix Breaking Test** 
**Status**: PENDING
- Fix `test_event_validation_error_handling` 
- Root cause: Uses old event format instead of ResourceConsumptionV1 schema
- Expected: 33% → 35% coverage

### **Phase 1: Core Business Logic** (Batch 1)
**Status**: PENDING
**Coverage Target**: 35% → 50%

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
**Status**: PENDING
**Coverage Target**: 50% → 65%

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
**Status**: PENDING
**Coverage Target**: 65% → 78%

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
**Status**: PENDING
**Coverage Target**: 78% → 85%+

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

### **Integration Validation**
- ✅ ResourceConsumptionV1 processing end-to-end tested
- ✅ Event publishing with outbox pattern validated
- ✅ Health monitoring and component status checks working
- ✅ Identity threading (org-first) logic fully validated

## Timeline & Execution

**Estimated Duration**: ~85 minutes total
- Phase 0: 5 minutes (single fix)
- Phases 1-4: 20 minutes per batch (parallel execution)
- Validation: 10 minutes between phases

**Agent Coordination**: Use Task tool with test-engineer subagent_type for all batch executions, lead-architect-planner for post-batch reviews.

---

**This plan ensures the entitlements service achieves production-ready test coverage following established HuleEdu architectural patterns and parallel test creation methodology.**
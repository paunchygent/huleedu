---
id: 'ENTITLEMENTS_SERVICE_TEST_COVERAGE_PLAN'
title: 'Entitlements Service — Test Coverage Plan (Final)'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2025-09-08'
last_updated: '2025-11-17'
related: []
labels: []
---
# Entitlements Service — Test Coverage Plan (Final)

## Goals

- ≥85% coverage with emphasis on behavioral tests, contracts, and cross-service flows.
- Validate 200/402/429 preflight semantics, org-first selection, per-metric rate limits, correlation threading, and Swedish identity handling.

## Functional E2E Scenarios

- AGW preflight denial 402: AGW → BOS preflight → Entitlements bulk returns 402 with breakdown and correlation threading.
- AGW preflight rate-limit 429: User-scoped RL violation yields 429; metrics incremented; correlation preserved.
- AGW preflight accepted 202: On 200 from BOS, AGW publishes `ClientBatchPipelineRequestV1` and returns 202.
- Runtime denial: Credits change after preflight → BOS publishes `PipelineDeniedV1` with denial_reason and breakdown.
- Consumption flow: Processing publishes `ResourceConsumptionV1` → Entitlements debits and relays `CreditBalanceChangedV1` via outbox.

## Contract Tests

- BulkCreditCheckRequestV1/BulkCreditCheckResponseV1 round-trip (common_core) including `per_metric` map, denial_reason, source.
- BOS preflight mapping contract: Ensure 1:1 mapping of Entitlements bulk response to BOS preflight payload and status codes.
- Correlation propagation: Header → BOS → Entitlements body; persisted in responses/events.
- Identity edge cases: Swedish characters in `user_id` / `org_id` across contracts.

## Integration Tests

- BOS domain: `PipelineCreditGuard` computes requirements and interprets bulk responses (allowed/insufficient/rl) with correct totals for pairwise CJ and linear feedback.
- BOS route: `/internal/v1/.../preflight` returns 200/402/429 and threads correlation.
- Entitlements route: `/v1/entitlements/check-credits/bulk` returns correct codes and `per_metric` statuses.

## Unit Tests (Targeted)

- Rate limiter: user-scoped metric windows; limit exceeded → publish RL event; allow when under threshold.
- Policy loader: YAML → cache; costs 0 for free ops; TTL respected.
- Credit manager: org-first selection; aggregate totals; per-metric RL short-circuit; advisory-only returns.
- Routes: Validation errors 422; happy paths and denial paths; Swedish identities accepted.

## Observability

- Metrics: counters for preflight outcomes (allowed, insufficient_credits, rate_limit_exceeded) at AGW and BOS.
- Logs: include `correlation_id`, `user_id`, `org_id`, `denial_reason` for preflight and consumption.

## Commands

- Run typecheck: `pdm run typecheck-all`
- Targeted tests: `pdm run pytest-root services/batch_orchestrator_service/tests` etc.
- Functional (docker): `pdm run pytest-root tests/functional -m 'docker'`

---

# Test Implementation Specifications

## 1. Functional E2E Tests (tests/functional/)

### test_e2e_credit_preflight_denial_402.py

**Purpose**: Validate 402 insufficient credits flow through AGW → BOS → Entitlements

**Test Methods**:

- `test_insufficient_credits_org_exhausted()`
  - Setup: Org with 10 credits, batch needs 1770 (60 essays)
  - Execute: POST /v1/batches/{id}/pipelines via AGW
  - Validate: 402 response with required_credits, available_credits, correlation_id
  
- `test_insufficient_credits_user_fallback()`
  - Setup: No org_id, user has 50 credits, need 435 (30 essays)
  - Execute: Pipeline request via AGW with user-only JWT
  - Validate: 402 with user-scoped denial and proper field mapping

- `test_swedish_identity_credit_denial()`
  - Setup: User "ANVÄNDARE_ÅÄÖ_901", org "ORGANISATION_ÅÄÖ_234"
  - Execute: Credit check with maximum Swedish characters
  - Validate: Identity preserved in response and audit trails

- `test_large_batch_credit_calculation()`
  - Setup: 60 essays batch, credits = 1769 (need 1770)
  - Execute: Pipeline request with CJ assessment
  - Validate: Exact calculation 60*(60-1)/2 = 1770 comparisons

**Fixtures Required**:

```python
@pytest.fixture
async def service_manager() -> ServiceTestManager
@pytest.fixture 
async def auth_manager() -> AuthManager
@pytest.fixture
async def kafka_manager() -> KafkaTestManager
```

**Test Utilities Pattern**:

```python
# Use ServiceTestManager for AGW registration (not direct BOS)
batch_response = await service_manager.register_batch_via_agw(
    headers={"Authorization": f"Bearer {token}"},
    file_content=create_test_essays(60),
    class_id="klass_7b_göteborg"
)

# Setup credits via admin endpoint
await service_manager.http_request(
    service="entitlements_service",
    method="POST", 
    path="/v1/admin/credits/set",
    json={"subject_type": "org", "subject_id": org_id, "balance": 10}
)
```

### test_e2e_credit_preflight_rate_limit_429.py

**Purpose**: Validate 429 rate limit exceeded scenarios

**Test Methods**:

- `test_per_metric_rate_limit_exceeded()` - Single metric RL violation
- `test_concurrent_requests_rate_limit()` - Multiple requests hit RL
- `test_rate_limit_with_swedish_identities()` - RL with Swedish chars

### test_e2e_credit_preflight_success_202.py  

**Purpose**: Validate successful preflight → pipeline execution

**Test Methods**:

- `test_sufficient_credits_org_first()` - Org has credits, success flow
- `test_sufficient_credits_user_fallback()` - User fallback success
- `test_pipeline_initiation_after_preflight()` - Verify ClientBatchPipelineRequestV1

### test_e2e_runtime_credit_denial.py

**Purpose**: Validate runtime denial when credits change after preflight

**Test Methods**:

- `test_credits_reduced_after_preflight()` - Credit balance changes
- `test_pipeline_denied_event_published()` - Verify PipelineDeniedV1 event
- `test_notification_projection_triggered()` - WebSocket notification

### test_e2e_resource_consumption_flow.py

**Purpose**: Validate ResourceConsumptionV1 → CreditBalanceChangedV1 flow

**Test Methods**:

- `test_cj_consumption_to_balance_change()` - CJ phase completion
- `test_ai_feedback_consumption_flow()` - AI feedback completion  
- `test_outbox_relay_reliability()` - Outbox pattern verification

**Event Verification Pattern**:

```python
# Subscribe to output topic
await kafka_manager.subscribe(["huleedu.entitlements.credit_balance_changed.v1"])

# Publish consumption event
await kafka_manager.publish(
    topic="huleedu.resource.consumption.v1",
    event=create_consumption_event(...)
)

# Wait for balance change
balance_event = await kafka_manager.wait_for_event(
    topic="huleedu.entitlements.credit_balance_changed.v1",
    condition=lambda e: e["data"]["subject"]["id"] == org_id
)
```

## 2. Integration Tests (tests/integration/)

### test_agw_bos_entitlements_integration.py

**Purpose**: Cross-service communication without Docker

**Test Methods**:

- `test_preflight_request_flow()` - Mock-based flow testing
- `test_denial_propagation()` - Error propagation through layers
- `test_field_mapping_integrity()` - Response field consistency

**Mock Pattern**:

```python
@pytest.fixture
def mock_entitlements_client():
    client = AsyncMock(spec=EntitlementsServiceClient)
    client.check_credits_bulk.return_value = {
        "allowed": False,
        "denial_reason": "insufficient_credits",
        "required_credits": 300,
        "available_credits": 10
    }
    return client
```

### test_correlation_id_threading.py

**Purpose**: Validate correlation ID propagation

**Test Methods**:

- `test_header_to_response_threading()` - HTTP header → response
- `test_event_envelope_correlation()` - Events preserve correlation_id
- `test_audit_trail_correlation()` - Database records include correlation_id

### test_credit_consumption_idempotency.py

**Purpose**: Validate duplicate event handling

**Test Methods**:

- `test_duplicate_event_handling()` - Same event_id ignored
- `test_no_double_charging()` - Credits not double-deducted
- `test_idempotency_key_management()` - Redis idempotency keys

## 3. Contract Tests (service-specific)

### services/entitlements_service/tests/contract/test_bulk_credit_check_contract.py

**Purpose**: Validate bulk DTO contracts

**Test Methods**:

- `test_request_dto_serialization()` - BulkCreditCheckRequestV1 roundtrip
- `test_response_per_metric_structure()` - per_metric field validation
- `test_denial_reason_enums()` - Valid denial_reason values

### services/batch_orchestrator_service/tests/contract/test_preflight_response_contract.py

**Purpose**: Validate BOS preflight response format

**Test Methods**:

- `test_field_mapping_consistency()` - Entitlements → BOS field mapping
- `test_status_code_alignment()` - 200/402/429 alignment
- `test_correlation_id_preservation()` - correlation_id threading

### services/common_core/tests/contract/test_entitlements_models_contract.py

**Purpose**: Validate shared DTO models

**Test Methods**:

- `test_bulk_dto_roundtrip()` - Serialization/deserialization
- `test_resource_consumption_event_schema()` - Event schema validation

## Test Setup & Execution

### Prerequisites

```bash
# Start all services
pdm run up

# Verify service health
pdm run pytest-root tests/functional/test_service_health.py

# Source environment
source .env
```

### Test Execution Commands

```bash
# Unit tests (service-specific)
pdm run pytest-root services/entitlements_service/tests/unit

# Contract tests
pdm run pytest-root services/entitlements_service/tests/contract

# Integration tests (no Docker)
pdm run pytest-root tests/integration -k "credit"

# Functional E2E tests (Docker required)
pdm run pytest-root tests/functional -m docker -k "credit_preflight"

# Full credit test suite
pdm run pytest-root tests/ -k "credit" --tb=short
```

### Test Data Specifications

#### Swedish Identity Test Cases

```python
SWEDISH_TEST_IDENTITIES = [
    ("lärare_åsa_123", "skola_örebro_456"),
    ("pedagog_örjan_789", "gymnasium_älvsjö_012"),
    ("ANVÄNDARE_ÅÄÖ_901", "ORGANISATION_ÅÄÖ_234"),
]

CREDIT_SCENARIOS = {
    "small_batch": {"essays": 10, "cj_comparisons": 45},
    "medium_batch": {"essays": 30, "cj_comparisons": 435}, 
    "large_batch": {"essays": 60, "cj_comparisons": 1770},
}
```

## Validation Criteria

### Each Test Must Validate

1. **Correlation ID Threading**: Request header → Response → Events
2. **Swedish Character Preservation**: åäöÅÄÖ handled correctly
3. **Field Completeness**: All required response fields present
4. **Performance Benchmarks**: Preflight <100ms, consumption <500ms
5. **Observability**: Metrics incremented, logs contain correlation_id

### Success Metrics

- **Response Time**: AGW preflight requests complete <100ms
- **Event Latency**: ResourceConsumptionV1 → CreditBalanceChangedV1 <1s
- **Error Rates**: Zero unhandled exceptions in preflight flow
- **Data Integrity**: Swedish characters preserved in all flows

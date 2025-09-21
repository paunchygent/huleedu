# Entitlements Service — Final Implementation Reference

## Executive Summary
- Purpose: Central authority for credit policies and accounting with org-first identity attribution. Provides advisory preflight and post-usage consumption.
- Scope: Bulk credit preflight authority for BOS; credit consumption via events; per-metric rate limits; no holds at preflight.
- Interfaces: HTTP bulk preflight; HTTP consumption; Kafka events for consumption and balance changes.

## Final Architecture
- Pattern: Quart HTTP + DI (Dishka), SQLAlchemy async, Redis (rate limits + policy cache), transactional outbox → Kafka.
- Identity: org-first selection; fallback to user. Both ids preserved on records for audit.
- Boundaries:
  - BOS computes resource requirements and calls Entitlements bulk preflight.
  - Entitlements is the policy authority; BOS never mutates balances.
  - Consumption is post-usage via ResourceConsumptionV1 events.
- Service structure: see `services/entitlements_service/` (api, implementations, protocols, di, policies).

## Key APIs
- Entitlements: `POST /v1/entitlements/check-credits/bulk`
  - Request: `{ user_id: str, org_id?: str, requirements: { [metric]: int }, correlation_id?: str }`
  - Responses:
    - 200 allowed: `{ allowed: true, required_credits, available_credits, per_metric, correlation_id }`
    - 402 insufficient: `{ allowed: false, denial_reason: "insufficient_credits", required_credits, available_credits, per_metric, correlation_id }`
    - 429 rate-limit: `{ allowed: false, denial_reason: "rate_limit_exceeded", required_credits, available_credits: 0, per_metric, correlation_id }`
  - Source: `services/entitlements_service/api/entitlements_routes.py` → `check_credits/bulk`

- BOS Preflight: `POST /internal/v1/batches/{batch_id}/pipelines/{phase}/preflight`
  - Returns 200/402/429 mirroring Entitlements outcomes; includes required/available and resource_breakdown.
  - Source: `services/batch_orchestrator_service/api/batch_routes.py` → `preflight_pipeline()`

- Consumption: `POST /v1/entitlements/consume-credits` (optimistic, post-usage)
  - Request: `{ user_id, org_id?, metric, amount, batch_id?, correlation_id }`
  - Source: `services/entitlements_service/api/entitlements_routes.py`

## Policies
- Org-First Selection: Evaluate org balance first when `org_id` is present; fallback to user if org cannot cover total requirement.
- Per-Metric Rate Limits: Apply per-user metric limits before credit availability. Any violation yields 429 with `denial_reason="rate_limit_exceeded"` and zero available_credits.
- Costs & Limits: Defined in `services/entitlements_service/policies/default.yaml`.
- Cache: Policy loader caches values in Redis; TTL from policy.

## Events
- Post-usage consumption: `ResourceConsumptionV1` → Entitlements consumer debits and publishes outbox events.
- Balance changes: `CreditBalanceChangedV1` (outbox → Kafka); RL notifications: `RateLimitExceededV1`.
- Runtime denial: BOS publishes `PipelineDeniedV1` on start-time denial (credits changed after preflight).
- Contracts: `libs/common_core/src/common_core/events/*.py` and `libs/common_core/src/common_core/entitlements_models.py`.

## Data Model
- `credit_balances(subject_type, subject_id, balance, timestamps)` composite PK `(subject_type, subject_id)`.
- `credit_operations(id, subject_type, subject_id, metric, amount, batch_id, consumed_from, correlation_id, status, created_at)` for audit.
- `event_outbox(id, aggregate_type, aggregate_id, event_type, event_data, topic, created_at, published_at)`.
- Implemented via async SQLAlchemy; repository encapsulates all writes.

## Current Service Structure
- HTTP: `services/entitlements_service/api/entitlements_routes.py`
- Business logic: `services/entitlements_service/implementations/credit_manager_impl.py`
- Protocols: `services/entitlements_service/protocols.py`
- DI: `services/entitlements_service/di.py`
- Policies: `services/entitlements_service/policies/default.yaml`

## BOS Integration (Authoritative Preflight)
- Requirement computation: `services/batch_orchestrator_service/domain/pipeline_credit_guard.py` uses `PipelineCostStrategy`.
- Bulk check client: `services/batch_orchestrator_service/implementations/entitlements_service_client_impl.py`
- Preflight route mapping: `200/402/429` with consistent body fields `allowed, denial_reason?, required_credits, available_credits, resource_breakdown, correlation_id`.

## Operational Semantics
- Preflight is advisory-only; no reservation. BOS denies at runtime if balances changed.
- Consumption only on successful phase completion via events.
- Correlation ID threading: Header `X-Correlation-ID` → BOS → Entitlements; persisted in audit and events.

## No-Legacy Policy (Prototype)
- No wrappers or aliases. Protocols reflect final interfaces. All call sites updated immediately.
- Reference: `CODEX.md` and `services/batch_orchestrator_service/protocols.py`.

## Testing & Quality
- Unit: bulk endpoint route behavior (200/402/429), cost and RL logic.
- Contracts: `BulkCreditCheckRequestV1/BulkCreditCheckResponseV1` and BOS preflight mapping.
- Functional E2E: AGW preflight 402/429/202, BOS runtime denial → `PipelineDeniedV1`, consumption flow `ResourceConsumptionV1 → Entitlements → CreditBalanceChangedV1` (outbox relay).
- Identity: Swedish characters in user/org IDs; org-first attribution; correlation ID threading tests.
- Observability: Metrics counters for preflight outcomes (allowed/insufficient/rate_limited).

## Operations
- Dev: `pdm run dev-start entitlements_service`
- Verify: `pdm run dev-logs entitlements_service`
- Typecheck/tests: `pdm run typecheck-all`, `pdm run pytest-root services/entitlements_service/tests`.

## Next Steps
- Expand contract tests for BOS ↔ Entitlements mapping and correlation propagation.
- Functional flows including runtime denial publication path.
- Metrics dashboards for preflight outcomes per org/user.

---

## Appendix A — Historical Log (Preserved)
The following section preserves the original implementation plan content for historical context and traceability. It is no longer normative; the reference above reflects the finalized design and APIs.

# Entitlements Service Implementation Plan

## Executive Summary

**Purpose**: Rate limiting and credit management for LLM-powered features to protect platform from API cost overruns while enabling B2B/B2C revenue models.

**Core Economics**: Resource-based pricing where credits map to actual LLM API calls, not arbitrary units like batches or essays.

**Integration**: BOS-centric architecture where pipeline cost calculations occur in Batch Orchestrator Service, with optimistic consumption on phase completion events.

## Session Progress Update (2025-09-06)

Cross-service orchestration and credit policy flow are aligned and implemented:

- API Gateway
  - ✅ Preflight orchestration to BOS; returns 402/429 per BOS preflight result.
  - ✅ Identity threading (user_id/org_id) intact; Swedish characters supported.
- BOS (Batch Orchestrator Service)
  - ✅ Domain-level `PipelineCreditGuard` computes resource requirements and performs bulk credit preflight via Entitlements.
  - ✅ Preflight route: `POST /internal/v1/batches/{batch_id}/pipelines/{phase}/preflight` returns 200/402 and now 429 for rate limits.
  - ✅ Protocol alignment: uses `check_credits_bulk` only (no legacy wrappers).
- Entitlements Service
  - ✅ New route: `POST /v1/entitlements/check-credits/bulk` with org-first attribution and per-metric rate limiting.
  - ✅ Policy-aware source selection (org preferred, fallback to user) and atomic evaluation across metrics.
  - ✅ 200 on allowed; 402 on insufficient credits; 429 on rate limits.

No-legacy policy: Protocols and clients were updated in lockstep; legacy shims and pass-throughs were removed to prevent drift.

## Implementation Status

### ✅ Phase 1 — Core Infrastructure (Complete)

- Database models and migrations
- Credit Manager with dual system (org/user precedence)
- Policy Loader with YAML + Redis caching
- Rate Limiter with Redis sliding window
- Core API endpoints (check-credits, consume-credits, balance)
- Admin endpoints for manual credit adjustments
- **Outbox Pattern**: OutboxManager, EventPublisher, EventRelayWorker
- **Event Publishing**: Proper ProcessingEvent enum usage (no magic strings)
- **Type Safety**: All type annotation issues resolved

### ✅ Phase 2 — Event Publishing Integration (Complete)

- ✅ EventPublisher injected into CreditManager via DI
- ✅ Publish CreditBalanceChangedV1 after credit operations  
- ✅ Publish RateLimitExceededV1 when limits hit
- ✅ Publish UsageRecordedV1 for tracking

### ✅ Phase 3 — ResourceConsumption + Identity Threading (Complete)

- ResourceConsumptionV1 contract standardized in common_core and published by CJ/other services
- Identity threading org-first preserved across AGW → BOS → downstream services → consumption events
- Entitlements consumer persists consumption with proper audit trail and outbox publishing

### ✅ Phase 4 — BOS Credit Guard & Pipeline Denial (Complete)

- Extracted credit logic from handler into domain service `PipelineCreditGuard`
- Kept `PipelineCostStrategy` in BOS domain to calculate requirements (pairwise CJ, linear AI feedback)
- Handler now delegates to guard; denial publishes `PipelineDeniedV1` and does not initiate pipeline
- SRP restored; no duplicated embedded credit logic remains in handler

### ✅ Phase 5 — Policy Configuration (Complete)

- `services/entitlements_service/policies/default.yaml` updated for resource-based costs and limits

### ✅ Phase 6 — Preflight Integration (Complete)

- BOS preflight endpoint returns 200 (allowed), 402 (insufficient), 429 (rate limit)
- Gateway invokes BOS preflight and returns 402/429 accordingly; 202 + publish on pass
- Runtime denials still publish `PipelineDeniedV1` for notification flows

### ✅ Phase 7 — Bulk Credit Check (Complete)

- Implemented `POST /v1/entitlements/check-credits/bulk` advisory check (no holds)
- Per-metric rate limiting; any violation yields rate-limit denial (429)
- Org-first or user fallback for total coverage; returns per-metric breakdown

## Architecture Alignment

### BOS-Centric Credit Calculation Architecture

**Critical Decision**: Credit calculations belong in **Batch Orchestrator Service (BOS)** as a domain service, not in Entitlements Service or processing services.

**Rationale**:

- BOS owns pipeline orchestration and resource planning
- BOS has complete context (pipeline steps + essay count)
- BOS is the single decision point for pipeline execution
- Keeps processing services focused on their domain
- Maintains clean DDD boundaries

### Resource-Based Pricing Model

**Credits map to actual resource consumption (LLM API calls)**:

- CJ Assessment: n*(n-1)/2 comparisons for n essays (full pairwise)
- AI Feedback: n API calls for n essays (linear)
- Free Operations: spellcheck, NLP analysis, batch operations

### Optimistic Consumption Pattern

- Preflight is advisory-only (no hold). Consumption occurs on successful phase outcome events
- If credits change between preflight and start, BOS will deny at runtime and publish `PipelineDeniedV1`

### No Legacy Policy (Prototype Codebase)

- Protocols and clients are evolved in lockstep; do not keep wrappers or pass-through methods.
- Prefer explicit, type-safe contracts and update all call sites immediately.
- Rationale: Align early to avoid spaghetti and hidden behavior in the prototype phase.

## Current Service Structure

```
services/entitlements_service/
  app.py                        # ✅ Integrated Quart + Kafka lifecycle
  startup_setup.py              # ✅ DI init, policy loader, EventRelayWorker
  config.py                     # ✅ Settings with ENTITLEMENTS_ prefix
  protocols.py                  # ✅ All protocols including EventPublisher
  di.py                         # ✅ Providers with EventPublisher integration
  models_db.py                  # ✅ SQLAlchemy models
  kafka_consumer.py             # ✅ ResourceConsumptionV1 consumer (credits post-usage)
  api/
    health_routes.py            # ✅ /healthz, /metrics
    entitlements_routes.py      # ✅ /v1/entitlements/* endpoints incl. bulk check
    admin_routes.py             # ✅ /v1/admin/credits/* (dev only)
  implementations/
    credit_manager_impl.py      # ✅ Core credit logic, EventPublisher injected
    policy_loader_impl.py       # ✅ YAML loading with Redis cache
    rate_limiter_impl.py        # ✅ Redis-based sliding window
    outbox_manager.py           # ✅ Transactional outbox
    event_publisher_impl.py     # ✅ Event publishing with proper enums
  policies/
    default.yaml                # ✅ Updated for resource-based pricing
```

## Database Schema ✅ **IMPLEMENTED**

```sql
-- Credit balances per subject (user or org)
CREATE TABLE credit_balances (
    subject_type VARCHAR(10) NOT NULL, -- 'user' or 'org'
    subject_id VARCHAR(255) NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (subject_type, subject_id)
);

-- Detailed audit trail for credit operations
CREATE TABLE credit_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type VARCHAR(10) NOT NULL,
    subject_id VARCHAR(255) NOT NULL,
    metric VARCHAR(100) NOT NULL,        -- 'cj_comparison', 'ai_feedback_generation'
    amount INTEGER NOT NULL,             -- Credits consumed
    batch_id VARCHAR(255),               -- For correlation with processing
    consumed_from VARCHAR(10) NOT NULL,  -- 'user' or 'org' (which balance used)
    correlation_id VARCHAR(255) NOT NULL,
    operation_status VARCHAR(20) DEFAULT 'completed', -- 'completed', 'failed', 'pending'
    created_at TIMESTAMP DEFAULT NOW()
);

-- Outbox for reliable event publishing
CREATE TABLE event_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(200) NOT NULL,
    event_data JSONB NOT NULL,
    topic VARCHAR(200) NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    published_at TIMESTAMP NULL
);
```

## Updated Policy Configuration (Phase 5)

```yaml
# services/entitlements_service/policies/default.yaml

costs:
  # Resource-based costs (per LLM API call)
  cj_comparison: 1              # Per pairwise comparison in CJ Assessment
  ai_feedback_generation: 5     # Per essay feedback generation
  ai_editor_revision: 3         # Per AI editor revision (future)
  
  # Free internal operations (no external API costs)
  spellcheck: 0                 # Internal processing via LanguageTool
  nlp_analysis: 0               # Internal NLP processing
  batch_create: 0               # Batch orchestration
  student_matching: 0           # NLP-based student matching
  content_upload: 0             # File uploads

rate_limits:
  # Resource-based limits (prevent API abuse)
  cj_comparison: 10000/day      # Max CJ comparisons per day
  ai_feedback_generation: 500/day   # Max AI feedback generations per day
  
  # Operation-based limits (prevent platform abuse)
  batch_create: 60/hour         # Maximum batch uploads per hour
  pipeline_request: 100/hour    # Maximum pipeline requests per hour
  credit_adjustment: 10/hour    # Administrative adjustments

signup_bonuses:
  # Initial credit allocation for new accounts
  user: 50          # Credits for individual teacher accounts
  org: 500          # Credits for institutional/organizational accounts

# Policy cache configuration
cache_ttl: 300      # Cache policies in Redis for 5 minutes
```

## Integration Flow Architecture (Final)

1. Teacher clicks Start → API Gateway `POST /v1/batches/{batch_id}/pipelines`
2. API Gateway performs BOS preflight: `POST /internal/v1/batches/{batch_id}/pipelines/{phase}/preflight`
3. BOS preflight:
   - BOS → BCS resolves final pipeline
   - BOS → PipelineCreditGuard calculates requirements (PipelineCostStrategy) and checks credits
   - Returns 200 allowed or 402 denial with breakdown; 429 for rate limits
4. If allowed: Gateway publishes `ClientBatchPipelineRequestV1` to Kafka and returns 202
5. Pipeline executes asynchronously; phases publish outcomes; Entitlements consumes credits from `ResourceConsumptionV1`
6. If runtime denial occurs (credits changed), BOS publishes `PipelineDeniedV1` and NotificationProjector emits teacher notification

This keeps queries synchronous (preflight) and execution event-driven, per Rule 020.

## Boundary Objects (Source of Truth)

These contracts are stable and must be used for onboarding and E2E tests.

- EventEnvelope (common_core.events.envelope)
  - Fields: `event_id: UUID`, `event_type: str`, `event_timestamp: datetime`, `source_service: str`, `correlation_id: UUID`, `data: Any`, `metadata: dict | None`

- ClientBatchPipelineRequestV1 (common_core.events.client_commands)
  - Fields: `batch_id: str`, `requested_pipeline: str`, `user_id: str`, `client_correlation_id: UUID`, optional `is_retry`, `retry_reason`

- PipelineDeniedV1 (common_core.events.pipeline_events)
  - Fields: `batch_id: str`, `user_id: str`, `org_id: Optional[str]`, `requested_pipeline: str`, `denial_reason: str`, `required_credits: int`, `available_credits: int`, `resource_breakdown: dict[str,int]`, `denied_at: datetime`
  - Topic: `huleedu.pipeline.denied.v1`

- ResourceConsumptionV1 (common_core.events.resource_consumption_events)
  - Fields: `user_id: str`, `org_id: Optional[str]`, `resource_type: str`, `quantity: int`, `service_name: str`, `processing_id: str`, `consumed_at: datetime` (enveloped with correlation)
  - Topic: `huleedu.resource.consumption.v1`

- BOS Preflight (new)
  - Endpoint: `POST /internal/v1/batches/{batch_id}/pipelines/{phase}/preflight`
  - Headers: `X-Correlation-ID: <uuid>`
  - 200 body: `{ allowed: true, batch_id, requested_pipeline, resolved_pipeline: [str], required_credits, available_credits, resource_breakdown, correlation_id }`
  - 402 body: `{ allowed: false, denial_reason: "insufficient_credits"|..., required_credits, available_credits, resource_breakdown, correlation_id }`
  - 429: rate-limit exceeded; 400/404 for invalid inputs; 500 on BOS error

- API Gateway Pipeline Request
  - Endpoint: `POST /v1/batches/{batch_id}/pipelines`
  - Preflight: calls BOS preflight; returns 402/429/400/404 per BOS; maps BOS 500→503
  - On pass: publishes `ClientBatchPipelineRequestV1`, returns `{ status: "accepted", correlation_id }`

- Entitlements API
  - `POST /v1/entitlements/check-credits` (single metric)
    - Request: `CreditCheckRequestV1 { user_id, org_id?, metric, amount }`
    - Response: `CreditCheckResponseV1 { allowed, reason?, required_credits, available_credits, source? }`
  - `POST /v1/entitlements/consume-credits` (single metric)
    - Request: `CreditConsumptionV1 { user_id, org_id?, metric, amount, batch_id?, correlation_id }`
    - Response: `{ success, new_balance, consumed_from }`

Decision: Entitlements provides a bulk credit check endpoint and BOS uses it exclusively (no BOS-side loops, no legacy wrappers).

- Endpoint: `POST /v1/entitlements/check-credits/bulk`
- Request: `{ user_id, org_id?, requirements: { [metric: string]: int }, correlation_id? }`
- Response (200 allowed, 402 denied, 429 rate-limit):
  - `allowed: bool` (overall)
  - `required_credits: int` (sum)
  - `available_credits: int`
  - `per_metric: { [metric]: { required, available, allowed, source, reason? } }`
  - `denial_reason?: "insufficient_credits" | "rate_limit_exceeded" | "policy_denied"`
  - `correlation_id: string`

## Next Steps (Immediate)

- Functional E2E Tests
  - Add scenarios in `tests/functional` to cover:
    - Preflight 402 (insufficient) with org-first Swedish IDs
    - Preflight 429 (rate limit exceeded)
    - Preflight 202 → BOS publishes `ClientBatchPipelineRequestV1` and pipeline starts
    - Runtime denial after preflight → `PipelineDeniedV1` consumed by notification path
    - `ResourceConsumptionV1` → Entitlements consume → `CreditBalanceChangedV1` via outbox relay

- Cross-Service Contract Tests
  - Add contract tests for `BulkCreditCheckRequestV1/BulkCreditCheckResponseV1` in common_core
  - Validate BOS preflight response mapping (stable fields, correlation threading)

- Observability
  - Add counters/histograms for preflight outcomes (allowed/insufficient/rate-limited) and per-metric rate-limit hits

- Documentation
  - Keep TASKS and service READMEs synced with contracts and routes (Rule 090)

### 📋 New Cross-Cutting Task (Test Infrastructure Alignment)

Scope: Align integration and functional test harnesses with the new AGW registration flow and identity threading.

- Update functional harness to use AGW `POST /v1/batches/register` instead of direct BOS calls
  - File: `tests/functional/pipeline_test_harness.py`
  - Ensure `user_id`/`org_id` are injected via JWT in AGW tests
- Update utility helpers impacted by registration flow
  - Directory: `tests/utils`
  - Adjust any BOS direct registration helpers to route via AGW
- Review cross-cutting integration tests for assumptions
  - Replace direct BOS registration calls with AGW proxy usage
  - Update assertions for `X-Org-ID` forwarding and envelope metadata `org_id`
- Run `typecheck-all` and targeted suites; fix fixtures to include optional `org_id`
## Lessons Learned

- Keep “queries” synchronous and “commands” event-driven; BOS preflight pattern simplifies UX and aligns with Rule 020
- Centralize credit policy evaluation in BOS domain; keep Entitlements focused on balance/rates and consumption
- Define boundary objects explicitly to avoid drift and accelerate onboarding
- Maintain org-first identity across all contracts; include Swedish characters in tests and schema validation
- Plan for bulk credit checks at Entitlements to avoid BOS-side loops when multiple resources are required

## BOS PipelineCostStrategy Implementation

```python
# services/batch_orchestrator_service/domain/pipeline_cost_strategy.py

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class ResourceRequirements:
    """Resource requirements for pipeline execution"""
    cj_comparisons: int = 0
    ai_feedback_calls: int = 0
    
    def to_entitlement_checks(self) -> List[Tuple[str, int]]:
        """Convert to entitlement check requests"""
        checks = []
        if self.cj_comparisons > 0:
            checks.append(("cj_comparison", self.cj_comparisons))
        if self.ai_feedback_calls > 0:
            checks.append(("ai_feedback_generation", self.ai_feedback_calls))
        return checks

class PipelineCostStrategy:
    """Domain Service for calculating pipeline resource requirements"""
    
    def calculate_requirements(
        self,
        pipeline_steps: List[str],  # From BCS resolution
        essay_count: int            # From batch data
    ) -> ResourceRequirements:
        """Calculate resource requirements for pipeline execution"""
        
        reqs = ResourceRequirements()
        
        for step in pipeline_steps:
            if step == "cj_assessment":
                # Full pairwise comparisons - what CJ actually does
                reqs.cj_comparisons = essay_count * (essay_count - 1) // 2
                
            elif step == "ai_feedback":
                # Linear: one API call per essay
                reqs.ai_feedback_calls = essay_count
                
            # spellcheck, nlp = free internal processing
        
        return reqs
```

## Event Models

### Consumed by Entitlements Service (Phase 3)

```python
ResourceConsumptionV1:
    """Event published when billable resources have been consumed.
    Published by processing services (CJ Assessment, AI Feedback, etc.)
    Consumed by Entitlements Service for credit tracking."""
    
    event_name: ProcessingEvent    # RESOURCE_CONSUMPTION_REPORTED
    entity_id: str                 # Batch ID
    entity_type: str               # "batch"
    
    # Identity (critical for credit attribution)
    user_id: str                   # User who owns the batch
    org_id: Optional[str]          # Organization if applicable
    
    # Resource details
    resource_type: str             # "cj_comparison", "ai_feedback_generation"
    quantity: int                  # Actual amount consumed
    
    # Service metadata
    service_name: str              # "cj_assessment_service"
    processing_id: str             # Internal job ID for tracing
    consumed_at: datetime          # When resources were consumed
    correlation_id: str            # For distributed tracing
```

### Published by Entitlements Service

```python
CreditBalanceChangedV1:
    subject: SubjectRefV1          # {type: "org"|"user", id: "uuid"}
    delta: int                     # Negative for consumption, positive for addition
    new_balance: int
    reason: str                    # "credit_operation", "manual_adjustment"
    correlation_id: str

RateLimitExceededV1:
    subject: SubjectRefV1
    metric: str                    # "cj_comparison", "ai_feedback_generation"
    limit: int
    window_seconds: int
    correlation_id: str

UsageRecordedV1:
    subject: SubjectRefV1
    metric: str
    amount: int
    period_start: datetime
    period_end: datetime
    correlation_id: str
```

### Published by BOS (Phase 4)

```python
PipelineDeniedV1:
    batch_id: str
    user_id: str
    org_id: Optional[str]
    requested_pipeline: str
    denial_reason: str             # "insufficient_credits" | "rate_limit_exceeded"
    required_credits: int
    available_credits: int
    # NO suggested_alternatives - client handles this (YAGNI)
```

### WebSocket Notification for Credit Denials

BOS's NotificationProjector will handle credit denial notifications:

- notification_type: "pipeline_denied_insufficient_credits" or "pipeline_denied_rate_limit"
- category: WebSocketEventCategory.BATCH_PROGRESS
- priority: NotificationPriority.IMMEDIATE
- action_required: true (teacher needs to purchase credits or wait)

## Testing Strategy

### Unit Tests

- ✅ Credit resolution logic (org-first, user fallback)
- ✅ Policy loading and caching mechanisms
- ✅ Rate limiting calculations with Redis
- ✅ Balance arithmetic operations
- ✅ Entitlements bulk route (allowed/insufficient/rate-limit/validation)
- ✅ BOS preflight route mapping (200/402/429)
- ⏳ PipelineCostStrategy calculations (10, 30, 60 essays)

### Integration Tests

- ✅ Redis rate limiting with concurrent requests
- ✅ Database credit operations with transactions
- ✅ Policy loading from YAML files
- ✅ Event publishing via outbox pattern
- ✅ BOS ↔ Entitlements communication flow (bulk preflight)
- ⏳ Phase completion event consumption

### End-to-End Tests

- ⏳ Preflight 402/429/202 via AGW → BOS → Entitlements
- ⏳ Credit consumption on successful completion (ResourceConsumptionV1)
- ⏳ Failed operations don't consume credits
- ⏳ Rate limit enforcement across services
- ⏳ Org-first identity path with Swedish characters

### Performance Tests

- API endpoint response times (<100ms for checks, <500ms for consumption)
- Event publishing throughput
- Redis rate limiting under load
- Policy cache hit rates

## Success Criteria

### ✅ **Completed**

1. **Service Foundation**: Core infrastructure operational
2. **Credit Management**: Dual system with audit trails
3. **Rate Limiting**: Redis-based sliding window protection
4. **Event Infrastructure**: Outbox pattern with reliable delivery
5. **Type Safety**: Proper enum usage, no magic strings

### 🔄 **In Progress**

6. **Event Publishing**: Domain events for all credit operations

### 📋 **Planned**

7. **Cost Protection**: No unauthorized LLM API consumption possible
8. **BOS Integration**: Pipeline cost calculation and credit checking
9. **Optimistic Consumption**: Credits consumed only on success
10. **Platform Integration**: End-to-end credit enforcement

### 🚀 **Future Expansion**

11. **Business Model**: Teacher credit purchases and organizational pools
12. **Payment Integration**: Webhook endpoints for credit top-ups
13. **Analytics**: Usage reporting and cost optimization insights

## Architectural Principles Maintained

- **Domain-Driven Design**: Clean bounded contexts with proper service responsibilities
- **Event-Driven Architecture**: Reliable async communication via Kafka
- **Service Autonomy**: Independent deployment and data ownership
- **Observability**: Full tracing, metrics, and structured logging
- **YAGNI Compliance**: Simple implementations without unnecessary complexity
- **EdTech Trust Model**: Optimistic patterns suitable for educational environments

## Appendix A: Phase 3 Technical Implementation (Historical Reference)

### Files Modified During Phase 3 Implementation

#### Database Schema Changes

- **File**: `services/cj_assessment_service/models_db.py`
  - **Change**: Added `user_id: Mapped[str | None]` and `org_id: Mapped[str | None]` fields to `CJBatchUpload` model
  - **Impact**: Enables identity storage for credit attribution
  - **Migration**: `20250831_0007_baf9cf9c8c5c_add_user_id_and_org_id_fields_to_cjbatchupload_for_credit_attribution.py`

#### Event Contract Changes (BREAKING)

- **File**: `libs/common_core/src/common_core/events/cj_assessment_events.py`
  - **Change**: Added `user_id: str` (required) and `org_id: str | None` fields to `ELS_CJAssessmentRequestV1`
  - **Impact**: All services creating CJ assessment requests must provide user_id
  - **Breaking**: Existing code without user_id will fail validation

#### Identity Threading Implementation

- **File**: `services/cj_assessment_service/event_processor.py`
  - **Change**: Extract user_id/org_id from event and thread through `converted_request_data`
  - **Impact**: Ensures identities flow through entire CJ workflow

- **File**: `services/cj_assessment_service/protocols.py`
  - **Change**: Updated `create_new_cj_batch()` method signature with optional user_id/org_id parameters
  - **Impact**: Protocol-level support for identity storage

- **File**: `services/cj_assessment_service/implementations/db_access_impl.py`
  - **Change**: Store user_id/org_id in CJBatchUpload during creation
  - **Impact**: Persistence layer stores identities for later retrieval

- **File**: `services/cj_assessment_service/cj_core_logic/batch_preparation.py`
  - **Change**: Extract identities from request data and pass to database creation
  - **Impact**: Workflow orchestration includes identity handling

#### Resource Event Publishing Changes

- **File**: `services/cj_assessment_service/cj_core_logic/dual_event_publisher.py`
  - **Change**: Removed conditional logic; always publish ResourceConsumptionV1 with identities
  - **Impact**: Reliable resource consumption tracking; fails fast if user_id missing
  - **Breaking**: Will raise ValueError if identity threading fails

#### Health Monitoring Enhancement

- **File**: `services/entitlements_service/api/health_routes.py`
  - **Change**: Added Kafka consumer health monitoring to `/healthz` endpoint
  - **Impact**: Operational visibility into consumer status

### Architectural Decisions Made

#### 1. Required vs Optional Identity Fields

- **Decision**: Made `user_id` required, `org_id` optional in event contract
- **Rationale**: Every assessment must have a user for billing; org membership is optional
- **Impact**: Clear contract enforcement prevents missing identity scenarios

#### 2. Fail-Fast Identity Validation

- **Decision**: Raise ValueError if user_id not available during resource event publishing
- **Rationale**: Better to fail visibly than silently skip credit attribution
- **Impact**: Forces proper identity threading; prevents billing data loss

#### 3. Database Migration Strategy

- **Decision**: Add identity fields as nullable to avoid migration issues
- **Rationale**: Allows gradual rollout; existing batches can complete without identities
- **Impact**: Backward compatibility during transition period

#### 4. Always-Publish Resource Events

- **Decision**: Removed conditional logic that checked for user_id availability
- **Rationale**: Consistent behavior; identity threading should always work
- **Impact**: Reliable credit consumption; failures are visible and debuggable

### Integration Points Established

```
ELS Service (Future)
    ↓ publishes ELS_CJAssessmentRequestV1 (with user_id/org_id)
CJ Assessment Service 
    ↓ threads identities through workflow
    ↓ stores identities in CJBatchUpload
    ↓ publishes ResourceConsumptionV1 (with user_id/org_id)
Entitlements Service
    ↓ consumes ResourceConsumptionV1
    ↓ debits credits from user_id (or org_id if user insufficient)
```

## Phase 3 Implementation Checklist - COMPLETED

### Common Core Changes

- [x] Create `libs/common_core/src/common_core/events/resource_consumption_events.py`
- [x] Add `ResourceConsumptionV1` event model with all required fields
- [x] Add `RESOURCE_CONSUMPTION_REPORTED` to `ProcessingEvent` enum
- [x] Add topic mapping: `"huleedu.resource.consumption.v1"`
- [ ] Run tests to ensure event model serialization works (Phase 3.1)

### CJ Assessment Service Changes

- [x] Update `cj_core_logic/dual_event_publisher.py` to publish third event
- [x] Pass `user_id` and `org_id` through the workflow (complete identity threading)
- [x] Calculate actual comparison count from completed comparisons
- [x] Publish `ResourceConsumptionV1` after successful assessment (always, no conditional logic)
- [x] **BONUS**: Added user_id/org_id fields to CJBatchUpload model with database migration
- [x] **BONUS**: Updated ELS_CJAssessmentRequestV1 event contract with required user_id field
- [x] **BONUS**: Updated repository protocol and implementation for identity storage
- [ ] Add unit tests for resource consumption event publishing (Phase 3.1)
- [ ] Integration test with Kafka to verify event publishing (Phase 3.1)

### Entitlements Service Changes

- [x] Create `services/entitlements_service/kafka_consumer.py`
- [x] Implement `EntitlementsKafkaConsumer` class
- [x] Add handler for `ResourceConsumptionV1` events
- [x] Subscribe to topic: `huleedu.resource.consumption.v1`
- [x] Call `credit_manager.consume_credits()` with event data
- [x] Add consumer to `app.py` lifecycle (startup/shutdown)
- [x] Consumer dependencies provided via DI (handled in startup_setup.py)
- [x] Add health check endpoint for consumer status
- [ ] Create integration tests with testcontainers (Phase 3.1)
- [ ] Test credit consumption with various event scenarios (Phase 3.1)

### Testing & Validation (Phase 3.1)

- [ ] Unit test: 10 essays = 45 comparisons consumed
- [ ] Unit test: 5 essays = 10 comparisons consumed
- [ ] Integration test: End-to-end flow from CJ to credits
- [ ] Test org vs user credit precedence
- [ ] Test handling of missing user_id/org_id (now fails fast with ValueError)
- [ ] Load test: Verify consumer can handle event volume
- [ ] Monitor: Outbox pattern ensures reliable delivery
- [ ] **NEW**: Contract tests for updated ELS_CJAssessmentRequestV1 event
- [ ] **NEW**: Unit tests for identity threading through CJ workflow
- [ ] **NEW**: Integration tests for idempotent resource consumption
- [ ] **NEW**: Health endpoint integration tests

### Documentation Updates

- [ ] Update this document when Phase 3 is complete
- [ ] Document the new event in common_core README
- [ ] Add architecture diagram showing event flow
- [ ] Update service READMEs with new capabilities

This implementation plan ensures robust credit management while maintaining the platform's architectural integrity and educational domain requirements.

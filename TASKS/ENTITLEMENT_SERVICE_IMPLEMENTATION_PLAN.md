# Entitlements Service Implementation Plan

## Executive Summary

**Purpose**: Rate limiting and credit management for LLM-powered features to protect platform from API cost overruns while enabling B2B/B2C revenue models.

**Core Economics**: Resource-based pricing where credits map to actual LLM API calls, not arbitrary units like batches or essays.

**Integration**: BOS-centric architecture where pipeline cost calculations occur in Batch Orchestrator Service, with optimistic consumption on phase completion events.

## Implementation Status

### ✅ **Phase 1: COMPLETE** - Core Infrastructure

- Database models and migrations
- Credit Manager with dual system (org/user precedence)
- Policy Loader with YAML + Redis caching
- Rate Limiter with Redis sliding window
- Core API endpoints (check-credits, consume-credits, balance)
- Admin endpoints for manual credit adjustments
- **Outbox Pattern**: OutboxManager, EventPublisher, EventRelayWorker
- **Event Publishing**: Proper ProcessingEvent enum usage (no magic strings)
- **Type Safety**: All type annotation issues resolved

### ✅ **Phase 2: COMPLETE** - Event Publishing Integration

- ✅ EventPublisher injected into CreditManager via DI
- ✅ Publish CreditBalanceChangedV1 after credit operations  
- ✅ Publish RateLimitExceededV1 when limits hit
- ✅ Publish UsageRecordedV1 for tracking

### 📋 **Phases 3-6: PLANNED** - Full Platform Integration

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

**Flow**: Check credits → Start pipeline → Consume credits on phase completion
**Benefits**: Fair billing (pay for success), graceful failure handling, educational trust model

## Current Service Structure

```
services/entitlements_service/
  app.py                        # ✅ Integrated Quart + Kafka lifecycle
  startup_setup.py              # ✅ DI init, policy loader, EventRelayWorker
  config.py                     # ✅ Settings with ENTITLEMENTS_ prefix
  protocols.py                  # ✅ All protocols including EventPublisher
  di.py                         # ✅ Providers with EventPublisher integration
  models_db.py                  # ✅ SQLAlchemy models
  kafka_consumer.py             # ⏳ TO BE CREATED (Phase 3)
  api/
    health_routes.py            # ✅ /healthz, /metrics
    entitlements_routes.py      # ✅ /v1/entitlements/* endpoints
    admin_routes.py             # ✅ /v1/admin/credits/* (dev only)
  implementations/
    credit_manager_impl.py      # ✅ Core credit logic, EventPublisher injected
    policy_loader_impl.py       # ✅ YAML loading with Redis cache
    rate_limiter_impl.py        # ✅ Redis-based sliding window
    outbox_manager.py           # ✅ Transactional outbox
    event_publisher_impl.py     # ✅ Event publishing with proper enums
  policies/
    default.yaml                # ⏳ TO BE UPDATED (Phase 5)
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

## Integration Flow Architecture

### Complete Pipeline Flow with Credit Management

```
1. Teacher clicks "Start Processing" → API Gateway → BOS
2. BOS → BCS (resolve pipeline) → ["spellcheck", "cj_assessment", "nlp"]
3. BOS calculates resource requirements:
   - CJ: essays*(essays-1)/2 comparisons
   - AI: essays API calls  
   - Spellcheck/NLP: 0 (free)
4. BOS → Entitlements (check_credits for each resource)
5. Entitlements validates credits + rate limits
6. If sufficient: BOS starts pipeline → ELS → Services
7. Services complete phases → Publish completion events
8. Entitlements consumes credits on phase completion events
9. If insufficient: 
   - BOS publishes PipelineDeniedV1 → API Gateway → 402 Payment Required
   - BOS projects TeacherNotificationRequestedV1 → WebSocket → Real-time teacher notification
```

## Implementation Phases

### ✅ **Phase 1: COMPLETE** - Core Infrastructure (January 2025)

- Database models, migrations, and indexing
- Credit Manager with dual system (org → user precedence)
- Policy Loader with YAML configuration and Redis caching
- Rate Limiter with Redis sliding window implementation
- Core API endpoints with proper validation
- Admin endpoints for manual operations
- Outbox pattern for reliable event publishing
- Type-safe event publishing with ProcessingEvent enums

### ✅ **Phase 2: COMPLETE** - Event Publishing Integration

**Timeline**: Completed January 2025
**Status**: All event publishing integrated into CreditManager

**Completed Tasks**:

1. ✅ Inject EventPublisher into CreditManager via DI
2. ✅ Publish CreditBalanceChangedV1 after successful credit operations
3. ✅ Publish RateLimitExceededV1 when rate limits are hit
4. ✅ Publish UsageRecordedV1 for usage analytics
5. ✅ Updated tests with MockEventPublisher

### ✅ **Phase 3: COMPLETE** - Resource Consumption Events & Kafka Consumer

**Timeline**: Completed January 2025
**Purpose**: Consume credits based on actual resource consumption events

**Status**: Core functionality implemented and working. Identity threading complete. Testing phase required.

**Architectural Decision**: Create dedicated `ResourceConsumptionV1` event

- Clean DDD boundaries between services
- Explicit resource consumption tracking
- Consistent pattern for all billable services

**Implementation Details**:

#### Part A: Create ResourceConsumptionV1 Event (common_core)

```python
# libs/common_core/src/common_core/events/resource_consumption_events.py
class ResourceConsumptionV1(BaseEventData):
    """Event for tracking billable resource consumption."""
    event_name: ProcessingEvent = Field(default=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED)
    user_id: str
    org_id: Optional[str]
    resource_type: str  # "cj_comparison", "ai_feedback_generation"
    quantity: int
    service_name: str
    processing_id: str
    consumed_at: datetime
```

#### Part B: Update CJ Assessment Service

```python
# In dual_event_publisher.py, add third event:
resource_event = ResourceConsumptionV1(
    entity_id=bos_batch_id,
    entity_type="batch",
    user_id=batch.user_id,  # Need to pass this through
    org_id=batch.org_id,
    resource_type="cj_comparison",
    quantity=len(comparison_results),  # Actual comparisons
    service_name="cj_assessment_service",
    processing_id=cj_assessment_job_id,
    consumed_at=datetime.now(UTC),
    correlation_id=correlation_id
)
await event_publisher.publish(topic="huleedu.resource.consumption.v1", event=resource_event)
```

#### Part C: Entitlements Kafka Consumer

```python
# services/entitlements_service/kafka_consumer.py
async def handle_resource_consumption(event: ResourceConsumptionV1):
    """Consume credits based on actual resource usage."""
    await credit_manager.consume_credits(
        user_id=event.user_id,
        org_id=event.org_id,
        metric=event.resource_type,
        amount=event.quantity,
        batch_id=event.entity_id,
        correlation_id=event.correlation_id
    )
```

**Tasks**:

1. ✅ Create `ResourceConsumptionV1` event model in common_core
2. ✅ Add RESOURCE_CONSUMPTION_REPORTED to ProcessingEvent enum + topic mapping
3. ✅ Update CJ Assessment Service `dual_event_publisher.py` to publish resource events (actual quantity)
4. ✅ Pass user_id/org_id through CJ Assessment workflow (complete identity threading)
5. ✅ Create `EntitlementsKafkaConsumer` class
6. ✅ Subscribe to topic: `huleedu.resource.consumption.v1`
7. ✅ Implement credit consumption handler and start background task
8. ✅ Add consumer health checks and monitoring
9. 📋 Integration tests with testcontainers (Phase 3.1)

**Key Architectural Changes Made:**

- Added `user_id` and `org_id` fields to `CJBatchUpload` model with database migration
- Updated `ELS_CJAssessmentRequestV1` event contract with required `user_id` field
- Implemented complete identity threading from event intake to resource consumption publishing
- Removed conditional publishing logic - ResourceConsumptionV1 events now always published
- Enhanced health endpoint with Kafka consumer status monitoring

### 🧪 **Phase 3.1: CURRENT** - Comprehensive Testing Implementation

**Timeline**: Current sprint (immediate priority)
**Purpose**: Create comprehensive test coverage for Phase 3 identity threading and credit consumption

**Critical Need**: The breaking changes made to event contracts and method signatures require immediate test coverage to ensure reliability.

**Testing Strategy Following HuleEdu Methodology**:

#### Testing Priority 1: Event Contract Testing

- **Event Contract Tests**: Update/create tests for `ELS_CJAssessmentRequestV1` with new `user_id`/`org_id` fields
- **Schema Validation Tests**: Test required `user_id` field validation and optional `org_id`
- **Cross-Service Contract Tests**: Verify ELS → CJ Assessment event compatibility
- **EventEnvelope Tests**: Test envelope serialization with updated event data

#### Testing Priority 2: Unit Test Coverage  

- **event_processor.py**: Test identity extraction and threading to workflow
- **batch_preparation.py**: Test identity extraction and database storage
- **db_access_impl.py**: Test `create_new_cj_batch()` with identity parameters
- **dual_event_publisher.py**: Test identity extraction and ResourceConsumptionV1 publishing
- **health_routes.py**: Test Kafka consumer status reporting logic

#### Testing Priority 3: Integration Testing

- **End-to-End Identity Threading**: Full flow from ELS event → ResourceConsumptionV1 publishing
- **Credit Consumption Integration**: ResourceConsumptionV1 → Entitlements credit deduction
- **Idempotency Testing**: Duplicate event handling with same event_id
- **Health Endpoint Integration**: Consumer status during various states

#### Testing Priority 4: Broken Test Repair

- **Assess Current Test Failures**: Identify tests broken by event contract changes
- **Update Test Fixtures**: Fix `ELS_CJAssessmentRequestV1` fixtures with required `user_id`
- **Repository Mock Updates**: Update mocks for `create_new_cj_batch()` signature changes
- **Contract Test Updates**: Fix cross-service contract validation tests

**Files Requiring Test Updates**:

- `services/cj_assessment_service/tests/conftest.py` - Update fixtures
- `services/cj_assessment_service/tests/test_llm_config_overrides_contract.py` - Event contract tests
- `services/entitlements_service/tests/` - New integration tests
- New contract tests for updated `ELS_CJAssessmentRequestV1`

**Success Criteria**:

- All existing tests pass after breaking changes
- >90% test coverage for identity threading logic
- Integration tests prove end-to-end credit consumption works
- Idempotency tests validate duplicate event handling
- `pdm run test-all` runs clean from repository root

### 📋 **Phase 4: PLANNED** - BOS Integration

**Timeline**: Following sprint  
**Purpose**: BOS-centric credit checking before pipeline execution

**Tasks**:

1. Create PipelineCostStrategy domain service in BOS:

   ```python
   def calculate_cj_comparisons(n: int) -> int:
       return n * (n - 1) // 2  # Simple full pairwise
   ```

2. Add credit checking to BOS pipeline request handler
3. Create PipelineDeniedV1 event model in common_core
4. Publish denial events when insufficient credits
5. Project credit denial notifications to WebSocket:
   - Use existing NotificationProjector (services/batch_orchestrator_service/notification_projector.py)
   - Create TeacherNotificationRequestedV1 for real-time teacher feedback
   - Include denial reason, required credits, and available credits in payload
6. Handle credit denial in ClientPipelineRequestHandler:
   - After credit check failure, call notification_projector.handle_pipeline_denied_credits()
   - Ensure teacher gets immediate visual feedback about credit insufficiency

### 📋 **Phase 5: PLANNED** - Policy Configuration Update

**Timeline**: Same sprint as Phase 4
**Purpose**: Align policy with resource-based pricing

**Tasks**:

1. Update services/entitlements_service/policies/default.yaml
2. Migrate from batch/essay-based to resource-based costs
3. Update rate limits to reflect actual resource constraints
4. Test policy loading and caching

### 📋 **Phase 6: PLANNED** - API Gateway Integration

**Timeline**: Final integration sprint
**Purpose**: Complete end-to-end credit enforcement

**Tasks**:

1. Handle PipelineDeniedV1 events in API Gateway
2. Return 402 Payment Required with credit details
3. Update client-facing error messages
4. Add credit purchase flow hooks (future payment integration)

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

- ✅ Credit resolution logic (dual system precedence)
- ✅ Policy loading and caching mechanisms
- ✅ Rate limiting calculations with Redis
- ✅ Balance arithmetic operations
- ⏳ Event publishing integration
- ⏳ PipelineCostStrategy calculations (10, 30, 60 essay batches)

### Integration Tests

- ✅ Redis rate limiting with concurrent requests
- ✅ Database credit operations with transactions
- ✅ Policy loading from YAML files
- ✅ Event publishing via outbox pattern
- ⏳ BOS ↔ Entitlements communication flow
- ⏳ Phase completion event consumption

### End-to-End Tests

- ⏳ Complete pipeline flow with credit checking
- ⏳ Credit consumption on successful completion
- ⏳ Failed operations don't consume credits
- ⏳ Rate limit enforcement across services
- ⏳ Organization membership changes

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

## Phase 3 Technical Implementation Details

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

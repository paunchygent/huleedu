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

### 🔄 **Phase 2: IN PROGRESS** - Event Publishing Integration

- ✅ EventPublisher injected into CreditManager via DI
- ⏳ Publish CreditBalanceChangedV1 after credit operations  
- ⏳ Publish RateLimitExceededV1 when limits hit
- ⏳ Publish UsageRecordedV1 for tracking

### 📋 **Phases 3-5: PLANNED** - Full Platform Integration

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
9. If insufficient: BOS publishes PipelineDeniedV1 → API Gateway → 402 Payment Required
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

### 🔄 **Phase 3: IN PROGRESS** - Resource Consumption Events & Kafka Consumer

**Timeline**: Current sprint (January 2025)
**Purpose**: Consume credits based on actual resource consumption events

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

1. ⏳ Create `ResourceConsumptionV1` event model in common_core
2. ⏳ Add RESOURCE_CONSUMPTION_REPORTED to ProcessingEvent enum
3. ⏳ Update CJ Assessment Service dual_event_publisher.py
4. ⏳ Pass user_id/org_id through CJ Assessment workflow
5. ⏳ Create EntitlementsKafkaConsumer class
6. ⏳ Subscribe to topic: `huleedu.resource.consumption.v1`
7. ⏳ Implement credit consumption handler
8. ⏳ Add consumer health checks and monitoring
9. ⏳ Integration tests with testcontainers

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

## Phase 3 Implementation Checklist

### Common Core Changes

- [ ] Create `libs/common_core/src/common_core/events/resource_consumption_events.py`
- [ ] Add `ResourceConsumptionV1` event model with all required fields
- [ ] Add `RESOURCE_CONSUMPTION_REPORTED` to `ProcessingEvent` enum
- [ ] Add topic mapping: `"huleedu.resource.consumption.v1"`
- [ ] Run tests to ensure event model serialization works

### CJ Assessment Service Changes

- [ ] Update `cj_core_logic/dual_event_publisher.py` to publish third event
- [ ] Pass `user_id` and `org_id` through the workflow (from batch context)
- [ ] Calculate actual comparison count from completed comparisons
- [ ] Publish `ResourceConsumptionV1` after successful assessment
- [ ] Add unit tests for resource consumption event publishing
- [ ] Integration test with Kafka to verify event publishing

### Entitlements Service Changes

- [ ] Create `services/entitlements_service/kafka_consumer.py`
- [ ] Implement `EntitlementsKafkaConsumer` class
- [ ] Add handler for `ResourceConsumptionV1` events
- [ ] Subscribe to topic: `huleedu.resource.consumption.v1`
- [ ] Call `credit_manager.consume_credits()` with event data
- [ ] Add consumer to `app.py` lifecycle (startup/shutdown)
- [ ] Update `di.py` to provide consumer dependencies
- [ ] Add health check endpoint for consumer status
- [ ] Create integration tests with testcontainers
- [ ] Test credit consumption with various event scenarios

### Testing & Validation

- [ ] Unit test: 10 essays = 45 comparisons consumed
- [ ] Unit test: 5 essays = 10 comparisons consumed
- [ ] Integration test: End-to-end flow from CJ to credits
- [ ] Test org vs user credit precedence
- [ ] Test handling of missing user_id/org_id
- [ ] Load test: Verify consumer can handle event volume
- [ ] Monitor: Outbox pattern ensures reliable delivery

### Documentation Updates

- [ ] Update this document when Phase 3 is complete
- [ ] Document the new event in common_core README
- [ ] Add architecture diagram showing event flow
- [ ] Update service READMEs with new capabilities

This implementation plan ensures robust credit management while maintaining the platform's architectural integrity and educational domain requirements.

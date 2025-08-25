# Entitlements Service Phase 3 - Implementation Decisions

## Session Date: January 2025

## Executive Summary

This document captures the critical architectural decisions made for Phase 3 of the Entitlements Service implementation, specifically regarding how the service will track and consume credits based on actual resource usage.

## Key Architectural Decision: Option B - Dedicated Resource Consumption Event

### Decision
Create a dedicated `ResourceConsumptionV1` event for tracking billable resource consumption, rather than reusing existing events from other domains.

### Rationale
1. **Clean DDD Boundaries**: Each bounded context owns its integration contracts
2. **Semantic Clarity**: Event name matches its purpose (resource consumption → credit deduction)
3. **Minimal Data Transfer**: Only sends what Entitlements needs (no grades, scores, rankings)
4. **Independent Evolution**: Can change without affecting other consumers
5. **Consistent Pattern**: All billable services (CJ, AI Feedback, future) use same event

### Alternative Considered (Option A)
Using the existing `AssessmentResultV1` event which contains `comparison_count` in metadata.
- **Rejected because**: Couples Entitlements to RAS's event contract, violates Single Responsibility

## Event Model Specification

```python
class ResourceConsumptionV1(BaseEventData):
    """Event published when billable resources have been consumed.
    
    Published by: Processing services (CJ Assessment, AI Feedback, etc.)
    Consumed by: Entitlements Service for credit tracking
    Topic: huleedu.resource.consumption.v1
    """
    
    event_name: ProcessingEvent = Field(default=ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED)
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

## Implementation Strategy

### Phase 3 Components

1. **Common Core Changes**
   - New event model: `ResourceConsumptionV1`
   - New enum value: `ProcessingEvent.RESOURCE_CONSUMPTION_REPORTED`
   - New topic: `"huleedu.resource.consumption.v1"`

2. **CJ Assessment Service Updates**
   - Publish third event (in addition to ELS and RAS events)
   - Include actual comparison count (not estimates)
   - Pass user_id/org_id through workflow

3. **Entitlements Service Consumer**
   - Subscribe to resource consumption events
   - Call existing `credit_manager.consume_credits()`
   - Handle missing identity gracefully

## Critical Corrections from Investigation

### What We Discovered
- ❌ `CJAssessmentPhaseCompletedV1` does NOT exist
- ❌ `AIFeedbackPhaseCompletedV1` does NOT exist (service not implemented)
- ✅ `CJAssessmentCompletedV1` exists but is a THIN event (no comparison count)
- ✅ `AssessmentResultV1` has comparison count but wrong semantic context

### What Actually Exists
- **CJ Assessment Service**: Publishing dual events (thin to ELS, rich to RAS)
- **Spellchecker Service**: Free operation (no credits)
- **NLP Service**: Free operation (no credits)
- **AI Feedback Service**: NOT IMPLEMENTED YET

## Resource Calculation Formula

For CJ Assessment (full pairwise comparisons):
```python
comparisons = n * (n - 1) / 2  # where n = number of essays
```

Examples:
- 10 essays = 45 comparisons
- 5 essays = 10 comparisons
- 3 essays = 3 comparisons

## Status Updates

### Phase 2: COMPLETE ✅
- Event publishing integrated into CreditManagerImpl
- CreditBalanceChangedV1, RateLimitExceededV1, UsageRecordedV1 all publishing
- Tests updated with MockEventPublisher

### Phase 3: IN PROGRESS 🔄
- ResourceConsumptionV1 event model defined
- Implementation checklist created
- Task document updated with detailed implementation steps

## Next Steps

1. **Immediate**: Create ResourceConsumptionV1 in common_core
2. **Next**: Update CJ Assessment Service to publish consumption events
3. **Then**: Implement Entitlements Kafka consumer
4. **Finally**: Integration testing with full pipeline

## Files Updated in This Session

1. `/TASKS/ENTITLEMENT_SERVICE_IMPLEMENTATION_PLAN.md`
   - Phase 2 marked complete
   - Phase 3 updated with Option B approach
   - Added implementation details and checklist

2. `/TASKS/ENTITLEMENTS_PHASE_3_DECISIONS.md` (this file)
   - Captured all decisions and rationale

## Implementation Checklist

See main task document section "Phase 3 Implementation Checklist" for detailed tasks.

## Architecture Maintained

- ✅ Domain-Driven Design principles
- ✅ Event-Driven Architecture patterns
- ✅ Service autonomy and boundaries
- ✅ YAGNI principle (no over-engineering)
- ✅ Clean Architecture separation

## Risk Mitigation

- **Risk**: User/org identity not available in CJ Assessment context
- **Mitigation**: Pass through from batch creation, store in CJ batch state

- **Risk**: Event delivery failure causing credit loss
- **Mitigation**: Outbox pattern already implemented, ensures delivery

- **Risk**: Double consumption of credits
- **Mitigation**: Idempotency via correlation_id tracking

---

This document serves as the source of truth for Phase 3 implementation decisions.
All implementation should follow these specifications exactly.
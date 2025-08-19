# Task T013: Implement Dual Event Pattern for Spellchecker Service

## Status: NOT STARTED
**Priority**: HIGH  
**Estimated Effort**: 5-8 days  
**Dependencies**: None (can proceed immediately)  
**Assignee**: TBD  

---

## Executive Summary

Refactor the spellchecker service to implement the dual event pattern, aligning it with the established pattern used by CJ Assessment and NLP Phase 2 services. This will optimize event data flow by publishing minimal state events to ELS/BCS and rich business events to RAS.

## Business Rationale

### Current Problems
1. **Inefficient Data Distribution**: Single rich event sent to all consumers (ELS, RAS, BCS) regardless of their needs
2. **Performance Impact**: ELS and BCS receive unnecessary business data, slowing state transitions
3. **Architectural Inconsistency**: Spellchecker is the last service not using the dual event pattern
4. **Downstream Confusion**: Unclear what data spellchecker can actually provide vs. what consumers expect

### Benefits of Implementation
1. **Optimized Performance**: 70% reduction in event size for state management consumers
2. **Architectural Alignment**: Consistent event patterns across all processing services
3. **Clear Data Contracts**: Explicit separation of state vs. business data
4. **Future-Ready**: Proper foundation for downstream NLP services (AES, AI Feedback)

---

## Technical Context

### Current Implementation Limitations
Based on architectural analysis, the spellchecker service uses:
- **pyspellchecker**: Basic spell checking (NO grammar, punctuation, or categorization)
- **L2 Swedish Dictionary**: Fixed learner error corrections (4,886 entries)
- **Capabilities**: ONLY spelling corrections, no linguistic analysis

### What Spellchecker CAN Provide
```python
# Realistic data available from current implementation:
- Total correction count
- L2 dictionary corrections vs. general spelling corrections
- Word count and correction density
- Corrected text (via storage reference)
```

### What Spellchecker CANNOT Provide
```python
# Not possible with current libraries:
- Grammar error detection
- Punctuation corrections
- Error categorization (spelling vs. grammar)
- Linguistic patterns or complexity metrics
```

---

## Implementation Plan

### Phase 1: Define Event Contracts (Days 1-2)

#### Step 1.1: Create Thin Event Contract
**File**: `libs/common_core/src/common_core/events/spellcheck_events.py`

```python
class SpellcheckPhaseCompletedV1(BaseModel):
    """
    Thin event for ELS state management and BCS batch coordination.
    
    Published to: huleedu.batch.spellcheck.phase.completed.v1
    Consumers: ELS, BCS
    """
    # Core identifiers
    entity_id: str  # Essay ID
    batch_id: str
    correlation_id: str
    
    # State transition data
    status: ProcessingStatus  # SUCCESS/FAILED
    corrected_text_storage_id: Optional[str]  # If successful
    
    # Minimal error info for state decisions
    error_code: Optional[str]  # If failed
    
    # Basic metrics
    processing_duration_ms: int
    timestamp: datetime
```

**Rationale**: Minimal data needed for state transitions, ~300 bytes vs. 2KB for rich event

#### Step 1.2: Enhance Rich Event Contract
**File**: `libs/common_core/src/common_core/events/spellcheck_events.py`

```python
class SpellcheckResultV1(ProcessingUpdate):
    """
    Rich event for RAS business data aggregation.
    
    Published to: huleedu.essay.spellcheck.results.v1
    Consumers: RAS, future NLP services
    """
    # Identifiers
    entity_id: str
    batch_id: str
    correlation_id: str
    user_id: str
    
    # Business results (what we ACTUALLY have)
    status: ProcessingStatus
    corrections_made: int
    
    # Realistic metrics
    correction_metrics: SpellcheckMetricsV1
    
    # Storage references
    original_text_storage_id: str
    corrected_text_storage_id: Optional[str]
    
    # Error details if failed
    error_details: Optional[ErrorDetailsV1]
    
    # Processing metadata
    processing_duration_ms: int
    processor_version: str  # "pyspellchecker_1.0_L2_swedish"

class SpellcheckMetricsV1(BaseModel):
    """Metrics that spellchecker can ACTUALLY provide."""
    total_corrections: int
    l2_dictionary_corrections: int  # Swedish learner errors
    spellchecker_corrections: int   # General spelling
    word_count: int
    correction_density: float  # corrections per 100 words
```

**Rationale**: Only includes data the spellchecker can actually provide, no false promises

---

### Phase 2: Implement Dual Publishing (Days 3-4)

#### Step 2.1: Extract Additional Metrics
**File**: `services/spell_checker_service/core_logic.py`

```python
def process_text(self, text: str) -> SpellcheckResult:
    """Enhanced to capture more metrics."""
    # Existing correction logic...
    
    # Add metric extraction
    word_count = len(text.split())
    l2_corrections = len([c for c in corrections if c.source == "L2"])
    spell_corrections = len([c for c in corrections if c.source == "pyspell"])
    correction_density = (total_corrections / word_count) * 100 if word_count > 0 else 0
    
    return SpellcheckResult(
        corrected_text=corrected_text,
        corrections_made=total_corrections,
        # New fields
        word_count=word_count,
        l2_corrections=l2_corrections,
        spell_corrections=spell_corrections,
        correction_density=correction_density
    )
```

**Actionable Items**:
- [ ] Add word_count calculation to process_text()
- [ ] Separate L2 vs. pyspell correction counts
- [ ] Calculate correction_density metric
- [ ] Update SpellcheckResult model

#### Step 2.2: Implement Dual Event Publishers
**File**: `services/spell_checker_service/implementations/event_publisher_impl.py`

```python
async def publish_completion(self, result: SpellcheckResult) -> None:
    """Publish both thin and rich events."""
    
    # 1. Publish thin event for state management
    thin_event = self._create_thin_event(result)
    await self._publish_to_topic(
        topic="huleedu.batch.spellcheck.phase.completed.v1",
        event=thin_event
    )
    
    # 2. Publish rich event for business data
    rich_event = self._create_rich_event(result)
    await self._publish_to_topic(
        topic="huleedu.essay.spellcheck.results.v1",
        event=rich_event
    )
    
    # 3. Keep legacy event for backward compatibility (temporary)
    legacy_event = self._create_legacy_event(result)
    await self._publish_to_topic(
        topic="huleedu.essay.spellcheck.completed.v1",
        event=legacy_event
    )
```

**Actionable Items**:
- [ ] Create _create_thin_event() method
- [ ] Create _create_rich_event() method  
- [ ] Update outbox pattern for multiple events
- [ ] Add feature flag for gradual rollout

---

### Phase 3: Migrate Consumers (Days 5-6)

#### Step 3.1: Migrate ELS to Thin Event
**File**: `services/essay_lifecycle_service/kafka_consumer.py`

```python
# Update topic subscription
KAFKA_TOPICS = [
    # Replace: "huleedu.essay.spellcheck.completed.v1"
    "huleedu.batch.spellcheck.phase.completed.v1",  # New thin event
    # ... other topics
]

# Update handler
async def _handle_spellcheck_completed(self, event: SpellcheckPhaseCompletedV1):
    """Handle thin spellcheck completion event."""
    # Only needs: entity_id, status, corrected_text_storage_id
    await self.essay_repository.update_spellcheck_status(
        essay_id=event.entity_id,
        status=event.status,
        storage_id=event.corrected_text_storage_id
    )
```

**Actionable Items**:
- [ ] Update ELS topic subscription
- [ ] Modify event handler for thin event structure
- [ ] Test state transitions with new event
- [ ] Update ELS unit tests

#### Step 3.2: Migrate BCS to Thin Event
**File**: `services/batch_conductor_service/kafka_consumer.py`

Similar changes for batch coordination:
- [ ] Update BCS topic subscription
- [ ] Modify handler for thin event
- [ ] Test batch phase coordination
- [ ] Update BCS unit tests

#### Step 3.3: Update RAS for Rich Event
**File**: `services/result_aggregator_service/implementations/event_processor_impl.py`

```python
async def _handle_spellcheck_result(self, event: SpellcheckResultV1):
    """Handle rich spellcheck result event."""
    # Store enhanced business data
    await self.batch_repository.update_essay_spellcheck_result(
        essay_id=event.entity_id,
        batch_id=event.batch_id,
        status=event.status,
        corrections_made=event.corrections_made,
        word_count=event.correction_metrics.word_count,
        correction_density=event.correction_metrics.correction_density,
        l2_corrections=event.correction_metrics.l2_dictionary_corrections,
        spell_corrections=event.correction_metrics.spellchecker_corrections,
        corrected_text_storage_id=event.corrected_text_storage_id
    )
```

**Actionable Items**:
- [ ] Add new topic subscription for rich event
- [ ] Update event handler for enhanced metrics
- [ ] Extend database schema for new fields
- [ ] Create migration script for schema changes

---

### Phase 4: Testing & Validation (Days 7-8)

#### Step 4.1: Unit Tests
- [ ] Test thin event creation with minimal data
- [ ] Test rich event creation with full metrics
- [ ] Test dual publishing mechanism
- [ ] Test backward compatibility mode

#### Step 4.2: Integration Tests
- [ ] Test ELS state transitions with thin event
- [ ] Test BCS batch coordination with thin event
- [ ] Test RAS data aggregation with rich event
- [ ] Test end-to-end pipeline with dual events

#### Step 4.3: Performance Validation
- [ ] Measure event size reduction (target: 70% for thin events)
- [ ] Measure ELS state transition latency improvement
- [ ] Validate Kafka throughput optimization
- [ ] Monitor consumer lag metrics

---

## Rollout Strategy

### Stage 1: Dual Publishing (Week 1)
1. Deploy spellchecker with dual publishing enabled
2. All consumers still use legacy event
3. Monitor new event topics for correctness

### Stage 2: Consumer Migration (Week 2)
1. Migrate ELS to thin event (monitor for 24h)
2. Migrate BCS to thin event (monitor for 24h)
3. Migrate RAS to rich event (monitor for 24h)

### Stage 3: Legacy Cleanup (Week 3)
1. Confirm all consumers migrated successfully
2. Remove legacy event publishing
3. Archive old event topics

---

## Success Criteria

### Functional Requirements
- [ ] Spellchecker publishes both thin and rich events correctly
- [ ] ELS processes state transitions with thin event
- [ ] BCS coordinates batches with thin event
- [ ] RAS aggregates business data from rich event
- [ ] All existing functionality maintained

### Performance Requirements
- [ ] Thin event size < 500 bytes (vs. 2KB legacy)
- [ ] ELS state transition latency reduced by 20%
- [ ] Kafka throughput reduced by 30% for state events
- [ ] No increase in processing errors

### Quality Requirements
- [ ] 100% backward compatibility during migration
- [ ] Zero data loss during rollout
- [ ] All tests passing (unit, integration, E2E)
- [ ] Documentation updated

---

## Risk Mitigation

### Risk 1: Consumer Migration Failures
**Mitigation**: Keep legacy event publishing during migration, feature flags for rollback

### Risk 2: Data Contract Mismatches
**Mitigation**: Extensive integration testing, gradual rollout with monitoring

### Risk 3: Performance Degradation
**Mitigation**: Load testing before production, canary deployment strategy

---

## Documentation Requirements

1. **Update Service README**: Document new event patterns and data contracts
2. **Update Architecture Diagrams**: Show dual event flow
3. **Create Migration Guide**: For other teams consuming spellcheck events
4. **Update API Documentation**: Clarify what data spellchecker provides

---

## Important Notes

### What This Task Does NOT Include
1. **Grammar Checking**: Spellchecker will NOT add grammar capabilities
2. **Error Categorization**: Cannot distinguish error types with current libraries
3. **Linguistic Analysis**: This belongs in NLP Service, not spellchecker

### Architectural Decisions
1. **Keep Spellchecker Simple**: It's a spelling service, not a linguistic analyzer
2. **NLP Service Responsibility**: Grammar and linguistic analysis belong in NLP Service
3. **Honest Data Contracts**: Only promise what we can actually deliver

---

## References

- CJ Assessment Dual Event Implementation: `/services/cj_assessment_service/`
- NLP Phase 2 Dual Event Pattern: `/services/nlp_service/`
- Event Contracts: `/libs/common_core/src/common_core/events/`
- Architecture Decision: Dual Event Pattern (ADR-007)

---

## Task Checklist

### Preparation
- [ ] Review existing spellchecker implementation
- [ ] Understand current consumer requirements
- [ ] Set up development environment

### Implementation
- [ ] Phase 1: Define event contracts
- [ ] Phase 2: Implement dual publishing
- [ ] Phase 3: Migrate consumers
- [ ] Phase 4: Testing & validation

### Deployment
- [ ] Stage 1: Enable dual publishing
- [ ] Stage 2: Migrate consumers
- [ ] Stage 3: Remove legacy events

### Completion
- [ ] All tests passing
- [ ] Documentation updated
- [ ] Performance metrics validated
- [ ] Stakeholders notified

---

**Last Updated**: 2025-08-19  
**Author**: Architecture Team  
**Reviewed By**: TBD
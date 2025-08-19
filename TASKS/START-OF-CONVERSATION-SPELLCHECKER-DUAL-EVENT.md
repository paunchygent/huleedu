# COMPREHENSIVE START-OF-CONVERSATION PROMPT FOR SPELLCHECKER DUAL EVENT PATTERN IMPLEMENTATION

## ULTRATHINK: SESSION CONTEXT AND PROJECT STATUS

You are continuing critical architectural work on the HuleEdu monorepo to complete the dual event pattern implementation across all processing services. This is the FINAL service that needs alignment with our established event-driven architecture pattern.

### Completed Work (What Has Been Done)

1. **CJ Assessment Service** ✅
   - Successfully refactored to dual event pattern
   - Thin event: `CJAssessmentCompletedV1` → ELS (state management)
   - Rich event: `AssessmentResultV1` → RAS (business data with rankings, scores)
   - Status: PRODUCTION READY

2. **NLP Phase 2 Service** ✅
   - Successfully refactored to dual event pattern
   - Thin event: `BatchNlpAnalysisCompletedV1` → ELS (state management)
   - Rich event: `EssayNlpCompletedV1` → RAS (linguistic analysis data)
   - Status: PRODUCTION READY

3. **Result Aggregator Service (RAS)** ✅
   - Fixed enum pattern mismatch (was using duplicated enums instead of common_core)
   - Now correctly imports from `common_core.status_enums.BatchClientStatus`
   - API responses use lowercase_snake_case to match established patterns
   - Successfully consuming rich events from CJ Assessment and NLP services
   - Location: `/services/result_aggregator_service/`

4. **Spellchecker Service Analysis** ✅
   - Conducted realistic capability assessment
   - Discovered fundamental limitations: pyspellchecker + L2 dictionary = ONLY spelling
   - Cannot provide: grammar, punctuation, error categorization, linguistic patterns
   - Created realistic dual event proposal based on actual capabilities
   - Task document created: `/TASKS/T013-spellchecker-dual-event-pattern.md`

### Current State (Where We Are Now)

**The Problem**: Spellchecker is the LAST service still using single rich event pattern, sending unnecessary data to all consumers regardless of their needs.

**Current Pattern**: 
```
SpellcheckResultDataV1 (2KB) → ALL consumers (ELS, RAS, BCS)
```

**Target Pattern**:
```
SpellcheckPhaseCompletedV1 (300 bytes) → ELS, BCS (state management)
SpellcheckResultV1 (2KB) → RAS (business data)
```

## ULTRATHINK: MANDATORY READING SEQUENCE

**MUST READ these files and rules in EXACT ORDER before ANY implementation:**

### 1. Core Architecture Rules
From `.cursor/rules/000-rule-index.mdc`, read in this sequence:
- `.cursor/rules/015-project-structure-standards.mdc` - Understand monorepo structure
- `.cursor/rules/010-foundational-principles.mdc` - Core DDD and Clean Architecture
- `.cursor/rules/020-architectural-mandates.mdc` - Service boundaries and communication
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` - **CRITICAL: Dual event pattern**
- `.cursor/rules/042-async-patterns-and-di.mdc` - Dishka DI and async patterns
- `.cursor/rules/051-eda-event-contracts.mdc` - Event structure and contracts
- `.cursor/rules/052-eda-implementation-patterns.mdc` - Outbox pattern implementation

### 2. Existing Dual Event Implementations (STUDY THESE AS EXAMPLES)
- `/services/cj_assessment_service/implementations/event_publisher_impl.py` - Dual publishing example
- `/services/nlp_service/implementations/event_publisher_impl.py` - Another dual pattern
- `/libs/common_core/src/common_core/events/cj_assessment_events.py` - Event contract examples
- `/libs/common_core/src/common_core/events/nlp_events.py` - More event contracts

### 3. Spellchecker Current Implementation
- `/services/spell_checker_service/implementations/spellchecker_impl.py` - Core logic
- `/services/spell_checker_service/core_logic.py` - Processing implementation
- `/services/spell_checker_service/implementations/event_publisher_impl.py` - Current single event
- `/libs/common_core/src/common_core/events/spellcheck_events.py` - Current event contract

### 4. Consumer Services (Understand Their Needs)
- `/services/essay_lifecycle_service/implementations/service_result_handler_impl.py` - ELS handler
- `/services/result_aggregator_service/implementations/event_processor_impl.py` - RAS handler
- `/services/batch_conductor_service/kafka_consumer.py` - BCS handler

### 5. Task Documentation
- `/TASKS/T013-spellchecker-dual-event-pattern.md` - **COMPLETE IMPLEMENTATION PLAN**

## ULTRATHINK: CRITICAL TECHNICAL CONTEXT

### Spellchecker Capabilities (REALISTIC ASSESSMENT)

**What Spellchecker CAN Provide:**
```python
{
    "total_corrections": int,              # Total count
    "l2_corrections": int,                 # Swedish learner dictionary
    "spellchecker_corrections": int,       # pyspellchecker
    "word_count": int,                     # Can calculate
    "correction_density": float,           # corrections per 100 words
    "corrected_text_storage_id": str       # Storage reference
}
```

**What Spellchecker CANNOT Provide (DO NOT ATTEMPT):**
```python
{
    "grammar_errors": IMPOSSIBLE,          # No grammar checking library
    "punctuation_corrections": IMPOSSIBLE,  # Not detected
    "error_categories": IMPOSSIBLE,        # Can't categorize
    "linguistic_patterns": IMPOSSIBLE,     # No linguistic analysis
    "error_severity": IMPOSSIBLE           # No context understanding
}
```

### Consumer Data Requirements

**ELS (Essay Lifecycle Service)**
- Needs: entity_id, status, corrected_text_storage_id
- Size requirement: < 500 bytes
- Purpose: State machine transitions

**RAS (Result Aggregator Service)**
- Needs: Full business data including metrics
- Size tolerance: 2-3KB acceptable
- Purpose: Business analytics and downstream query

**BCS (Batch Conductor Service)**
- Needs: entity_id, batch_id, status
- Size requirement: < 500 bytes
- Purpose: Batch coordination

## ULTRATHINK: CURRENT TASK - IMPLEMENT DUAL EVENT PATTERN

### Step 1: Define Event Contracts (START HERE)

Create two new event contracts in `/libs/common_core/src/common_core/events/spellcheck_events.py`:

1. **SpellcheckPhaseCompletedV1** (Thin Event)
   - Topic: `huleedu.batch.spellcheck.phase.completed.v1`
   - Size: ~300 bytes
   - Consumers: ELS, BCS

2. **SpellcheckResultV1** (Rich Event)
   - Topic: `huleedu.essay.spellcheck.results.v1`
   - Size: ~2KB
   - Consumers: RAS

### Step 2: Enhance Spellchecker to Extract Metrics

Modify `/services/spell_checker_service/core_logic.py`:
- Add word_count calculation
- Separate L2 vs pyspell correction counts
- Calculate correction_density

### Step 3: Implement Dual Publishing

Update `/services/spell_checker_service/implementations/event_publisher_impl.py`:
- Create thin event for state management
- Create rich event for business data
- Maintain legacy event temporarily for backward compatibility
- Use outbox pattern for transactional consistency

### Step 4: Migrate Consumers

1. **ELS Migration**: Update to consume thin event
2. **BCS Migration**: Update to consume thin event
3. **RAS Migration**: Update to consume rich event

## ULTRATHINK: ARCHITECTURAL CONSTRAINTS AND DECISIONS

### CRITICAL CONSTRAINTS

1. **Spellchecker is NOT a linguistic analyzer** - It's ONLY a spell corrector
2. **Grammar belongs in NLP Service** - Spellchecker will NEVER do grammar
3. **Keep it simple** - Don't add complexity that libraries can't support
4. **Honest data contracts** - Only promise what we can deliver

### ESTABLISHED PATTERNS TO FOLLOW

1. **Outbox Pattern**: All events must use transactional outbox
2. **Storage References**: Large text via Content Service, not inline
3. **Event Envelope**: All Kafka events wrapped in EventEnvelope
4. **Dual Publishing**: Publish both events in single transaction

### COMMON PITFALLS TO AVOID

1. **DON'T promise grammar data** - Libraries don't support it
2. **DON'T inline corrected text** - Use storage references
3. **DON'T break existing consumers** - Keep legacy event during migration
4. **DON'T over-engineer** - Simple spelling service, nothing more

## ULTRATHINK: VERIFICATION AND SUCCESS CRITERIA

### Testing Requirements

1. **Unit Tests**: Both event creation paths tested
2. **Integration Tests**: Consumer migration validated
3. **E2E Tests**: Full pipeline with dual events
4. **Performance Tests**: Verify 70% size reduction for thin events

### Success Metrics

- Thin event size < 500 bytes ✓
- Rich event maintains all business data ✓
- Zero data loss during migration ✓
- 20% latency improvement for ELS ✓
- All existing functionality preserved ✓

## ULTRATHINK: IMMEDIATE NEXT STEPS

1. **Read all referenced files and rules** (30 minutes)
2. **Review task document T013** (15 minutes)
3. **Create event contracts** (Step 1 of implementation)
4. **Set up local testing environment**
5. **Begin implementation following task checklist**

## ULTRATHINK: KEY INFORMATION AND TIPS

### Docker Container Access
```bash
# Always find container first
docker ps | grep huleedu_spell

# Access logs
docker logs huleedu_spell_checker --tail 100 -f

# Restart after changes
pdm run restart spell_checker_service
```

### Database Schema
- Spellchecker DB: `huleedu_spell_checker` on port 5437
- No schema changes needed (event-driven, no direct DB writes)

### Kafka Topics
```bash
# Monitor new events
docker exec huleedu_kafka kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 \
  --topic huleedu.batch.spellcheck.phase.completed.v1 \
  --from-beginning
```

### Testing Commands
```bash
# Run spellchecker tests
pdm run pytest services/spell_checker_service/tests/ -xvs

# Run integration test
pdm run pytest tests/integration/test_spellchecker_dual_events.py -xvs

# Run E2E pipeline test
pdm run pytest tests/functional/test_e2e_spellcheck_pipeline.py -xvs -m e2e
```

## ULTRATHINK: SYSTEM STATE

- **Spellchecker Container**: Running (huleedu_spell_checker on port 8002)
- **Kafka**: All topics created and accessible
- **Database**: No changes needed (event-driven)
- **Consumers**: Currently using legacy single event
- **Task Document**: `/TASKS/T013-spellchecker-dual-event-pattern.md` ready
- **Examples**: CJ Assessment and NLP services as reference implementations

## ULTRATHINK: YOUR MISSION

Implement the dual event pattern for the spellchecker service following the detailed plan in T013. This is the FINAL service needing this architectural alignment. The implementation should be:

1. **Realistic**: Only promise what spellchecker can deliver
2. **Consistent**: Follow patterns from CJ Assessment and NLP services
3. **Safe**: Maintain backward compatibility during migration
4. **Tested**: Full test coverage at all levels
5. **Documented**: Clear contracts and migration guide

**Remember**: 
- Spellchecker is a simple spelling service, NOT a linguistic analyzer
- Grammar and linguistic analysis belong in NLP Service
- Follow the established patterns exactly
- Test thoroughly before declaring complete

## FINAL CHECKLIST BEFORE STARTING

- [ ] Read all rules in the mandatory sequence
- [ ] Review existing dual event implementations
- [ ] Understand spellchecker limitations
- [ ] Read task document T013 completely
- [ ] Set up development environment
- [ ] Begin with Step 1: Event Contracts

**Critical Files to Keep Open**:
1. `/TASKS/T013-spellchecker-dual-event-pattern.md` - Your implementation guide
2. `/services/cj_assessment_service/implementations/event_publisher_impl.py` - Reference implementation
3. `/libs/common_core/src/common_core/events/spellcheck_events.py` - Where to add contracts
4. `/services/spell_checker_service/implementations/event_publisher_impl.py` - What to modify

---

**Session Goal**: Complete Phase 1 (Event Contracts) and Phase 2 (Dual Publishing) of the spellchecker dual event pattern implementation, setting up for consumer migration in the next session.

**Time Estimate**: 4-6 hours for Phases 1-2

**Success Indicator**: Spellchecker publishing both thin and rich events correctly with all tests passing.
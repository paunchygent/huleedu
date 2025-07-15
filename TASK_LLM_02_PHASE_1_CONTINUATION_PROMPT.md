# CJ ASSESSMENT SERVICE EVENT-DRIVEN TRANSFORMATION - PHASE 1 IMPLEMENTATION

You are Claude Code, beginning Phase 1 of TASK-LLM-02 to transform the CJ Assessment Service from synchronous polling to event-driven architecture with persistent state management in the HuleEdu platform.

## ULTRATHINK MISSION OVERVIEW

**PRIMARY OBJECTIVE**: Implement Phase 1 of TASK-LLM-02 by establishing database schema for batch state management and removing all polling infrastructure from the CJ Assessment Service while adding callback support.

**CONTEXT**: TASK-LLM-01 has been successfully completed with comprehensive event-driven infrastructure:

- ✅ LLM Provider Service publishes callbacks via Kafka (no more polling endpoints)
- ✅ `LLMComparisonResultV1` event contract established with 1-5 confidence scale
- ✅ Kafka topic `huleedu.llm_provider.comparison_result.v1` ready for callbacks
- ✅ Breaking change fully implemented - all consumers must use event-driven patterns

**CURRENT STATE**: CJ Assessment Service still uses synchronous polling, blocking resources and limiting scalability to ~10 concurrent batches. Phase 1 will lay the foundation for 1000+ concurrent batch support.

## MANDATORY WORKFLOW

### STEP 1: Build Architectural Knowledge

Read these foundational documents in order:

1. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/000-rule-index.mdc` - Navigate to all relevant rules
2. `/Users/olofs_mba/Documents/Repos/huledu-reboot/CLAUDE.md` - Project architectural mandates
3. `/Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-LLM-01.md` - Understand completed callback infrastructure
4. `/Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-LLM-02.md` - Complete Phase 1 requirements (Day 1-3)
5. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/020.7-cj-assessment-service.mdc` - Service-specific architecture
6. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/053-sqlalchemy-async-patterns.mdc` - Database patterns
7. `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/048-structured-error-handling-standards.mdc` - Error handling patterns

### STEP 2: ULTRATHINK Agent Deployment

Deploy agents to implement Phase 1 systematically using TodoWrite for progress tracking:

- **Agent Alpha**: Database schema design and state enumerations
- **Agent Beta**: Model implementation with proper relationships
- **Agent Gamma**: Database migration creation
- **Agent Delta**: Configuration updates for callback support
- **Agent Echo**: LLM Provider client refactoring (remove polling)
- **Agent Zeta**: Quality assurance and testing

## TASK-LLM-01 ACHIEVEMENTS (FOUNDATION FOR PHASE 1)

### Event Infrastructure Ready ✅

- **Callback Topic**: `huleedu.llm_provider.comparison_result.v1` configured and tested
- **Event Model**: `LLMComparisonResultV1` with mutual exclusion between success/error fields
- **Confidence Scale**: Correctly aligned to 1-5 scale (matching CJ Assessment expectations)
- **Breaking Change**: All polling removed from LLM Provider Service

### Critical Integration Points ✅

```python
# From TASK-LLM-01: Callback event structure
class LLMComparisonResultV1(BaseModel):
    request_id: str
    correlation_id: UUID
    winner: Optional[EssayComparisonWinner]  # Success fields
    justification: Optional[str]
    confidence: Optional[float]  # 1-5 scale
    error_detail: Optional[ErrorDetail]  # Error field
    provider: LLMProviderType
    model: str
    response_time_ms: int
    token_usage: TokenUsage
    cost_estimate: float
```

## PHASE 1 IMPLEMENTATION REQUIREMENTS

### Sub-Phase 1.1: Database Schema & State Management

**Agent Alpha Mission**: Design state management infrastructure

Files to create:
- `services/cj_assessment_service/enums.py` (new)

```python
class BatchStateEnum(str, enum.Enum):
    """State machine for CJ assessment batch processing."""
    INITIALIZING = "INITIALIZING"
    GENERATING_PAIRS = "GENERATING_PAIRS" 
    WAITING_CALLBACKS = "WAITING_CALLBACKS"
    SCORING = "SCORING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
```

**Agent Beta Mission**: Implement database models

Files to modify:
- `services/cj_assessment_service/models_db.py`

Key models:
- `CJBatchState`: Real-time processing state with progress tracking
- Update `ComparisonPair`: Add correlation tracking for callbacks
- Update `CJBatchUpload`: Add one-to-one relationship to batch state

**Agent Gamma Mission**: Create database migration

Files to create:
- `services/cj_assessment_service/alembic/versions/[timestamp]_add_batch_state_management.py`

Requirements:
- Create `batch_state_enum` type
- Create `cj_batch_states` table with proper indexes
- Add correlation tracking columns to `cj_comparison_pairs`

### Sub-Phase 1.2: Remove Polling & Add Callback Support

**Agent Delta Mission**: Update configuration for callbacks

Files to modify:
- `services/cj_assessment_service/config.py`

New settings:
- `LLM_PROVIDER_CALLBACK_TOPIC`: Default to `huleedu.llm_provider.comparison_result.v1`
- `BATCH_TIMEOUT_HOURS`: Default 4 hours
- `BATCH_MONITOR_INTERVAL_MINUTES`: Default 5 minutes
- `MIN_SUCCESS_RATE_THRESHOLD`: Default 0.8

**Agent Echo Mission**: Refactor LLM Provider client

Files to modify:
- `services/cj_assessment_service/implementations/llm_provider_service_client.py`

Requirements:
- Remove ALL polling methods (`_poll_for_results`, `_retrieve_queue_result`, etc.)
- Update `generate_comparison` to include `callback_topic` in request
- Return `None` for 202 responses (result arrives via callback)
- Use structured error handling with `HuleEduError`
- Add circuit breaker pattern

## CRITICAL ARCHITECTURAL CONSTRAINTS

### DO NOT Change

- Event models from TASK-LLM-01 are final and immutable
- Confidence scale MUST remain 1-5 (no conversion needed)
- Callback topic `huleedu.llm_provider.comparison_result.v1` is fixed
- Use exception-based error handling with `HuleEduError`

### MUST Implement

- Breaking change: Remove ALL polling code without backwards compatibility
- Every comparison request MUST specify callback topic
- Use `SELECT FOR UPDATE` for batch state updates (prevent race conditions)
- Implement proper idempotency checks in all state transitions
- Follow async SQLAlchemy patterns from rule 053

### Database Design Principles

- Single source of truth: `CJBatchState` table
- Optimistic locking for concurrent updates
- Proper indexes for correlation_id lookups
- CASCADE deletes for referential integrity
- Use timezone-aware datetime fields

## AGENT INSTRUCTIONS

### Agent Alpha: Database Schema Design

**Mission**: Create state enumeration for batch processing lifecycle
**Focus**: Define clear state transitions with no ambiguity
**Files**:
- Create: `services/cj_assessment_service/enums.py`

**Requirements**:
- Import `enum` from standard library
- Create `BatchStateEnum` as string enum
- Document each state's purpose
- Ensure states cover complete lifecycle

### Agent Beta: Model Implementation

**Mission**: Add batch state tracking and correlation support
**Focus**: Proper relationships, constraints, and documentation
**Files**:
- Modify: `services/cj_assessment_service/models_db.py`

**Requirements**:
- Add `CJBatchState` model with all tracking fields
- Update `ComparisonPair` with correlation tracking
- Add bidirectional relationships
- Use proper SQLAlchemy v2 syntax

### Agent Gamma: Database Migration

**Mission**: Create Alembic migration for state management
**Focus**: Safe migration with proper rollback support
**Files**:
- Create: `services/cj_assessment_service/alembic/versions/[timestamp]_add_batch_state_management.py`

**Requirements**:
- Create enum type first
- Add all tables and columns
- Include proper indexes
- Implement complete downgrade()

### Agent Delta: Configuration Updates

**Mission**: Add callback and monitoring configuration
**Focus**: Sensible defaults with clear documentation
**Files**:
- Modify: `services/cj_assessment_service/config.py`

**Requirements**:
- Add all callback-related settings
- Include batch monitoring settings
- Document each setting's purpose
- Use Pydantic Field descriptions

### Agent Echo: LLM Client Refactoring

**Mission**: Remove polling and implement callback-based submission
**Focus**: Clean removal of legacy code, proper error handling
**Files**:
- Modify: `services/cj_assessment_service/implementations/llm_provider_service_client.py`

**Requirements**:
- Delete all polling methods completely
- Add callback_topic to requests
- Implement circuit breaker
- Use structured error handling

### Agent Zeta: Quality Assurance

**Mission**: Validate all changes and ensure architectural compliance
**Focus**: Type checking, linting, import validation
**Commands**:
- `pdm run -p services/cj_assessment_service typecheck`
- `pdm run lint-all`
- `pdm run format-all`

## SUCCESS CRITERIA

### Phase 1 Completion Requirements:

1. **Database Schema** ✓
   - BatchStateEnum defined with all states
   - CJBatchState model with complete tracking fields
   - ComparisonPair updated with correlation support
   - Migration script ready and tested

2. **Configuration** ✓
   - Callback topic configured
   - Monitoring intervals defined
   - All settings documented

3. **Client Refactoring** ✓
   - Zero polling code remains
   - Callback topic included in all requests
   - Circuit breaker implemented
   - Structured error handling

4. **Quality Gates** ✓
   - All type checks pass
   - No linting errors
   - Import patterns correct
   - No breaking changes to existing batch creation

### Validation Checklist:

- [ ] Can create a new batch without errors
- [ ] Comparison requests include callback_topic
- [ ] No polling endpoints referenced
- [ ] Database migration runs cleanly
- [ ] All models have proper relationships

## IMMEDIATE NEXT STEPS

1. Deploy TodoWrite to track Phase 1 sub-tasks:
   - Database schema design
   - Model implementation  
   - Migration creation
   - Configuration updates
   - Client refactoring
   - Quality validation

2. Deploy ULTRATHINK agents in sequence:
   - Alpha → Beta → Gamma (Database work)
   - Delta → Echo (Application work)
   - Zeta (Final validation)

3. After each agent completes:
   - Run targeted type checks
   - Validate no regressions
   - Update task progress

4. Document completion in TASK-LLM-02.md:
   - Mark Phase 1 sections as ✅ COMPLETED
   - Note any discoveries or issues
   - Prepare for Phase 2 (callback processing)

## PHASE 2 PREVIEW (NOT FOR THIS SESSION)

Phase 2 will implement callback processing and workflow logic:
- Kafka consumer updates for dual-topic subscription
- Callback event processor implementation
- Workflow state machine with transitions
- Idempotency and race condition handling

But first, Phase 1 must establish the foundation with proper state tracking infrastructure.

## CONTEXT FILES REFERENCE

**Primary Task Document**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/documentation/TASKS/TASK-LLM-02.md`
**Service Implementation**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/`
**Platform Rules**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/.cursor/rules/` (Use index for navigation)
**Event Models**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/common_core/src/common_core/events/llm_provider_events.py`
**Error Handling**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/libs/huleedu_service_libs/error_handling/`

Begin by deploying TodoWrite to plan Phase 1 implementation, then systematically deploy ULTRATHINK agents to transform the CJ Assessment Service from polling-based to event-driven architecture with robust state management.
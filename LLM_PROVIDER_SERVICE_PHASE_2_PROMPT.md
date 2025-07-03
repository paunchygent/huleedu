# 🔄 LLM Provider Service Phase 2: Orchestrator Integration

## MANDATORY PRE-TASK READING

You MUST read these files in EXACT order before proceeding:

### 1. Core Architecture Rules
- `.cursor/rules/010-foundational-principles.mdc` # Zero tolerance for architectural deviation
- `.cursor/rules/020-architectural-mandates.mdc` # Service communication patterns, DI requirements
- `.cursor/rules/030-event-driven-architecture-eda-standards.mdc` # Kafka event patterns
- `.cursor/rules/042-async-patterns-and-di.mdc` # Dishka patterns, async context managers
- `.cursor/rules/051-pydantic-v2-standards.mdc` # Event envelope patterns
- `.cursor/rules/070-testing-and-quality-assurance.mdc` # Protocol-based testing
- `.cursor/rules/080-repository-workflow-and-tooling.mdc` # PDM commands, development workflow

### 2. Task Context & Current Status
- `Documentation/TASKS/LLM_CALLER_SERVICE_IMPLEMENTATION_v2.md` # Full task details & current progress
- `PHASE_1_IMPLEMENTATION_SUMMARY.md` # What was completed in Phase 1
- `services/llm_provider_service/README.md` # Service documentation

### 3. Current Implementation Files
- `services/llm_provider_service/implementations/llm_orchestrator_impl.py` # CRITICAL: Cache check at line ~108
- `services/llm_provider_service/queue_models.py` # Queue models created in Phase 1
- `services/llm_provider_service/protocols.py` # Both cache and queue protocols present
- `services/llm_provider_service/implementations/resilient_queue_manager_impl.py` # Queue manager ready
- `services/llm_provider_service/di.py` # DI with both cache and queue providers

### 4. Service Context
- `services/cj_assessment_service/README.md` # Understand CJ methodology requirements
- `common_core/src/common_core/enums.py` # EnvironmentType, QueueStatus enums
- `common_core/src/common_core/events/envelope.py` # EventEnvelope pattern

## CRITICAL UNDERSTANDING CHECKPOINTS

Before writing ANY code, you MUST be able to answer:

### 1. Current State Understanding
- Where exactly does the orchestrator check cache? (Line number)
- What happens BEFORE any provider availability check?
- How does the queue infrastructure relate to current flow?
- Why is the cache check fundamentally wrong?

### 2. Phase 1 Accomplishments
- What queue components were created?
- How does ResilientQueueManagerImpl work?
- What is the watermark pattern for capacity?
- How does local queue fallback operate?

### 3. Required Changes
- What specific lines need removal in orchestrator?
- How should provider availability be checked?
- Where should queue logic be inserted?
- What response should be returned when queuing?

### 4. Architecture Compliance
- How must the orchestrator inject queue manager?
- What events should be published for queue operations?
- How to handle 202 Accepted responses?
- What about backwards compatibility during transition?

## TASK SPECIFICATION

**Goal**: Integrate the queue infrastructure created in Phase 1 into the LLM orchestrator, replacing cache-first logic with provider-first logic.

**Current Problem**:
- Orchestrator checks cache BEFORE provider availability (line ~108)
- Returns cached responses instead of fresh LLM calls
- No queue usage despite infrastructure being ready
- Psychometric validity still compromised

**Required Outcome**:
1. Provider availability checked FIRST
2. Fresh LLM calls when provider available
3. Queue requests when provider unavailable
4. Return 202 Accepted with queue_id
5. NO cached responses in production

## EXPECTED APPROACH

### Phase 2 Implementation Steps:

1. **Update DI in orchestrator**:
   - Inject QueueManagerProtocol
   - Keep cache temporarily for safe transition

2. **Refactor perform_comparison method**:
   - Remove cache check at beginning
   - Add provider availability check
   - Implement queue logic for unavailable providers
   - Return appropriate responses (200 vs 202)

3. **Add provider health checking**:
   - Circuit breaker integration
   - Health status methods
   - Timeout handling

4. **Update response models**:
   - Add queue response types
   - Handle 202 Accepted case
   - Include queue_id in response

5. **Add Kafka events**:
   - Request queued event
   - Queue full event
   - Provider unavailable event

## SUCCESS CRITERIA

Your implementation MUST:
- Check provider availability before ANY cache/queue operation
- Never return cached responses in production
- Queue requests when providers unavailable
- Return 202 with queue_id for queued requests
- Maintain service availability during changes
- Follow all HuleEdu patterns exactly

## WHAT NOT TO DO

- Don't remove cache completely yet (Phase 4)
- Don't implement queue processing (Phase 3)
- Don't add status endpoints yet (Phase 5)
- Don't break existing API contract

Remember: This phase is about changing the FLOW from cache-first to provider-first, integrating the queue infrastructure we built in Phase 1.
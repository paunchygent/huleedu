# New Claude Session Prompt: Fix Critical Race Condition in HuleEdu Event Processing

## Your First Actions (MANDATORY)

1. **Read the handoff document**: `TASKS/CLAUDE_HANDOFF_RACE_CONDITION_FIX.md`
2. **Read the project rules**: Start with `.cursor/rules/000-rule-index.mdc`
3. **Understand the outbox pattern**: Read `.cursor/rules/042.1-transactional-outbox-pattern.mdc`
4. **Review test results**: Examine the race condition debug tests in `tests/integration/`

## Context

I need you to fix a critical race condition in the HuleEdu microservices platform. After refactoring to use an outbox-first pattern (instead of Kafka-first with fallback), functional tests are failing due to a race condition between `BatchEssaysRegistered` and `EssayContentProvisioned` events.

### The Problem in Simple Terms

1. When a teacher uploads essays, two types of events are generated:
   - `BatchEssaysRegistered` (from BOS) - Creates slots for essays
   - `EssayContentProvisioned` (from File Service) - Contains essay content

2. If essay content arrives at ELS BEFORE the batch is registered, essays are marked as "excess content" because there are no slots available.

3. This prevents the `BatchEssaysReady` event from being generated, causing tests to hang.

### Why This Started Happening

The outbox pattern introduces relay workers that publish events asynchronously. Each service has its own relay worker with independent timing, exposing a pre-existing race condition.

## Your Mission

Using ULTRATHINK methodology and the appropriate subagents:

1. **Analyze** the current implementation
2. **Design** a fix that ensures proper event ordering
3. **Implement** the solution while respecting service boundaries
4. **Test** using the debug tests we've created
5. **Document** the changes

## Key Constraints

- **MUST** preserve the transactional outbox pattern
- **MUST** respect DDD service boundaries (no direct service communication)
- **MUST** maintain idempotent event processing
- **MUST** follow SOLID principles and YAGNI philosophy
- **MUST** use existing patterns from the codebase

## Test Command to Verify the Problem

```bash
# This test currently hangs - your fix should make it pass
pdm run pytest tests/functional/test_e2e_client_pipeline_resolution_workflow.py::TestClientPipelineResolutionWorkflow::test_state_aware_pipeline_optimization -v -s
```

## Debug Tests Available

We've created two debug tests that isolate the race condition:

1. `tests/integration/test_race_condition_simplified.py` - Proves the race condition with minimal setup
2. `tests/integration/test_debug_race_condition_isolation.py` - Full testcontainers isolation

Run these to understand the problem better.

## Expected Outcome

After your fix:
- All functional tests should pass
- Essays should be properly assigned to batch slots regardless of event arrival order
- The system should be resilient to relay worker timing variations

Start by reading the handoff document and understanding the full context. Use the subagents appropriately and follow the ULTRATHINK methodology for all major decisions.

---

## Copy and Paste This Text to Start New Claude Session:

I need you to fix a critical race condition in the HuleEdu microservices platform. Please start by:

1. Reading `TASKS/CLAUDE_HANDOFF_RACE_CONDITION_FIX.md` for full context
2. Reading `.cursor/rules/000-rule-index.mdc` to understand project rules
3. Reading `.cursor/rules/042.1-transactional-outbox-pattern.mdc` to understand the outbox pattern

The issue: After implementing an outbox-first pattern, functional tests fail because `EssayContentProvisioned` events sometimes arrive at ELS before `BatchEssaysRegistered` events, causing essays to be marked as "excess content" instead of being assigned to slots.

We've created debug tests in `tests/integration/` that prove this race condition. Your task is to design and implement a fix that ensures proper event ordering while maintaining all architectural principles.

Use ULTRATHINK methodology and appropriate subagents (lead-architect-planner for analysis, code-implementation-specialist for implementation, documentation-maintainer for docs).

The failing test is:
```bash
pdm run pytest tests/functional/test_e2e_client_pipeline_resolution_workflow.py::TestClientPipelineResolutionWorkflow::test_state_aware_pipeline_optimization -v -s
```

Please analyze the situation thoroughly before proposing a solution.
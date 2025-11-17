# Phase 2.5: Integration Verification - Start of Conversation Prompt

## Context: Where We Are

You are continuing work on the **LLM Provider Model Version Management System**. Phase 1 (Model Manifest) and Phase 2 (Model Checkers + CLI + Tests) are **100% complete and committed**.

### What Exists (Completed):

**Phase 1 Deliverables** ✅
- Model manifest: `services/llm_provider_service/model_manifest.py` (200 LoC)
  - Pydantic models: `ModelConfig`, `ModelRegistry`, `ProviderName`, `StructuredOutputMethod`
  - Functions: `get_model_config()`, `list_models()`, manifest validation
  - All 4 providers: Anthropic, OpenAI, Google, OpenRouter

**Phase 2 Deliverables** ✅
- Model checker protocol: `services/llm_provider_service/model_checker/base.py` (230 LoC)
  - `DiscoveredModel`, `ModelComparisonResult`, `ModelCheckerProtocol`
- Provider checkers (1,109 LoC total):
  - `anthropic_checker.py` (283 LoC): AsyncAnthropic SDK, Claude 3+ filtering
  - `openai_checker.py` (264 LoC): AsyncOpenAI SDK, GPT-4+/O1/O3 filtering
  - `google_checker.py` (272 LoC): google.genai async, Gemini 1.5+ filtering
  - `openrouter_checker.py` (290 LoC): aiohttp REST, Anthropic models filtering
- CLI tools (542 LoC):
  - `cli_check_models.py` (342 LoC): Typer CLI, CheckerFactory, exit codes
  - `cli_output_formatter.py` (200 LoC): Rich tables, summaries, breaking changes
- Test suite (2,586 LoC, 120 tests, 100% passing):
  - `test_model_checker_base.py` (346 LoC, 33 tests)
  - `test_anthropic_checker.py` (327 LoC, 13 tests)
  - `test_openai_checker.py` (359 LoC, 14 tests)
  - `test_google_checker.py` (407 LoC, 14 tests)
  - `test_openrouter_checker.py` (415 LoC, 14 tests)
  - `test_cli_check_models.py` (347 LoC, 16 tests)
  - `test_model_checker_financial.py` (385 LoC, 16 tests, @pytest.mark.financial)
- Bug fix: `services/llm_provider_service/tests/conftest.py` (fixture imports, fixed 23 broken tests)

**Validation Status**:
- ✅ All 227 unit tests passing (100% pass rate)
- ✅ `pdm run typecheck-all` passes (0 errors, 1195 files)
- ✅ All files < 500 LoC hard limit
- ✅ CLI command works: `pdm run llm-check-models --provider <name>`

---

## Your Task: Phase 2.5 - Integration Verification

### Objective

Verify that the model manifest system **integrates correctly** with upstream callers that use the LLM Provider Service:

1. **CJ Assessment Service**: Event-driven comparisons via Kafka
2. **ENG5 Batch Runner**: CLI-driven assessment batches

### Critical Finding from Integration Analysis

**The architecture is already manifest-ready** (discovered during Phase 2 planning). The integration points exist and work:

- ✅ API accepts `llm_config_overrides` with `model_override`, `provider_override`
- ✅ Event contracts (`ELS_CJAssessmentRequestV1`) support `llm_config_overrides`
- ✅ Response callbacks include actual `model` and `provider` metadata
- ✅ ENG5 runner has `--llm-model`, `--llm-provider` CLI flags
- ✅ Zero breaking changes required

**Your job**: Write integration tests that **prove** this works end-to-end and document the integration patterns.

---

## Integration Architecture (Reference)

### Complete Call Chain

```
ENG5 Batch Runner (CLI)
    ↓ (--llm-provider, --llm-model flags)
    └→ _build_llm_overrides() → LLMConfigOverrides
        ↓ (Kafka Event)
ELS_CJAssessmentRequestV1(llm_config_overrides)
    ↓ (consumed by)
CJ Assessment Service - Event Processor
    └→ LLMInteractionImpl.perform_comparisons()
        └→ LLMProviderServiceClient.generate_comparison()
            ↓ (HTTP POST)
LLM Provider Service - /api/v1/comparison
    └→ Provider Implementation (uses model_override)
        └→ Publishes: LLMComparisonResultV1
            ↓ (Kafka Callback)
CJ Assessment Service - Result Handler
```

### Key Integration Points (File:Line)

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **CJ Default Model** | `services/cj_assessment_service/config.py` | 118-121 | Hardcoded default (to deprecate) |
| **CJ Client** | `services/cj_assessment_service/implementations/llm_provider_service_client.py` | 142-158 | Builds `llm_config_overrides` |
| **CJ Orchestration** | `services/cj_assessment_service/implementations/llm_interaction_impl.py` | 85-192 | Passes model/temp/tokens |
| **Event Contract** | `libs/common_core/src/common_core/events/cj_assessment_events.py` | 106-131 | `llm_config_overrides` field |
| **ENG5 CLI Params** | `.claude/research/scripts/eng5_np_batch_runner.py` | 968-985 | `--llm-model`, `--llm-provider` |
| **ENG5 Override Build** | `.claude/research/scripts/eng5_np_batch_runner.py` | 373-395 | `_build_llm_overrides()` |
| **LLM API Endpoint** | `services/llm_provider_service/api/llm_routes.py` | 34-100 | POST /comparison |
| **LLM API Validation** | `services/llm_provider_service/api/llm_routes.py` | 79-90 | Requires `provider_override` |
| **Callback Event** | `libs/common_core/src/common_core/events/llm_provider_events.py` | 111-183 | `LLMComparisonResultV1` |

---

## Deliverables

You must deliver **3 test files + documentation**:

### 1. CJ Assessment Service Integration Tests
**File**: `services/cj_assessment_service/tests/integration/test_llm_provider_manifest_integration.py` (~150-200 LoC)

**Test Coverage**:
- ✅ CJ uses manifest default model when `llm_config_overrides=None`
- ✅ CJ respects assignment-level model override when specified
- ✅ CJ callback events include actual model metadata from response
- ✅ Invalid model IDs are rejected with clear error messages
- ✅ Manifest lookup failures fall back to service default gracefully

**Test Strategy**:
- Use `@pytest.mark.integration` marker
- Mock LLM Provider Service HTTP responses (no real API calls)
- Verify event contracts include correct override structures
- Validate callback parsing extracts model metadata

### 2. ENG5 Batch Runner Integration Tests
**File**: `.claude/research/scripts/tests/test_eng5_np_manifest_integration.py` (~100-150 LoC)

**Test Coverage**:
- ✅ CLI flags (`--llm-model`, `--llm-provider`) validate against manifest
- ✅ Valid model IDs from manifest are accepted
- ✅ Invalid model IDs are rejected before Kafka publishing
- ✅ `_build_llm_overrides()` correctly constructs LLMConfigOverrides
- ✅ Event composition includes override metadata

**Test Strategy**:
- Test CLI validation logic in isolation
- Mock Kafka producer (no actual event publishing)
- Verify manifest validation happens before event composition
- Test error messages guide user to `pdm run llm-check-models`

### 3. Manifest Validation Enhancement (Optional)
**File**: `.claude/research/scripts/eng5_np_batch_runner.py` (add validation function)

**Enhancement**: Add `validate_llm_overrides()` function that:
- Validates `--llm-model` against manifest before publishing
- Logs manifest model metadata (API version, release date)
- Raises `typer.BadParameter` with helpful error for invalid models
- Suggests running `pdm run llm-check-models` to see available models

### 4. Documentation
**File**: `services/llm_provider_service/README.md` (new section: "Integration with Upstream Services")

**Contents**:
- How callers should query manifest for available models
- How to build `LLMConfigOverrides` with selected model
- How to pass via event contract or HTTP API
- How to parse model metadata from response/callback
- Example code snippets for each integration pattern

---

## Process Requirements

### 1. Use Plan Agent for Planning (MANDATORY)

**Before writing any code**, you MUST:

```
Use Task tool with subagent_type=Plan to:
1. Explore existing integration test patterns in the codebase
2. Understand CJ service testing setup (fixtures, mocking patterns)
3. Review ENG5 runner structure and CLI testing approach
4. Identify existing test utilities to reuse
5. Present a detailed plan for user approval
```

### 2. Ask User Questions (MANDATORY)

During planning, use `AskUserQuestion` tool to clarify:

**Required Questions**:
1. **Test Isolation**: Should CJ integration tests mock LLM Provider Service HTTP calls, or use testcontainers to spin up real service?
2. **ENG5 Validation**: Should manifest validation be added to ENG5 runner now, or just write tests that verify current behavior?
3. **Backward Compatibility**: Should tests verify hardcoded defaults still work (for transition period), or only test manifest-based flows?
4. **Documentation Scope**: Should README include migration guide for deprecated hardcoded defaults, or focus only on manifest-first approach?
5. **Coverage Priority**: Which integration point is most critical to test first (CJ event flow vs ENG5 CLI validation)?

**Additional Questions** (if needed):
- Should tests verify specific error messages, or just error types?
- Should CJ tests verify Kafka callback parsing, or just HTTP response?
- Should documentation include code examples for all 4 providers, or focus on Anthropic?

### 3. Validation Before Coding

After planning, verify:
- ✅ Plan addresses all 3 deliverables (2 test files + docs)
- ✅ Test strategy aligns with existing codebase patterns
- ✅ File structure follows HuleEdu conventions
- ✅ All user questions answered and incorporated into plan

---

## Technical Constraints

### Testing Standards (`.claude/rules/075-test-creation-methodology.md`)

- **Markers**: Use `@pytest.mark.integration` for all integration tests
- **Fixtures**: Reuse existing fixtures from `services/cj_assessment_service/tests/fixtures/`
- **Mocking**: Follow established patterns in `services/cj_assessment_service/tests/integration/`
- **Isolation**: Each test must be independent (no shared state)
- **LoC Limit**: Each test file must be < 500 LoC

### Code Quality Requirements

- **Type Safety**: `pdm run typecheck-all` must pass (0 errors)
- **Test Pass Rate**: 100% of new tests must pass
- **Documentation**: Follow `.claude/rules/090-documentation-standards.md`
- **Imports**: Use absolute imports from repo root (no relative imports across service boundaries)

### File Naming Conventions

- Integration tests: `test_*_integration.py`
- Test classes: `TestDescriptiveClassName`
- Test methods: `test_specific_behavior_being_verified`

---

## Success Criteria

Phase 2.5 is complete when:

✅ **CJ Integration Tests**:
- File exists with 5+ tests covering manifest integration
- All tests pass using `pdm run pytest-root <file> -v`
- Tests verify event contracts include correct override structures

✅ **ENG5 Integration Tests**:
- File exists with 5+ tests covering CLI validation
- Tests verify manifest validation happens before Kafka publishing
- Tests demonstrate helpful error messages for invalid models

✅ **Documentation**:
- README section documents integration patterns with code examples
- Integration points clearly explained with file:line references
- Future callers have clear guidance on manifest usage

✅ **Validation**:
- `pdm run typecheck-all` passes (0 errors)
- All integration tests pass (100% pass rate)
- No regressions in existing test suite (227/227 still passing)

✅ **Backward Compatibility**:
- Tests verify hardcoded defaults still work (if user confirms this requirement)
- Zero breaking changes to existing functionality

---

## Reference Documents (READ THESE FIRST)

**Task Document** (CRITICAL - READ FIRST):
```
TASKS/TASK-LLM-MODEL-VERSION-MANAGEMENT.md
```
- See Phase 2.5 section (lines 332-508)
- See Appendix A: Integration Analysis (lines 880-1063)

**Architecture Rules**:
- `.claude/rules/020.13-llm-provider-service-architecture.md`
- `.claude/rules/042-async-patterns-and-di.md`
- `.claude/rules/075-test-creation-methodology.md`
- `.claude/rules/090-documentation-standards.md`

**Implementation Files to Study**:
- `services/cj_assessment_service/implementations/llm_provider_service_client.py`
- `services/cj_assessment_service/implementations/llm_interaction_impl.py`
- `.claude/research/scripts/eng5_np_batch_runner.py`
- `libs/common_core/src/common_core/events/cj_assessment_events.py`
- `libs/common_core/src/common_core/events/llm_provider_events.py`

**Existing Test Patterns to Follow**:
- `services/cj_assessment_service/tests/integration/test_llm_provider_*.py`
- `services/cj_assessment_service/tests/fixtures/`

---

## Starting Instructions

1. **Read the task document**: `TASKS/TASK-LLM-MODEL-VERSION-MANAGEMENT.md`
   - Focus on Phase 2.5 section and Appendix A

2. **Launch Plan agent**:
   ```
   Use Task tool with subagent_type=Plan to explore codebase and create detailed plan
   ```

3. **Ask user questions** using `AskUserQuestion` tool:
   - Test isolation strategy (mocks vs testcontainers)
   - ENG5 validation enhancement scope
   - Backward compatibility requirements
   - Documentation depth

4. **Present plan** using `ExitPlanMode` tool:
   - Detailed breakdown of test files
   - Test coverage strategy
   - Documentation outline
   - Validation steps

5. **Get user approval** before writing any code

6. **Implement** following approved plan

7. **Validate** using success criteria above

---

## Expected Timeline

- **Planning**: 1-2 hours (exploration + questions + plan approval)
- **CJ Tests**: 2-3 hours (150-200 LoC, 5+ tests)
- **ENG5 Tests**: 1-2 hours (100-150 LoC, 5+ tests)
- **Documentation**: 1 hour (README section + examples)
- **Validation**: 30 minutes (typecheck + pytest + review)

**Total**: 1-2 days (6-8 hours focused work)

---

## Begin Now

Start by reading `TASKS/TASK-LLM-MODEL-VERSION-MANAGEMENT.md` and then launch the Plan agent to explore the codebase and ask clarifying questions.

Remember: **No coding until plan is approved by user.**

# Repomix Package Examples

Real-world examples from actual usage in the HuleEdu project.

**See also**:
- **SKILL.md**: Quick reference and activation criteria
- **reference.md**: Detailed templates, workflows, and best practices

## Example 1: Minimal Context Package

**Objective**: Quick context for CJ assessment service overview

**Files Included** (7 files, 24,796 tokens):
- `.claude/research/scripts/eng5_np_batch_runner.py`
- `.claude/research/scripts/test_eng5_np_batch_runner.py`
- `.claude/research/scripts/cj_confidence_analysis.py`
- `.claude/research/scripts/cj_confidence_summary.json`
- `services/cj_assessment_service/kafka_consumer.py`
- `.claude/work/session/handoff.md`
- `.claude/work/session/readme-first.md`

**Command**:
```bash
repomix --style xml --no-gitignore \
  --output .claude/repomix_packages/repomix-cj-assessment-context.xml \
  --include ".claude/research/scripts/eng5_np_batch_runner.py,.claude/research/scripts/test_eng5_np_batch_runner.py,services/cj_assessment_service/kafka_consumer.py,.claude/research/scripts/cj_confidence_analysis.py,.claude/research/scripts/cj_confidence_summary.json,.claude/work/session/handoff.md,.claude/work/session/readme-first.md"
```

**Output**: 96 KB, suitable for initial context loading

**Use Case**: Quickly onboard an AI reviewer to the CJ assessment implementation and research tooling.

---

## Example 2: Comprehensive Code Review Package

**Objective**: Full code review of ENG5 NP batch runner Kafka consumer integration

**Files Included** (29 files, 70,382 tokens):

**Core Implementation**:
- `.claude/research/scripts/eng5_np_batch_runner.py` (5,540 tokens)
- `.claude/research/scripts/test_eng5_np_batch_runner.py`
- `services/cj_assessment_service/kafka_consumer.py` (1,641 tokens)

**Event Contracts**:
- `libs/common_core/src/common_core/events/cj_assessment_events.py`
- `libs/common_core/src/common_core/events/llm_provider_events.py`
- `libs/common_core/src/common_core/event_enums.py`
- `libs/common_core/src/common_core/__init__.py`
- `libs/common_core/src/common_core/events/__init__.py`

**Service Patterns**:
- `services/cj_assessment_service/event_processor.py` (6,020 tokens)
- `services/cj_assessment_service/protocols.py`
- `services/cj_assessment_service/di.py`
- `services/cj_assessment_service/config.py`

**Documentation**:
- `.claude/work/session/handoff.md` (3,488 tokens)
- `.claude/work/session/readme-first.md` (2,727 tokens)
- `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`
- `TASKS/ASSESSMENT_RESULT_ARCHITECTURE_WITH_ANCHORS.md`

**Infrastructure**:
- `libs/huleedu_service_libs/src/huleedu_service_libs/idempotency_v2.py` (3,601 tokens)
- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`

**Rules** (9 files):
- `.claude/rules/000-rule-index.md`
- `.claude/rules/030-event-driven-architecture-eda-standards.md`
- `.claude/rules/042-async-patterns-and-di.md`
- `.claude/rules/043-service-configuration-and-logging.md`
- `.claude/rules/048-structured-error-handling-standards.md`
- `.claude/rules/051-pydantic-v2-standards.md`
- `.claude/rules/052-event-contract-standards.md`
- `.claude/rules/070-testing-and-quality-assurance.md`
- `.claude/rules/075-test-creation-methodology.md`

**Command**:
```bash
repomix --style xml --no-gitignore \
  --output .claude/repomix_packages/repomix-eng5-kafka-review.xml \
  --include ".claude/research/scripts/eng5_np_batch_runner.py,.claude/research/scripts/test_eng5_np_batch_runner.py,services/cj_assessment_service/kafka_consumer.py,libs/common_core/src/common_core/events/cj_assessment_events.py,libs/common_core/src/common_core/events/llm_provider_events.py,libs/common_core/src/common_core/event_enums.py,libs/common_core/src/common_core/__init__.py,libs/common_core/src/common_core/events/__init__.py,services/cj_assessment_service/event_processor.py,services/cj_assessment_service/protocols.py,services/cj_assessment_service/di.py,services/cj_assessment_service/config.py,.claude/work/session/handoff.md,.claude/work/session/readme-first.md,TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md,TASKS/ASSESSMENT_RESULT_ARCHITECTURE_WITH_ANCHORS.md,.claude/research/scripts/cj_confidence_analysis.py,.claude/research/scripts/cj_confidence_summary.json,libs/huleedu_service_libs/src/huleedu_service_libs/idempotency_v2.py,libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py,.claude/rules/000-rule-index.md,.claude/rules/030-event-driven-architecture-eda-standards.md,.claude/rules/042-async-patterns-and-di.md,.claude/rules/043-service-configuration-and-logging.md,.claude/rules/048-structured-error-handling-standards.md,.claude/rules/051-pydantic-v2-standards.md,.claude/rules/052-event-contract-standards.md,.claude/rules/070-testing-and-quality-assurance.md,.claude/rules/075-test-creation-methodology.md"
```

**Output**: 301 KB

**Use Case**: Comprehensive code review focusing on:
- Kafka consumer lifecycle management
- Event filtering by correlation ID
- Artifact hydration logic
- Testing coverage
- Compliance with architectural standards

---

## Example 3: Metadata Flow Analysis Package

**Objective**: Trace metadata propagation from CJ service through LLM provider to result events

**Problem Statement**: `LLMComparisonResultV1` events missing `essay_a_id`, `essay_b_id`, `prompt_sha256` in `request_metadata`

**Files Included** (34 files, 83,682 tokens):

**Core Implementation**:
- `.claude/research/scripts/eng5_np_batch_runner.py` (8,440 tokens) - Where metadata is consumed
- `.claude/research/scripts/test_eng5_np_batch_runner.py`
- `services/cj_assessment_service/kafka_consumer.py`

**Event Contracts**:
- `libs/common_core/src/common_core/events/cj_assessment_events.py`
- `libs/common_core/src/common_core/events/llm_provider_events.py`
- `libs/common_core/src/common_core/event_enums.py`
- `libs/common_core/src/common_core/__init__.py`
- `libs/common_core/src/common_core/events/__init__.py`

**CJ Service - Comparison Request Flow** (7 files):
- `services/cj_assessment_service/event_processor.py` (6,020 tokens)
- `services/cj_assessment_service/implementations/llm_interaction_impl.py` - Where requests are sent
- `services/cj_assessment_service/cj_core_logic/batch_pool_manager.py` (3,814 tokens)
- `services/cj_assessment_service/cj_core_logic/batch_submission_tracking.py`
- `services/cj_assessment_service/cj_core_logic/callback_state_manager.py`
- `services/cj_assessment_service/models_api.py`
- `services/cj_assessment_service/implementations/db_access_impl.py` (3,961 tokens)

**LLM Provider Service - Result Creation** (6 files):
- `services/llm_provider_service/implementations/queue_processor_impl.py` (3,947 tokens) ⭐ **KEY FILE**
- `services/llm_provider_service/protocols.py`
- `services/llm_provider_service/config.py`
- `services/llm_provider_service/internal_models.py`
- `services/llm_provider_service/queue_models.py`
- `services/llm_provider_service/api_models.py`

**Documentation**:
- `.claude/work/session/handoff.md`
- `.claude/work/session/readme-first.md`
- `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`

**Infrastructure**:
- `libs/huleedu_service_libs/src/huleedu_service_libs/idempotency_v2.py`
- `libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py`

**Critical Rules** (6 files):
- `.claude/rules/000-rule-index.md`
- `.claude/rules/042-async-patterns-and-di.md`
- `.claude/rules/048-structured-error-handling-standards.md`
- `.claude/rules/051-pydantic-v2-standards.md`
- `.claude/rules/052-event-contract-standards.md`
- `.claude/rules/075-test-creation-methodology.md`

**Command**:
```bash
repomix --style xml --no-gitignore \
  --output .claude/repomix_packages/repomix-metadata-population-task.xml \
  --include ".claude/research/scripts/eng5_np_batch_runner.py,.claude/research/scripts/test_eng5_np_batch_runner.py,services/cj_assessment_service/kafka_consumer.py,libs/common_core/src/common_core/events/cj_assessment_events.py,libs/common_core/src/common_core/events/llm_provider_events.py,libs/common_core/src/common_core/event_enums.py,libs/common_core/src/common_core/__init__.py,libs/common_core/src/common_core/events/__init__.py,services/cj_assessment_service/event_processor.py,services/cj_assessment_service/implementations/llm_interaction_impl.py,services/cj_assessment_service/cj_core_logic/batch_pool_manager.py,services/cj_assessment_service/cj_core_logic/batch_submission_tracking.py,services/cj_assessment_service/cj_core_logic/callback_state_manager.py,services/cj_assessment_service/protocols.py,services/cj_assessment_service/config.py,services/cj_assessment_service/models_api.py,services/cj_assessment_service/implementations/db_access_impl.py,services/llm_provider_service/implementations/queue_processor_impl.py,services/llm_provider_service/protocols.py,services/llm_provider_service/config.py,services/llm_provider_service/internal_models.py,services/llm_provider_service/queue_models.py,services/llm_provider_service/api_models.py,.claude/work/session/handoff.md,.claude/work/session/readme-first.md,TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md,libs/huleedu_service_libs/src/huleedu_service_libs/idempotency_v2.py,libs/huleedu_service_libs/src/huleedu_service_libs/logging_utils.py,.claude/rules/000-rule-index.md,.claude/rules/042-async-patterns-and-di.md,.claude/rules/048-structured-error-handling-standards.md,.claude/rules/051-pydantic-v2-standards.md,.claude/rules/052-event-contract-standards.md,.claude/rules/075-test-creation-methodology.md"
```

**Output**: 389 KB

**Use Case**: Deep analysis of request→response metadata flow to identify where `essay_a_id`, `essay_b_id`, and `prompt_sha256` should be populated in `LLMComparisonResultV1` events.

**Top Files by Token Count**:
1. `eng5_np_batch_runner.py` - 8,440 tokens (where metadata is consumed)
2. `event_processor.py` - 6,020 tokens (event processing patterns)
3. `db_access_impl.py` - 3,961 tokens (CJ database access)
4. `queue_processor_impl.py` - 3,947 tokens (where LLMComparisonResultV1 is created) ⭐
5. `callback_state_manager.py` - 3,814 tokens (callback tracking)

---

## Key Learnings

### File Selection Strategy

**Files to ADD** when tracing metadata flow:
- Request originators (where data is available)
- Message processors (where data should be threaded through)
- Result creators (where data needs to be populated)
- Event contracts (schema definitions)
- Protocols and models (type definitions)

**Files to REMOVE** when focused on specific problem:
- Large reference data files (e.g., `cj_confidence_summary.json`)
- General architectural docs not relevant to the specific flow
- Broad testing/style rules (keep focused standards like error handling, event contracts)

### Naming Convention Evolution

Session naming pattern:
```
repomix-{feature/service}-{purpose}.xml
```

Examples:
- `repomix-cj-assessment-context.xml` (feature: cj-assessment, purpose: context)
- `repomix-eng5-kafka-review.xml` (feature: eng5, purpose: kafka-review)
- `repomix-metadata-population-task.xml` (feature: metadata-population, purpose: task)

### Token Budget Guidelines

Based on actual usage:
- **Quick Context**: 20-30K tokens (7-10 files)
- **Code Review**: 60-80K tokens (25-35 files)
- **Deep Analysis**: 80-100K tokens (30-40 files)

Most AI models can handle up to 200K tokens, but 70-90K provides good detail without overwhelming the context window.

### Package Evolution

**Session Progression**:
1. Started with minimal context (7 files, 24K tokens)
2. Expanded to full review (29 files, 70K tokens)
3. Refined to targeted analysis (34 files, 83K tokens)

The iteration shows how packages should evolve: start small, identify gaps, expand strategically rather than including everything upfront.

# Lead Architect Review: ENG5 NP Phase 3.3 Data Capture Pipeline

**Date**: 2025-11-09  
**Session Scope**: 3-4 focused hours  
**Context**: Phase 3.3 – Batch Tooling & Data Capture


## 🎯 Review Objective

Validate that the ENG5 NP runner's event-driven pipeline is architecturally complete for a single execute-mode run to emit schema-compliant artefacts without manual patching or missing metadata. This review should confirm the runner is ready for downstream statistical validation (Phase 4) with deterministic inputs/outputs and full observability for LLM cost tracking.

---

## 📋 Critical Review Areas

### 1. Metadata Integrity (Priority: CRITICAL)

**Question**: Does `LLMComparisonResultV1.request_metadata` always carry `essay_a_id`, `essay_b_id`, and `prompt_sha256`?

**Files to Review**:
- `services/cj_assessment_service/implementations/llm_interaction_impl.py` (lines ~150-250)
- `services/llm_provider_service/implementations/queue_processor_impl.py` (lines ~200-350)
- `services/llm_provider_service/implementations/openai_provider.py` (metadata injection)
- `services/llm_provider_service/implementations/anthropic_provider.py` (metadata injection)
- `services/llm_provider_service/implementations/google_provider.py` (metadata injection)
- `services/llm_provider_service/implementations/openrouter_provider.py` (metadata injection)
- `services/llm_provider_service/implementations/mock_provider.py` (metadata injection)

**Validation Checklist**:
- [ ] CJ service injects `essay_a_id` and `essay_b_id` at comparison request creation
- [ ] LLM Provider computes and appends `prompt_sha256` before publishing callbacks
- [ ] Queue processor preserves all metadata fields through the processing pipeline
- [ ] No layer strips or drops optional metadata fields
- [ ] Test coverage exists for metadata propagation (check `test_callback_state_manager*.py`)

**Decision Point**: Should `prompt_sha256` be computed once (at CJ) or re-derived at provider publish time for trust/verification?

---

### 2. Runner Error Handling (Priority: HIGH)

**Question**: Does the runner treat missing metadata as a hard fault with actionable error messages?

**Files to Review**:
- `scripts/cj_experiments_runners/eng5_np/hydrator.py` (`_build_comparison_record` method)
- `scripts/cj_experiments_runners/eng5_np/kafka_flow.py` (`AssessmentEventCollector`)
- `scripts/cj_experiments_runners/eng5_np/cli.py` (exit code handling)

**Validation Checklist**:
- [ ] `_build_comparison_record` raises descriptive exception when metadata is missing
- [ ] Kafka consumer stops consumption if hydrator signals an error
- [ ] CLI propagates errors to exit codes (non-zero on failure)
- [ ] Error messages include correlation_id, essay_ids, and missing field names
- [ ] No silent skips or partial writes to artefacts

**Decision Point**: Should the runner fail-fast on first missing metadata, or collect all errors and report at end?

---

### 3. Artefact Completeness (Priority: HIGH)

**Question**: Does `assessment_run.execute.json` include fully populated sections that align with the schema?

**Files to Review**:
- `Documentation/schemas/eng5_np/assessment_run.schema.json` (ground truth)
- `scripts/cj_experiments_runners/eng5_np/artefact_io.py` (write operations)
- `scripts/cj_experiments_runners/eng5_np/hydrator.py` (section population)
- `scripts/tests/test_eng5_np_runner.py` (schema validation tests)

**Validation Checklist**:
- [ ] `llm_comparisons` section includes all comparison records with metadata
- [ ] `bt_summary` section populated from `AssessmentResultV1` events
- [ ] `grade_projections` section includes per-essay projections with confidence
- [ ] `costs` section tracks provider, model, tokens, and USD amounts
- [ ] `manifest.json` hashes all artefact files with deterministic ordering
- [ ] Schema validation passes for all generated artefacts

**Decision Point**: Which files should be hashed in `manifest.json`? Raw events vs derived artefacts?

---

### 4. Kafka Consumer Strategy (Priority: MEDIUM)

**Question**: Should the runner stop after `AssessmentResultV1` or wait for explicit `CJAssessmentCompletedV1`?

**Files to Review**:
- `scripts/cj_experiments_runners/eng5_np/kafka_flow.py` (`run_publish_and_capture`)
- `scripts/cj_experiments_runners/eng5_np/events.py` (event type definitions)
- `scripts/cj_experiments_runners/eng5_np/settings.py` (timeout configuration)
- `libs/common_core/src/common_core/events/cj_assessment_events.py` (event contracts)

**Validation Checklist**:
- [ ] Consumer subscribes to all three required topics (comparison_result, assessment_result, completed)
- [ ] Timeout behavior prevents hanging sessions (`--completion-timeout` flag)
- [ ] Idempotent writes when events arrive late or out of order
- [ ] Consumer commits offsets only after successful artefact writes
- [ ] Partial data scenarios are handled gracefully (logged + manifest flag)

**Decision Point**: What's the timeout strategy? Fixed duration, or dynamic based on batch size?

---

### 5. Observability & Monitoring (Priority: MEDIUM)

**Question**: Which metrics/logs confirm metadata coverage and artefact hydration?

**Files to Review**:
- `services/cj_assessment_service/metrics.py` (Prometheus counters)
- `Documentation/OPERATIONS/01-Grafana-Playbook.md` (dashboard panels)
- `scripts/cj_experiments_runners/eng5_np/cli.py` (runner logging)
- `scripts/cj_experiments_runners/eng5_np/hydrator.py` (cost summaries)

**Validation Checklist**:
- [ ] `huleedu_llm_prompt_fetch_failures_total` tracks prompt hydration failures
- [ ] `cj_admin_instruction_operations_total` tracks admin API usage
- [ ] Runner emits structured logs with correlation_id, batch_id, essay counts
- [ ] Cost summaries logged per provider/model at completion
- [ ] Prompt hash statistics logged (unique prompts, hash collisions)
- [ ] Grafana panels exist for ENG5 runner metrics

**Decision Point**: Should runner metrics be pushed to Prometheus, or only logged?

---

### 6. Operational Runbook (Priority: MEDIUM)

**Question**: Is there a documented checklist for executing `pdm run eng5-np-run --mode execute`?

**Files to Review**:
- `services/cj_assessment_service/README.md` (admin setup section)
- `Documentation/OPERATIONS/01-Grafana-Playbook.md` (ENG5 monitoring)
- `scripts/cj_experiments_runners/eng5_np/cli.py` (CLI help text)

**Validation Checklist**:
- [ ] Docker pre-checks documented (required services, health endpoints)
- [ ] Environment sourcing steps (`.env` variables, Kafka bootstrap)
- [ ] Kafka consumer lag monitoring instructions
- [ ] Artefact validation commands (schema check, manifest verify)
- [ ] Troubleshooting guide for common failures (missing metadata, timeout, schema errors)

**Decision Point**: Where should the runbook live? Service README or Operations playbook?

---

## 🔍 Architectural Compliance Review

### Rule Adherence Checklist

- [ ] **Rule 020 (Architectural Mandates)**: Runner uses contract-only integration (no direct DB access)
- [ ] **Rule 020.7 (CJ Service)**: Metadata propagation follows established patterns
- [ ] **Rule 037.1 (Phase Processing)**: Event flow aligns with phase state machine
- [ ] **Rule 048 (Error Handling)**: Structured errors with correlation IDs
- [ ] **Rule 071 (Observability)**: Metrics, logs, and traces for all critical paths
- [ ] **File Size Limit**: All runner modules < 500 LoC

### Integration Points to Verify

1. **CJ → LLM Provider**: Metadata preserved through queue/job layers
2. **LLM Provider → Runner**: Callbacks include all required fields
3. **Runner → Artefacts**: Schema-compliant JSON with validation
4. **Runner → Kafka**: Consumer offset management and idempotency

---

## 📊 Package Contents Summary

**Total**: 92,418 tokens across 36 files

### Core Runner Package (13 files)
- `cli.py`, `kafka_flow.py`, `hydrator.py`, `artefact_io.py`, `events.py`, `requests.py`, `paths.py`, `settings.py`, `inventory.py`, `schema.py`, `environment.py`, `utils.py`, `__init__.py`

### Service Implementations (7 files)
- CJ: `llm_interaction_impl.py`, `callback_state_manager.py`, `metrics.py`, `config.py`, `README.md`
- LLM Provider: `queue_processor_impl.py`, 5 provider implementations

### Event Contracts (3 files)
- `cj_assessment_events.py`, `llm_provider_events.py`, `event_enums.py`

### Tests (3 files)
- `test_eng5_np_runner.py`, `test_callback_state_manager.py`, `test_callback_state_manager_extended.py`, `test_llm_provider_manifest_integration.py`

### Documentation (5 files)
- Task docs, HANDOFF, README_FIRST, schema, operations playbook

### Architecture Rules (5 files)
- Rules 020, 020.7, 037.1, 048, 071

---

## 🚨 Known Risks & Mitigations

### Risk 1: Partial Event Capture
**Symptom**: Kafka callbacks arrive late, artefacts miss comparisons  
**Mitigation**: Add `completion_timeout` telemetry + rerun guidance  
**Review Action**: Verify timeout handling in `kafka_flow.py`

### Risk 2: Schema Drift
**Symptom**: Multiple contributors editing schema/runner independently  
**Mitigation**: Enforce `jsonschema` validation in runner tests  
**Review Action**: Confirm test coverage in `test_eng5_np_runner.py`

### Risk 3: Cost Overruns
**Symptom**: Execute mode hits real LLMs unexpectedly  
**Mitigation**: Ensure `--no-kafka` and mock toggles are clearly documented  
**Review Action**: Verify CLI help text and README warnings

---

## ✅ Desired Outcomes

By end of this review session, we should have:

1. **Confirmed Metadata Integrity**: All three required fields (`essay_a_id`, `essay_b_id`, `prompt_sha256`) propagate end-to-end
2. **Validated Error Handling**: Runner fails fast with actionable messages on missing metadata
3. **Schema Compliance**: Generated artefacts pass validation against `assessment_run.schema.json`
4. **Operational Readiness**: Documented runbook for execute mode with monitoring hooks
5. **Architectural Approval**: Green light for Phase 4 statistical validation

---

## 📝 Review Deliverables

Please provide:

1. **Approval Status**: ✅ Approved / ⚠️ Approved with Conditions / ❌ Requires Changes
2. **Critical Issues**: List any blocking issues that must be fixed before Phase 4
3. **Recommendations**: Suggested improvements (non-blocking)
4. **Decision Log**: Answers to all "Decision Point" questions above
5. **Next Steps**: Specific implementation tasks if changes required

---

## 🔗 Related Documents

- **Parent Task**: `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`
- **Mathematical Validation**: `TASKS/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`
- **Session Context**: `.claude/work/session/handoff.md` (Phase 3.2/3.3 completion status)
- **Architecture Rules**: `.windsurf/rules/020-architectural-mandates.md`

---

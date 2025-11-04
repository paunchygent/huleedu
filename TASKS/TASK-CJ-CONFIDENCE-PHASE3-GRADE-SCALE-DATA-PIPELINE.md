# Task Plan: Phase 3 – Grade Scale Enablement & Data Capture

## Executive Summary
- **Purpose**: Extend CJ Assessment to support ENG5 NP grade scales and generate reproducible comparison datasets for empirical validation.
- **Scope**: Service-side grade-scale registry + API integration, helper/CLI updates, and ENG5 NP 2016 batch execution with structured JSON outputs.
- **Integration Context**: Feeds the mathematical validation effort (`TASKS/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`) by supplying scale-aware confidence data without polluting production databases.

## Architectural Alignment
- **Core mandates**: `.claude/rules/020-architectural-mandates.mdc`, `.claude/rules/020.7-cj-assessment-service.mdc`, `.claude/rules/037.1-cj-assessment-phase-processing-flow.mdc`
- **Shared contracts**: `.claude/rules/020.4-common-core-architecture.mdc`
- **Async/DI patterns**: `.claude/rules/042-async-patterns-and-di.mdc`
- **Error handling**: `.claude/rules/048-structured-error-handling-standards.mdc`
- **Testing & QA**: `.claude/rules/070-testing-and-quality-assurance.mdc`, `.claude/rules/075-test-creation-methodology.mdc`
- **Observability**: `.claude/rules/071-observability-index.mdc`
- **Planning methodology**: `.claude/rules/110.7-task-creation-and-decomposition-methodology.mdc`

## Phase Breakdown

### Phase 3.1 – Grade Scale Foundations *(Completed 2025-11-04)*
- **Deliverables (✅)**
  - Registry metadata for Swedish + ENG5 NP scales with helper utilities.
  - Alembic migration + ORM/Pydantic updates threading `grade_scale` across instructions, anchors, projections.
  - Scale-aware anchor API, batch preparation, context builder, and GradeProjector with updated unit coverage.
- **Implementation Notes**
  - `assessment_instructions.grade_scale` now authoritative; anchors filtered per assignment scale.
  - GradeProjector emits `grade_scale`, boundary diagnostics, and primary anchor grade in stored metadata.
  - Anchor registration responses include the resolved scale for client awareness.
- **Follow-ups**
  - Documentation refreshed (README updated 2025-11-04); CLI helper refresh scheduled for Phase 3.2 alongside ENG5 NP tooling.

### Phase 3.2 – Service Integration
- **Deliverables**
  - Admin-facing endpoint or CLI command to register/update `assessment_instructions` (assignment metadata + `grade_scale`).
  - Anchor API (`services/cj_assessment_service/api/anchor_management.py`) accepts/validates `grade_scale`.
  - `GradeProjector`, `ContextBuilder`, and related calibrators consume scale metadata.
  - Helper CLI (`.claude/agents/...` or existing helper script) exposes `--grade-scale` flags + inventory mode.
- **Steps**
  1. Design and implement an authenticated admin route that accepts `assignment_id`, `course_id`, `instructions_text`, and `grade_scale`, validating the scale against the registry before persisting to `assessment_instructions`.
  2. Update API request models & handlers to persist scale by resolving `assignment_id` metadata (instructions table); enforce structured error responses (rule 048).
  3. Propagate scale through DI wiring, ensuring Dishka scopes remain correct (rule 042).
  4. Extend helper CLI (keeping in sync with repo tooling rules 080) for scale-aware anchor management, including convenience commands to seed assignment instructions where appropriate.
- **Checkpoints**
  - Unit tests covering ENG5 legacy vs national scale flows (no behavioral drift).
  - Helper smoke test against dev stack confirming validation/inventory commands.
- **Done Definition**
  - Anchor registration rejects invalid grades with structured errors.
  - Grade projector outputs include scale metadata in projection summaries/events.
  - Observability metrics/traces confirm scale data propagates (rule 071).

### Phase 3.3 – Batch Tooling & Data Capture
- **Deliverables**
  - CLI/module (`.claude/research/scripts` or service CLI) to run ENG5 NP batches without persisting essays to prod DB.
  - JSON schema implemented at `.claude/research/data/eng5_np_2016/assessment_run.json`.
  - Stored artefacts: comparisons, BT stats, grade projections, metadata (instructions, prompts, correlation IDs).
- **Steps**
  1. Build ingestion runner leveraging new scale registry; load essays/anchors from `test_uploads/...`.
  2. Launch dev Docker stack (rule 080) and execute CJ pipeline with full instructions/prompt metadata.
  3. Serialize outputs to machine-readable JSON (per agreed schema), ensuring integrity checksums recorded.
- **Checkpoints**
  - CLI dry-run against mock essays verifying schema compliance.
  - ENG5 NP batch completes with captured results ready for Phase 3 analysis.
- **Done Definition**
  - JSON artefacts versioned + documented.
  - LLM cost tracked (metadata) for auditing.
  - Integration tests confirm CLI does not mutate persistent DB state.

## Dependencies & Integration
- **Prerequisites**: Phase 2 theoretical model (already complete) informs boundary-stay probability outputs.
- **Downstream**: Phase 4 will consume the JSON artefacts for confidence refactor/testing.
- **Cross-Service Touchpoints**: Content Service (for essay retrieval), LLM provider configuration (prompt overrides), Event contracts from `common_core.events.cj_assessment_events`.

## Success Criteria
- Grade-scale metadata fully configurable; existing tests updated/passing.
- ENG5 NP batch run reproducible locally; JSON artefacts align with schema.
- Documentation refreshed (`services/cj_assessment_service/README.md`, helper docs).

## Risks & Mitigation
- **Risk**: Legacy anchors missing scale metadata -> Provide backfill script/default.
- **Risk**: CLI inadvertently writing to production DB -> Use isolated storage, feature-flag, and unit/integration tests.
- **Risk**: LLM cost overruns -> Capture provider usage stats in metadata for audit.

## Reference Materials
- `.claude/rules/020.7-cj-assessment-service.mdc`
- `.claude/rules/037.1-cj-assessment-phase-processing-flow.mdc`
- `.claude/rules/020.4-common-core-architecture.mdc`
- `.claude/rules/042-async-patterns-and-di.mdc`
- `.claude/rules/048-structured-error-handling-standards.mdc`
- `.claude/rules/070-testing-and-quality-assurance.mdc`
- `.claude/rules/075-test-creation-methodology.mdc`
- `.claude/rules/071-observability-index.mdc`
- `.claude/rules/110.7-task-creation-and-decomposition-methodology.mdc`
- `.claude/rules/080-repository-workflow-and-tooling.mdc`

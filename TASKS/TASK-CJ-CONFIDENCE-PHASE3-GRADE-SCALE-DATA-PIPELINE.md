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

### Phase 3.1 – Grade Scale Foundations
- **Deliverables**
  - `grade_scales.py` (or equivalent) defining `eng5_np_legacy_9_step`, `eng5_np_national_9_step` metadata (ordering, labels, priors).
  - Database migration adding `grade_scale` columns to anchor/projection tables; ORM/Pydantic updates.
- **Steps**
1. Design scale metadata structure (names, ordinal indices, display labels, optional priors).  
    - `eng5_np_legacy_9_step` grade codes: `["F+", "E-", "E+", "D-", "D+", "C-", "C+", "B", "A"]` (anchor IDs like `F+1`, `F+2`, `B1`, `B2` map to these codes; essays below `F+` treated as `F`).  
    - `eng5_np_national_9_step` ordered grades: `["1", "2", "3", "4", "5", "6", "7", "8", "9"]`.
  2. Implement shared registry consumed by service + helper; ensure no reinvention of existing logic (reuse current anchor helpers).
  3. Create Alembic migration + data models changes; maintain backward compatibility (default existing anchors to `swedish_8_anchor` until deprecation).
- **Checkpoints**
  - Metadata review signed off (no missing grades, naming aligned with ENG5 NP variants).
  - Migration validated locally (`pdm run pytest-root`, `pdm run typecheck-all` per rule 070).
- **Done Definition**
  - Registry module unit-tested for lookup/validation behavior.
  - Migration generates new columns with defaults; CI scripts green.

### Phase 3.2 – Service Integration
- **Deliverables**
  - Anchor API (`services/cj_assessment_service/api/anchor_management.py`) accepts/validates `grade_scale`.
  - `GradeProjector`, `ContextBuilder`, and related calibrators consume scale metadata.
  - Helper CLI (`.claude/agents/...` or existing helper script) exposes `--grade-scale` flags + inventory mode.
- **Steps**
  1. Update API request models & handlers to persist scale by resolving `assignment_id` metadata (instructions table); enforce structured error responses (rule 048).
  2. Propagate scale through DI wiring, ensuring Dishka scopes remain correct (rule 042).
  3. Extend helper CLI (keeping in sync with repo tooling rules 080) for scale-aware anchor management.
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

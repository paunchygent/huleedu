# Handoff: Mathematical Validation of CJ Confidence Calculations

**Date**: 2025-11-04
**From**: Codex (CJ Confidence Validation Session)
**To**: Next Assistant / Maintainer
**Task**: `TASKS/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`


## Session Summary (2025-11-08) – Prompt Reference Validation & Documentation

**Status:** Phase 3.2 prompt architecture is fully reference-native across BOS, ELS, NLP, CJ, and Gateway callers. Documentation/tests updated to block regressions.

### What Changed Today
- Scoped Phase 3.3 deliverables: documented the ENG5 NP runner/CLI, data-source mapping, validation plan, and JSON artefact manifest requirements in `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md` (see new “Phase 3.3 Detailed Scope” section) and published the draft schema at `Documentation/schemas/eng5_np/assessment_run.schema.json`.
- Consolidated the legacy `docs/` directory into structured `Documentation/` subtrees (`apis/`, `guides/`, `research/`, `adr/`) and updated all references/scripts so contributors have a single canonical location per documentation category.
- Updated Phase 3.2 task plan, discovery notes, and child migration tracker to reflect completed work; removed references to legacy `essay_instructions` bridging.
- Refreshed `.claude/HANDOFF.md` and TASK logs with the new validation baseline plus remaining fixture-only follow-ups.
- Converted API Gateway + BOS unit suites to use `student_prompt_ref`, ensuring tests now fail if inline prompts reappear.
- Added shared test helper for prompt references (`services/batch_orchestrator_service/tests/__init__.py::make_prompt_ref`) and rewired every BOS test fixture/contract instantiation to rely on Content Service references.
- Ran targeted validations:
  - `pdm run pytest-root services/api_gateway_service/tests/test_batch_registration_proxy.py`
  - `pdm run pytest-root services/batch_orchestrator_service/tests -k "prompt or idempotency or batch_context"`

### Validation / Tooling
- BOS + API Gateway pytest targets above now pass with the new prompt reference fixtures.

### Outstanding Follow-Ups
- Result Aggregator functional fixtures still include legacy prompt text; update alongside AI Feedback notebook refresh so integration tests assert on `student_prompt_ref`.
- Monitor AI Feedback and downstream analytics notebooks to ensure they consume `student_prompt_ref` once their datasets are regenerated (tracked in parent plan).

---

### Dev Docker Shared Deps ✅ COMPLETED (2025-11-07)
- Created `Dockerfile.deps`, `scripts/compute_deps_hash.py`, and `scripts/update_service_dockerfiles.py` so every service builds atop a hashed dependency layer injected via `DEPS_IMAGE_TAG` in `docker-compose.dev.yml`.
- Validated with `pdm run dev-build-clean <service>` followed by `docker compose exec <service> curl .../healthz` (content_service, class_management_service, email, entitlements, identity, language_tool).
- Outcome: dependency installs now happen once per hash; routine `pdm run dev-build` reuses the cached deps layer, cutting rebuild time.

### Prompt Reference Migration – Documentation & Validation ✅ COMPLETED (2025-11-06)
- Refreshed downstream docs (`services/nlp_service/README.md`, `services/cj_assessment_service/README.md`, `Documentation/OPERATIONS/01-Grafana-Playbook.md`) and task trackers to describe the reference-only flow plus new metrics.
- Validation commands:  
  `pdm run pytest-root services/result_aggregator_service/tests/unit/test_event_processor_impl.py::TestProcessBatchRegistered::test_successful_batch_registration -q`  
  `pdm run pytest-root services/essay_lifecycle_service/tests/unit/test_nlp_command_handler.py -q`
- Residual: Result Aggregator fixtures / AI Feedback notebook still need prompt-ref updates (retained in Outstanding Follow-Ups above).

### CJ Service Prompt Hydration ✅ COMPLETED (2025-11-06)
- CJ service now hydrates prompts locally, logs `huleedu_cj_prompt_fetch_failures_total{reason=…}`, stores prompt metadata, and ships Alembic migration `20251106_1845_make_cj_prompt_nullable.py`.
- Tests: `pdm run pytest-root services/cj_assessment_service/tests -k 'event_processor or batch_preparation'` plus `pdm run typecheck-all`.
- Follow-ups: documentation handled in Step 5 summary; dashboards should chart the new CJ metric.

### NLP Service Prompt Hydration ✅ COMPLETED (2025-11-06)
- `batch_nlp_analysis_handler`, event publisher, and metrics now pull prompt text via Content Service, emit `huleedu_nlp_prompt_fetch_failures_total`, and forward optional `prompt_storage_id`.
- Tests: `pdm run pytest-root services/nlp_service/tests -k batch_nlp_analysis_handler`.
- Follow-up addressed by Step 4 once CJ migrated; AI Feedback remains the last inline consumer.

### ELS Dispatcher Refactor ✅ COMPLETED (2025-11-05)
- `BatchNlpProcessingRequestedV2` / `ELS_CJAssessmentRequestV1` converted to reference-only contracts; dispatcher no longer hydrates prompts, and `huleedu_els_prompt_fetch_failures_total` was retired.
- Tests: `pdm run pytest-root services/essay_lifecycle_service/tests/unit/test_nlp_command_handler.py`, `...test_cj_assessment_command_handler.py`, `...test_kafka_circuit_breaker_business_impact.py`.
- Child execution plan (`TASK-PHASE-3.2-PROMPT-ARCHITECTURE-IMPLEMENTATION.child-prompt-reference-consumer-migration.md`) tracks the downstream migrations that followed.

### Phase 3.1 – Grade Scale Registry ✅ COMPLETED (2025-11-04)
- Delivered ENG5 NP-aware registry (`libs/common_core/.../grade_scales.py`), CJ service migrations (models, API, GradeProjector), and alembic updates threading `grade_scale` through `assessment_instructions`, anchors, and projections.
- Tests: refreshed CJ unit suites plus registry-focused coverage (`libs/common_core/tests/test_grade_scales.py`); database migrations verified via psql + CI.
- Next actions captured in the parent plan: finalize documentation/CLI notes, proceed to Phase 3.2/3.3 execution.

2. ✅ **Unit Tests** (`libs/common_core/tests/test_grade_scales.py` - 365 LoC):
   - 59 behavioral tests (all passing)
   - Comprehensive coverage: scale validation, error cases, edge cases
   - Parametrized tests for all three scales

3. ✅ **Database Migration** (revision: `bf559b4a86bf`):
   - Added `grade_scale` column to `anchor_essay_references` and `grade_projections`
   - Type: `String(50)`, default: `swedish_8_anchor`, indexed
   - Migration applied and verified via psql
   - File: `services/cj_assessment_service/alembic/versions/20251103_2222_bf559b4a86bf_add_grade_scale_columns.py`

4. ✅ **ORM Models Updated** (`services/cj_assessment_service/models_db.py`):
   - `AnchorEssayReference.grade_scale` field added
   - `GradeProjection.grade_scale` field added
   - Type checking passes (pdm run typecheck-all: Success)

### Phase 3.1 Completion Highlights

- ✅ `RegisterAnchorRequest` extended; API now resolves assignment grade scale and validates grades against the registry.
- ✅ Repository/context builder expose `grade_scale`; anchor queries filter by scale; batch preparation pulls scale-aware anchors.
- ✅ `GradeProjector` rewritten to consume registry metadata, derive priors/boundaries per scale, and persist scale diagnostics.
- ✅ Unit suites refreshed (`test_anchor_management_api_core.py`, `test_grade_projector_swedish.py`, `test_grade_projector_system.py`), all passing.
- ✅ Alembic migration `f83f2988a7c2` applied and verified (`assessment_instructions.grade_scale`).
- ✅ Mock repository/test helpers updated to register assignment contexts explicitly; tests now assert emitted `grade_scale`.

### Configuration Decisions (User-Confirmed):
- ENG5 NP Legacy: `F+, E-, E+, D-, D+, C-, C+, B, A` (below F+ → F, uniform priors 1/9)
- ENG5 NP National: `1-9` (below 1 → 0, uniform priors 1/9)
- CLI tooling deferred to Phase 3.2
- Backward compatibility: Swedish 8-anchor remains default
- Assignment metadata (instructions table) is the source of truth for `grade_scale`; anchor registration and grade projection must resolve scale via `assignment_id` rather than trusting client input.

### Quality Gates Met:
- All tests passing (59 new + existing)
- Type checking clean (1171 files)
- Migration applied successfully
- Files under 500 LoC limit
- Database schema verified

### Next Session Tasks:
1. Refresh documentation/CLI notes for scale-aware workflows (Phase 3.1 Step 10 follow-up).
2. Plan and execute Phase 3.2 (ENG5 NP batch tooling + data capture).
3. Begin preparation for Phase 3.3 JSON artefact pipeline once ENG5 NP batch runner is ready.

### Phase 3.2 Planning Outline (for next session)
1. **Admin Assignment Management**
   - Design authenticated API/CLI for creating/updating `assessment_instructions` (fields: `assignment_id`, `course_id`, `instructions_text`, `grade_scale`).
   - Coordinate with Class Management/BOS teams so the owning service exposes assignment metadata consistently.
2. **Assess ENG5 NP Instruction Seeding**
   - Verify migration/tooling to seed ENG5 NP 2016 instructions via the new admin interface.
   - Define repeatable workflow to toggle `grade_scale` between Swedish default and ENG5 variants.
3. **CLI/Automation Enhancements**
   - Extend anchor helper CLI (or create dedicated Typer command) to surface available scales, seed assignments via the new admin route, and register anchors.
   - Document invocation patterns (assignment lookup, grade validation errors, scale inventory).
4. **ENG5 NP Batch Runner Design**
   - Decide on execution surface (`scripts/bayesian_consensus_model` vs. service CLI) and environment isolation.
   - Enumerate required artefacts (essay registry, anchor payloads, comparison outputs, BT stats, projection export).
5. **Data Capture Schema Finalization**
   - Confirm JSON schema fields for `.claude/research/data/eng5_np_2016/*` (metadata, comparisons, calibration info).
   - Map service events/logs to schema inputs; note additional instrumentation needs if gaps exist.
6. **Testing & Observability Plan**
   - Identify target unit/integration tests for ENG5 NP scale flows (including new admin endpoint).
   - Outline metrics/log updates to trace scale propagation during batch runs.

---

## Session Summary (2025-11-07) - Phase 2 Theoretical Validation

- Phase 1 research inputs are complete: core service files reviewed, initial analytical tooling created, and the expanded literature set (Pollitt 2012 through Kinnear et al. 2025) summarised in `.claude/research/CJ-CONFIDENCE-VALIDATION.md`.
- Phase 2 theoretical work captured in the same notebook: Fisher-information derivation, SE → boundary probability mapping, audit notes for `compute_bt_standard_errors`, and the planned factor-weight sensitivity analysis.
- Baseline analysis scripts (`cj_confidence_analysis.py`, `test_cj_confidence_analysis.py`) reproduce production heuristics and generate comparison tables for theoretical benchmarking.
- Existing empirical logs are single-essay rating records (58 assessments for 12 essays) – **no pairwise CJ comparisons currently exist**, so fresh CJ batches must be executed via the CJ Assessment Service to collect comparison data for validation.
- Phase 3 implementation plan recorded in `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`, outlining grade-scale registry work, service integration, and ENG5 NP batch tooling per rule 110.7.
- Grade-scale implementation will introduce `eng5_np_legacy_9_step` (grade codes `F+, E-, E+, D-, D+, C-, C+, B, A`; anchor IDs such as `F+1`, `F+2` map to the same `F+` code, essays below `F+` treated as `F`) and `eng5_np_national_9_step` (ordered `1`–`9`); SV3’s multi-aspect scale is deferred. Legacy anchors remain on the current Swedish 8-grade default until migration.
- ENG5 NP 2016 artefacts: student essays (`test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays/`), anchors from `scripts/bayesian_consensus_model/d_optimal_workflow/models.py::DEFAULT_ANCHOR_ORDER`, exam instructions (`.../eng5_np_vt_2017_essay_instruction.md`), LLM comparison prompt (`.../llm_prompt_cj_assessment_eng5.md`).
- Phase 3 data capture will persist machine-readable JSON bundles under `.claude/research/data/eng5_np_2016/` (metadata, essay registry, comparisons, BT stats, grade projections) to avoid repeated LLM runs.
- Progress and research notebooks have been refreshed with the new findings; ready to proceed into grade-scale implementation and data generation.

Outstanding next steps:
1. Execute Phase 3.1 (grade-scale registry + migrations) per `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`.
2. Update CJ anchor API, GradeProjector, and helper CLI for scale awareness (Phase 3.2).
3. Build/run the ENG5 NP ingestion CLI, capture outputs using the agreed JSON schema (Phase 3.3), then move to confidence recalibration/testing (Phase 4).

---

## Why You're Doing This Task

### Mathematical Validation Context (reference)

The full research brief (success criteria, deliverables, proof requirements, and data sources) lives in:

- `TASKS/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`
- `.claude/research/CJ-CONFIDENCE-VALIDATION.md`
- `.claude/research_prompts/RESEARCH_PROMPT_CJ_ANCHOR_PAIRING.md`

Key reminders for future work:
- Validate/replace the logistic thresholds in `confidence_calculator.py` via Fisher Information + Session 1 data.
- Produce proofs and runnable scripts under `.claude/research/scripts/`, documenting results in the research notebook.
- Compare at least three external CJ frameworks before recommending changes.

This handoff now tracks only the engineering phases (3.1–3.3) and outstanding prompt-reference migrations; consult the docs above for the complete mathematical task description.

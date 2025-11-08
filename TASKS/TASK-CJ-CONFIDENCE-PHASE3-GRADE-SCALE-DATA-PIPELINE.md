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
  - JSON schema implemented at `Documentation/schemas/eng5_np/assessment_run.schema.json` (runner copies this into `.claude/research/data/eng5_np_2016/` alongside generated artefacts).
  - Stored artefacts: comparisons, BT stats, grade projections, metadata (instructions, prompts, correlation IDs).
- ✅ Initial scaffold complete: `pdm run eng5-np-run --mode plan|dry-run|execute` (see `.claude/research/scripts/eng5_np_batch_runner.py`). Execute now generates schema artefacts, writes a typed `ELS_CJAssessmentRequestV1` envelope, publishes it via `KafkaBus` (unless `--no-kafka`), accepts LLM overrides, and can optionally wait for `CJAssessmentCompleted` events for the batch.
- 🔄 Architecture decision (2025-11-08): The runner will observe `huleedu.llm_provider.comparison_result.v1`, `huleedu.cj_assessment.completed.v1`, and the rich `AssessmentResultV1` topic with a scoped consumer instead of querying CJ storage. Callbacks are filtered by the batch correlation ID and persisted under `.claude/research/data/eng5_np_2016/events/…`, and the JSON artefact’s `llm_comparisons`, `bt_summary`, `grade_projections`, and `costs` sections will be hydrated from those events. This keeps Phase 3.3 compliant with rule 020 (contract-only communication) and reuses CJ’s existing observability payloads for cost/token tracking.
- ✅ Implementation (2025-11-08 evening): `AssessmentEventCollector` + `AssessmentRunHydrator` now live inside `.claude/research/scripts/eng5_np_batch_runner.py`. Execute mode spins up the consumer before publishing, writes raw events into `events/comparisons|assessment_results|completions`, and rewrites `assessment_run.execute.json` with LLM comparison entries, BT summaries, grade projections, and rolling cost totals. The validation manifest now hashes every stored event/request artefact. Tests cover the hydrator behaviors.
- 📌 Follow-up: Relocate the runner to `scripts/cj_experiments_runners/eng5_np_batch_runner.py` and split logistics into SRP-friendly modules (`cli.py`, `collector.py`, `hydrator.py`, etc.) so future ENG5/ENG6 runners can share components without bloating a single script.
- 📌 Follow-up: Ensure CJ service populates `essay_a_id`, `essay_b_id`, and `prompt_sha256` inside every `LLMComparisonResultV1.request_metadata` entry. Until then the runner skips callbacks missing these fields to avoid corrupting `llm_comparisons` per schema requirements.
- ✅ Metadata echo-back (2025-11-08): CJ’s `LLMInteractionImpl`/provider client now send `essay_a_id`/`essay_b_id` in the metadata for each comparison request, and the LLM Provider (all concrete providers + queue processor) computes and appends `prompt_sha256` before publishing callbacks. Tests cover the CJ client, interaction unit suite, and provider callback publisher.
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

#### Phase 3.3 Detailed Scope (2025-11-08)

**Runner / CLI (`.claude/research/scripts/eng5_np_batch_runner.py`)**
- PDM entrypoint (`pdm run eng5-np-run --assignment-id ...`) that shells into the repo root per rule 080 and accepts three modes: `plan` (prints assets/cost estimate), `dry-run` (generates payloads + JSON only), and `execute` (publishes `ELS_CJAssessmentRequestV1` events and tails the batch until `CJAssessmentCompletedV1`).
- Loads grade-scale metadata from the registry introduced in Phase 3.1, defaulting to `eng5_np_legacy_9_step` while allowing overrides via `--grade-scale`.
- Pulls anchors, student essays, prompt references, and instruction markdown from `test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/**`, emitting structured diagnostics if any file is missing or unsupported.
- Streams comparison callbacks to an artefact builder that records each comparison (`winner`, `loser`, `llm_provider`, `cost`) plus derived Bradley–Terry stats and the final GradeProjector output.
- Execute mode now composes a full `ELS_CJAssessmentRequestV1` envelope (prompt references, course metadata, assignment context), stores it under `.claude/research/data/eng5_np_2016/requests/`, publishes it through `KafkaBus` unless `--no-kafka` is supplied (Kafka bootstrap/client id configurable), and can tail `huleedu.cj_assessment.completed.v1` to capture completion metadata (`--await-completion`, `--completion-timeout`).
- Provides `--no-kafka` flag for offline fixture generation so we can unit-test ingestion logic without touching Kafka.

**Data Sources & Preflight**
- Instructions: `eng5_np_vt_2017_essay_instruction.md` drives assignment metadata and is embedded verbatim into batch context.
- Prompt references: `llm_prompt_cj_assessment_eng5.md` supplies the rubric and JSON instructions fed to the LLM provider.
- Anchors: `ANCHOR_ESSAYS_BAYESIAN_INFERENCE_DATA.(csv|xlsx)` map anchor IDs to grade labels and file names; runner cross-validates these entries with files under `anchor_essays/`.
- Student submissions: `.docx` payloads in `student_essays/` become essay refs; each file is tagged with a deterministic `essay_id` and checksum for reproducibility.
- Default anchor ordering: `scripts/bayesian_consensus_model/d_optimal_workflow/models.py::DEFAULT_ANCHOR_ORDER` seeds the runner’s anchor sequence to stay aligned with the Bayesian tooling.
- Preflight script verifies Docker Compose state (`pdm run dev-ps | grep huleedu_cj_assessment_service`), ensures `USE_MOCK_LLM` toggles match the chosen mode, and requires `.env` to be sourced before executing cost-bearing runs.

**JSON Artefact Schema (`Documentation/schemas/eng5_np/assessment_run.schema.json`)**
- Top-level sections: `metadata` (assignment, runner version, timestamps, git SHA), `inputs` (instructions, prompt reference, grade scale, anchor roster, student registry), `llm_comparisons` (ordered list with prompt hash + provider cost), `bt_summary` (per-essay θ, standard error, rank, anchor flags), `grade_projections` (GradeProjector payload echoing service output), `costs` (token + USD by provider), and `validation` (checksums, schema version, CLI mode).
- Each section will contain `schema_version` so later analyses can detect incompatible artefacts; plan to start at `1.0.0`.
- Artefact builder writes a `manifest.json` containing relative paths and SHA256 digests for every generated file to guard against tampering.

**Validation & Testing Strategy (Rules 070/075)**
- Unit tests (`pdm run pytest-root .claude/research/scripts/tests/test_eng5_np_batch_runner.py -q`) cover ingest transforms, CLI flag parsing, and schema validation using synthetic essay fixtures under `.claude/research/scripts/tests/fixtures`.
- Contract tests validate the JSON schema by round-tripping a fixture through `jsonschema.validate` plus our dataclass loader before and after serialization.
- Integration smoke (`pdm run pytest-root services/cj_assessment_service/tests/integration/test_eng5_np_runner.py -m "not slow"`) spins up the runner in `--no-kafka` mode with mocked Dishka providers to guarantee no real LLM calls while still asserting event payloads conform to `ELS_CJAssessmentRequestV1`.
- Every CLI test run must call `pdm run typecheck-all` first (Rule 070 §4.1) and re-run it after modifications. We will also add a `lint-runner` target once implementation begins to keep the new script inside Ruff coverage.

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

---
id: eng5-runner-assumption-hardening
title: Eng5 Runner Assumption Hardening
type: task
status: in_progress
priority: high
domain: programs
owner_team: agents
created: '2025-11-21'
last_updated: '2026-02-03'
service: ''
owner: ''
program: ''
related: []
labels: []
---

# Task: Harden ENG5 Runner Assumptions

> **Autonomous AI Execution Prompt**
>
> 1. **Validate inputs aggressively.** Reject configurations that cannot yield valid CJ comparison batches before we publish to Kafka or touch downstream services.
> 2. **Keep business rules near the producer.** Changes should live in the ENG5 runner and its helper modules unless a shared contract must change.
> 3. **Demonstrate outcomes.** For each requirement, capture evidence (logs, test output, or CLI screenshots) showing the new behaviour.
>
> Follow `090-documentation-standards.md` when updating this file. Summaries must be action-oriented, not diary-style.

## Status

**IN PROGRESS** – R1–R5 implemented; R6/R7 pending

## Context

Recent validation exposed several incorrect ENG5 runner assumptions that mask configuration bugs, duplicate assets, and block automated verification. The runner should guide contributors toward valid CJ Assessment requests rather than silently emitting unusable payloads.

## Prerequisite Status (2025-11-14)

- Anchor infrastructure fixes (Content Service PostgreSQL store, CJ anchor upsert + uniqueness) landed in commits `87b606dd`, `7d263334`, `4c67e549`, and `c405775b` and are ready for runner consumption.
- Manual verification from `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md` completed on 2025-11-14 (ENG5 dev DB migration, anchor re-registration, ENG5 execute smoke test). Runner work can now assume canonical anchors exist.
- Proceed with runner hardening under the assumption that anchor uploads are now service-managed; remove any ENG5-side dedupe once verification confirms the DB contains the expected 12 anchors with valid `text_storage_id`s.

## Progress (2025-11-14)

- **R1 – Comparison validation**
  - Added `ComparisonValidationError` + `ensure_comparison_capacity()` in `inventory.py`, updated `apply_comparison_limit` to reject `--max-comparisons < 2` and zero anchor/student inventories.
  - CLI now invokes `ensure_comparison_capacity` for plan/dry-run/execute; emits actionable guidance on failure.
  - Tests: `pdm run pytest-root scripts/tests/test_eng5_np_cli_validation.py` (new R1 assertions) and `scripts/tests/test_eng5_np_runner.py`/`test_eng5_np_execute_integration.py` (fixtures updated for stricter validation).
- **R2 – Canonical batch UUID**
  - `RunnerSettings` now has `batch_uuid`; CLI prints canonical ID + human label, and we bind it through logging/supporting modules.
  - Kafka publishers, AssessmentEventCollector, and AssessmentRunHydrator compare callbacks against `batch_uuid`; CJ request envelopes use canonical IDs with human-readable labels in metadata.
  - Tests: same pytest command above plus `scripts/tests/test_eng5_np_execute_integration.py` (hydrator + kafka flow scenarios updated).

## Immediate Next Actions

1. Complete Checkpoint 4 (R6) by documenting anchor grade metadata and CJ enforcement surfaces (grade-scale ownership is enforced in the runner via R3).
2. Complete Checkpoint 5 (R7 Phase 1–2) by documenting the current essay-upload flow, then adding manifest-level caching with a `--force-reupload` override plus unit coverage.
3. Run and analyse dedicated ENG5 anchor alignment experiments using `ANCHOR_ALIGN_TEST` with language-control prompts and Sonnet 4.5, feeding findings back into runner defaults and CJ prompt configuration.

## Progress (2026-02-01) – Grade Scale Ownership (R3)

- Runner now treats CJ `assessment_instructions.grade_scale` as source of truth:
  - Removed `--grade-scale` and replaced it with `--expected-grade-scale` (assertion only).
  - Added CJ admin preflight (`GET /admin/v1/assessment-instructions/assignment/{assignment_id}`) to resolve and echo `grade_scale` for `plan`/`dry-run`/`execute` when `--assignment-id` is provided.
- Tests:
  - `pdm run pytest-root scripts/tests/test_eng5_np_assignment_preflight.py` ✅

## Progress (2026-02-02) – Anchors as Preconditions (R4) + Optional DB Extraction (R5)

- R4 (student-only execute; anchors are CJ-managed preconditions):
  - Added CJ admin anchor summary endpoint used for runner preflight:
    - `GET /admin/v1/anchors/assignment/<assignment_id>` (scoped to `assessment_instructions.grade_scale`).
  - Runner `execute` no longer registers anchors; local anchor docs are optional for execute runs.
  - `.agent/rules/020.19-eng5-np-runner-container.md` updated to remove the now-invalid execute-time anchor registration claim.
- R5 (optional post-success DB extraction):
  - Added `--auto-extract-eng5-db` (requires `--await-completion`; disallowed with `--no-kafka`).
  - After a completion event is observed, the runner runs the existing CJ DB diagnostics extraction and captures output under `output_dir/db_extract/`.
  - Failure semantics: batch completion is still reported, but extraction failure returns a non-zero exit code and is recorded in artefacts.
- Tests:
  - `pdm run pytest-root scripts/tests/test_eng5_np_anchors_preflight.py` ✅
  - `pdm run pytest-root scripts/tests/test_eng5_np_execute_flow.py` ✅
  - `pdm run pytest-root scripts/cj_experiments_runners/eng5_np/tests/unit/test_execute_handler.py` ✅
  - `pdm run pytest-root services/cj_assessment_service/tests/unit/test_admin_anchor_endpoints.py` ✅

## Progress (2026-02-03) – Documentation Alignment (R4/R5)

- Updated ENG5 runbook and handler architecture docs to reflect:
  - CJ admin preflight + anchor precondition semantics (no execute-time anchor registration).
  - Assignment-owned prompt handling in execute mode.
  - Required execute inputs (`assignment_id`, `course_id`) and optional post-run extraction flag.

## Progress (2026-02-03) – R6 Anchor Grade Metadata Research

- Research artefact captured under:
  - `.claude/research/data/eng5_np_2016/eng5-anchor-grade-metadata-findings-2026-02-03.md`
- Key findings (CJ-owned grade semantics):
  - `assessment_instructions.grade_scale` is authoritative and immutable per assignment.
  - Anchor registration validates grades against that scale via `common_core.grade_scales`.
  - Anchor grade metadata persists in `anchor_essay_references` and propagates through
    `CJAnchorMetadata` into grade projection resolution.

## Progress (2025-11-30) – ENG5 Anchor Alignment Experiment

- Added focused ENG5 NP runner tests to codify the anchor alignment configuration:
  - `scripts/cj_experiments_runners/eng5_np/tests/unit/test_cli_integration.py::TestCliAnchorAlignMode::test_anchor_align_language_control_configuration_uses_sonnet_and_prompts` verifies CLI wiring for:
    - `--mode anchor-align-test`
    - `--llm-provider anthropic`
    - `--llm-model claude-sonnet-4-5-20250929`
    - `--system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt`
    - `--rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt`
  - `scripts/cj_experiments_runners/eng5_np/tests/unit/test_anchor_align_handler_prompts.py::TestAnchorAlignHandlerLanguageControlPrompts::test_execute_with_language_control_prompts_wires_overrides_and_report` verifies that:
    - `AnchorAlignHandler` loads the 003 language-control system prompt and rubric from disk.
    - `RunnerSettings.system_prompt_text` / `rubric_text` are populated with the loaded content.
    - `LLMConfigOverrides` preserves provider/model/temperature/max_tokens and adds matching `system_prompt_override` and `judge_rubric_override`.
    - `generate_alignment_report(...)` receives the same prompt text that was sent to CJ.
- Ran a full ENG5 anchor-only alignment experiment in `ANCHOR_ALIGN_TEST` mode:
  - Command:
    - `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode anchor-align-test --course-id 00000000-0000-0000-0000-000000000052 --batch-id eng5-language-control-sonnet45 --kafka-bootstrap localhost:9093 --llm-provider anthropic --llm-model claude-sonnet-4-5-20250929 --system-prompt scripts/cj_experiments_runners/eng5_np/prompts/system/003_language_control.txt --rubric scripts/cj_experiments_runners/eng5_np/prompts/rubric/003_language_control.txt --await-completion`
  - Model manifest validation confirmed `claude-sonnet-4-5-20250929` as a valid Anthropic model (64k max tokens).
  - Runner submitted 12 anchors as “student” essays via Content Service and awaited CJ completion over Kafka (`66` LLM comparisons, `1` CJ completion, `1` assessment result).
  - Alignment report written to:
    - `.claude/research/data/eng5_np_2016/anchor_align_eng5-language-control-sonnet45_20251130_235510.md`
- High-level findings from the language-control alignment report:
  - Overall rank/grade alignment is strong:
    - Kendall’s tau ≈ `0.85` with only `5` direct inversions across the full anchor set.
    - A-band anchors (A/A) are correctly ranked at the top with high win rates (≥80%).
    - F-band and E-band anchors appear at the bottom with low win rates, with one zero-win E- anchor behaving as a “hard negative” reference.
  - Misalignment patterns:
    - Most inversions occur at near-boundaries (e.g. B vs C+, D- vs E+, E- vs F+), suggesting the prompt/rubric is sensitive but not perfect around neighbouring grade thresholds.
    - Language-heavy mid-band essays (C+/C-/D+) are occasionally preferred over slightly higher-grade anchors when content/structure is weak, which is acceptable for a language-control-focused experiment but should be monitored.
  - Configuration implications:
    - The 003 language-control system + rubric prompts appear suitable as a stricter language-weighted lens on ENG5 anchors without catastrophic drift from the expert grade ordering.
    - For follow-ups, we may want to:
      - Explore slightly lower temperature (e.g. `0.0–0.1`) or a narrower max-token budget for justifications to reduce stochastic inversions at boundaries.
      - Compare these results against a baseline prompt configuration (e.g. the current ENG5 production system prompt) using the same anchor set and CJ convergence thresholds.

This task hardens the ENG5 runner as a **strict validating orchestrator**: it validates inputs, resolves authoritative metadata from CJ APIs, and emits well-formed batches without owning persistence rules that belong in services.

## Problem Statement

1. `--max-comparisons` values below 2 result in a single student essay. CJ pair generation then skips work and the batch stalls without a clear error.
2. `--batch-id` currently accepts arbitrary strings and doubles as a cross-service identifier. This conflicts with the requirement for UUID-based identifiers and makes tracing/idempotency fragile.
3. Assignment metadata is opaque at the CLI level. Operators cannot easily confirm that an `assignment_id`/UUID corresponds to the intended assignment slug (e.g., `np_2017_vt`) and grade_scale from `assessment_instructions`.
4. ENG5 runner still uploads anchors on every run even though anchors are already managed as canonical data in CJ/Content Service.
5. Successful executions require a manual follow-up step to run the ENG5 DB extraction script.
6. Anchor registration currently infers grades from filenames but never verifies or surfaces how grades and grade_scales are actually stored and enforced in CJ.
7. Student essays are uploaded eagerly on every run, with no manifest-level caching or clear strategy for reusing already-persisted content.

## Goals & Requirements

### R1. Fail fast on invalid comparison counts

- Fail fast when `--max-comparisons < 2`.
- Compute the actual number of possible comparisons from anchors × students and fail when this is `< 1`, even if `--max-comparisons >= 2`.
- Apply the same validation in `execute` and `plan`/dry-run modes (no Kafka publish on failure).
- Provide actionable CLI guidance ("set `--max-comparisons` to at least 2", "add more student essays/anchors").
- Add unit coverage for `apply_comparison_limit()` and CLI validation.

### R2. Separate human batch label from canonical batch UUID

- Treat `--batch-id` as a **human-readable batch label** for operators. It is not required to be a UUID and must not be the only cross-service identifier.
- For every `execute` run, generate a canonical `batch_uuid` (`uuid4`) that is used as the primary identifier in Kafka payloads and downstream services.
- Surface both values clearly in CLI output and artefacts:
  - `batch_uuid` as the canonical identifier for tracing/idempotency.
  - `batch_label` (from `--batch-id`) for human context.
- Update artefact filenames and log summaries to mention the canonical `batch_uuid` (optionally including the label), avoiding composite IDs that concatenate arbitrary labels and UUIDs.
- Keep downstream contracts aligned with the architectural pattern of using `uuid.UUID` for identifiers rather than free-form strings.

### R3. Assignment metadata via CJ API (slug + grade_scale verification)

- Resolve `assignment_id` via the **CJ Assessment API/admin surfaces**, using `assessment_instructions` as the authoritative source of:
  - Assignment slug/name (e.g., `np_2017_vt`).
  - `grade_scale` and related metadata.
- Ensure the CJ API communicates this metadata, and keep any CLI/runner display fields (labels, friendly names) as **derived presentation only**.
- Run this lookup in `plan`, `execute`, and `register-anchors` modes before publishing to Kafka and:
  - Print assignment slug, grade_scale, and any other key fields.
  - Fail fast with a helpful error if the assignment cannot be resolved.
- Error messages must point operators to the CJ admin CLI/API (e.g., `pdm run cj-admin assignments list/create ...`) instead of encouraging manual DB inspection.
- Document the command/API endpoint used for the lookup so other tools can reuse the pattern.

### R4. Anchors as CJ-managed precondition (no runner-side dedupe)

- Treat anchors as **canonical CJ/Content data**, not ENG5 runner state.
- Make `execute` runs **student-only**:
  - Before executing, perform a CJ API preflight that verifies the required anchors exist for the given `assignment_id` (and grade_scale where applicable).
  - On missing anchors, fail fast with guidance to use explicit anchor registration flows (`--mode register-anchors` or CJ admin CLI).
- Keep anchor registration **opt-in and explicit**:
  - Do not auto-register anchors during `execute`.
  - Do not implement ENG5-local dedupe or grade-scale logic; rely on CJ’s unique constraint and upsert semantics from the anchor infrastructure task.
- Explicitly depend on `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md` for:
  - Persistent Content Service storage.
  - Unique constraint on `(assignment_id, anchor_label, grade_scale)`.
  - Upsert behaviour in CJ’s `anchor_management` API.
  - Note: `.agent/rules/020.19-eng5-np-runner-container.md` currently describes execute-time anchor registration; R4 intentionally removes this and will require a rule update once implemented.

### R5. Optional automatic ENG5 DB extraction on successful completion

- Introduce an **opt-in** flag (e.g., `--auto-extract-eng5-db`) that, when combined with `--await-completion`, runs the existing ENG5 extraction script under `scripts/` after successful completion events.
- Default `--auto-extract-eng5-db` to **off**, especially for CI/non-interactive contexts.
- Capture extraction script output in the run summary artefact.
- Define failure semantics:
  - If the batch completes but extraction fails, mark the extraction step as failed in artefacts and exit with a non-zero code, without hiding the fact that the CJ batch itself succeeded.
- Add smoke coverage (CLI test or integration harness) asserting that:
  - The script runs when completion events arrive and the flag is enabled.
  - No script is run when the flag is omitted.

### R6. Anchor grade metadata (research + CJ alignment)

- Investigate the current anchor registration flow to confirm how grade metadata is stored and enforced today:
  - CJ API routes and payloads.
  - `assessment_instructions` usage for `grade_scale`.
  - Content Service interactions, where applicable.
- Summarise findings (routes, payloads, DB fields) in this task’s notes and/or a dedicated research artefact before modifying any code.
- Confirm and document that **grade_scale and grade semantics are owned by CJ** (especially via `assessment_instructions`), not by the ENG5 runner or filename conventions.
- Update ENG5 documentation and anchor registration examples to align with the agreed grade taxonomy.
- If new enforcement or schema changes are required in CJ, open a separate CJ-focused task and treat service-side changes as out of scope for this ENG5 runner task.

### R7. Student essay persistence & re-upload avoidance (phased)

- **Phase 1 – Behaviour documentation (this task)**:
  - Document the current behaviour for student essay uploads:
    - How ENG5 calls Content Service.
    - How storage IDs are propagated into CJ (e.g., via processing metadata).
  - No behavioural change; capture the baseline clearly.
- **Phase 2 – Manifest-level caching (this task)**:
  - Introduce a manifest-level mapping from local essay identifiers to Content Service storage IDs stored alongside the ENG5 manifest/artefacts.
  - On upload, persist the returned storage ID into this mapping.
  - On subsequent runs, reuse stored IDs instead of re-uploading essays when the mapping is present, unless a `--force-reupload` flag is provided.
  - Do not yet rely on Content Service existence checks; accept that infra issues (e.g., content resets) will surface as downstream errors that point back to Content Service.
- **Phase 3 – Remote verification (follow-up task)**:
  - After Content Service is fully migrated to database-backed storage and exposes stable APIs (e.g., `content_exists`), design an optional `--verify-content` mode that:
    - Confirms remote existence for stored IDs.
    - Re-uploads or fails with clear guidance when content is missing.
  - Track this as a separate task; do not implement it under this ENG5 runner hardening task.

## Deliverables / Acceptance Criteria

- R1–R6 and **R7 Phase 1–2** implemented and tested (unit + targeted integration where applicable).
- Updated CLI/docs describing:
  - New validation rules for comparison counts.
  - Canonical `batch_uuid` vs human batch label semantics.
  - Assignment metadata lookup behaviour and failure paths.
  - Anchor precondition semantics for `execute`.
  - Optional automated ENG5 DB extraction.
  - Manifest-level essay caching behaviour and `--force-reupload`.
- New/updated artefacts under `.claude/research/data/eng5_np_2016/` demonstrate:
  - Failure handling (invalid comparisons, missing assignments/anchors).
  - Successful end-to-end run with optional automated extraction.
- Regression tests for ENG5 runner pass: `pdm run pytest-root scripts/tests/test_eng5_np_manifest_integration.py` plus any new suites.
- Handoff notes in this task document summarise:
  - Changes applied.
  - Test commands used.
  - Any follow-up tasks opened (e.g., CJ service changes for grades or Content Service verification).

## Dependencies & References

- Runner sources: `scripts/cj_experiments_runners/eng5_np/cli.py`, `inventory.py`, `cj_client.py`, `requests.py`.
- Existing tasks:
  - `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` (prompt correctness and assignment/rubric handling).
  - `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE.md` (anchor persistence, Content Service migration, upsert semantics).
  - `TASK-CJ-ASSESSMENT-CODE-HARDENING.md` (error handling, DI, logging patterns).
- CJ Assessment API/admin docs for assignment lookup and anchor registration.

## Execution Plan & Checkpoints

### Checkpoint 1 – CLI validation & batch UUID (R1, R2) ✅ COMPLETED

- **Objective**: Ensure ENG5 rejects obviously invalid comparison configurations and always uses a canonical UUID for cross-service identity.
- **Implementation (high-level)**:
  - Add/extend CLI validation helpers to:
    - Enforce `--max-comparisons >= 2`.
    - Compute possible anchor×student comparisons and fail when `< 1`.
  - Introduce `batch_uuid` generation for `execute` runs and surface it in:
    - Kafka payloads and logging metadata.
    - CLI summary output and artefact filenames (alongside human `batch_id` label).
- **Validation**:
  - New/updated unit tests for comparison validation and batch ID handling (e.g. under `scripts/tests/`):
    - Cases: `max_comparisons=1`, zero anchors, one student, etc.
    - Ensure `batch_uuid` is present and `batch_label` remains optional/human-facing.
  - Run:
    - `pdm run pytest-root scripts/tests/test_eng5_np_manifest_integration.py -k comparisons`

### Checkpoint 2 – Assignment metadata preflight (R3) ✅ COMPLETED

- **Objective**: Resolve assignment metadata from CJ via API before any ENG5 run and display it clearly to the operator.
- **Implementation (high-level)**:
  - Implement a preflight helper that calls the CJ admin API:
    - `GET /admin/v1/assessment-instructions/assignment/{assignment_id}`.
    - Map response into an internal `AssignmentMetadata` structure.
  - Call this helper in `plan`, `execute`, and `register-anchors` modes, failing fast on:
    - Unknown assignment (404).
    - Auth/config problems (401/403, bad URL/token).
  - Echo slug-related information (from assignment_id), grade_scale, and prompt presence to the CLI while treating the CJ response as authoritative.
- **Validation**:
  - `pdm run pytest-root scripts/tests/test_eng5_np_assignment_preflight.py` ✅
  - `pdm run eng5-np-run --help` ✅ (flag surface: `--expected-grade-scale`, no `--grade-scale`)

### Checkpoint 3 – Anchors as precondition & optional DB extraction (R4, R5) ✅ COMPLETED

- **Objective**: Make ENG5 `execute` runs student-only with anchors treated as a CJ-managed precondition, and add optional post-success DB extraction.
- **Implementation (high-level)**:
  - Anchor precondition:
    - Add a CJ API preflight step that verifies required anchors exist for the assignment/grade_scale.
    - On failure, provide guidance to run explicit anchor registration flows.
    - Ensure `execute` does not upload anchors or try to dedupe them locally.
  - DB extraction:
    - Add `--auto-extract-eng5-db` flag, used only in combination with `--await-completion`.
    - Wire this flag to call the existing ENG5 extraction script and capture its output in run artefacts.
    - Define clear behaviour when extraction fails while the batch itself succeeds.
- **Validation**:
  - Tests for anchor precondition behaviour, including:
    - No anchors present → ENG5 fails fast with helpful CLI guidance.
    - Anchors present → `execute` proceeds without uploading anchors.
  - Smoke test for extraction:
    - `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode execute ... --await-completion --auto-extract-eng5-db`
    - Verify extraction script runs exactly once on success and output is captured in artefacts.

### Checkpoint 4 – Anchor grade metadata research & alignment (R6)

- **Objective**: Document how grade metadata is persisted and enforced in CJ and ensure ENG5 docs/examples align, without moving enforcement logic into ENG5.
- **Implementation (high-level)**:
  - Inspect CJ endpoints and models (`assessment_instructions`, anchor APIs, grade scales) to confirm:
    - Where `grade_scale` and grade semantics live.
    - How anchors reference grade/grade_scale.
  - Capture findings in this task and/or a dedicated research artefact.
  - Update ENG5 documentation and examples so anchor registration uses the agreed taxonomy and does not invent new grade-scale semantics.
  - If gaps are found, open a follow-up CJ task to adjust service-side enforcement.
- **Validation**:
  - Updated docs checked against CJ models and tests (no contradictory statements).
  - Optional: add or extend CJ tests (unit/integration) to prove grade metadata round-trips correctly through the CJ APIs used by ENG5.

### Checkpoint 5 – Essay persistence & manifest caching (R7 Phase 1–2)

- **Objective**: Make ENG5’s interaction with Content Service observable and incrementally more efficient via manifest-level caching, without over-coupling to Content Service internals.
- **Implementation (high-level)**:
  - Phase 1 (documentation):
    - Document current ENG5 → Content Service → CJ flow for essay uploads.
  - Phase 2 (caching):
    - Add a manifest-adjacent mapping from local essay identifiers to Content Service storage IDs.
    - On upload, persist the returned storage ID into this mapping.
    - On subsequent runs, reuse stored IDs when present, unless `--force-reupload` is set.
    - Keep behaviour simple: do not probe Content Service for existence yet; allow infra issues to surface as Content Service errors.
- **Validation**:
  - Unit tests covering:
    - First-run behaviour (no cache → uploads all essays and writes mapping).
    - Second-run behaviour (cache present → reuses storage IDs without re-uploading).
    - `--force-reupload` behaviour (ignores mapping and overwrites it).
  - Optional integration test with a running Content Service instance to observe reduced upload calls across repeated runs.

### Checkpoint 6 – Final consolidation & documentation (all requirements)

- **Objective**: Ensure all requirements and checkpoints are implemented coherently and validated before closing the task.
- **Implementation (high-level)**:
  - Reconcile implementation with R1–R7 and this execution plan.
  - Update this task document with:
    - Which checkpoints are complete.
    - Exact commands used for validation.
    - Any follow-up tasks created (CJ-side grades, Content verification, etc.).
  - Ensure ENG5 docs (readme/usage guides) reflect new flags and preflight behaviours.
- **Validation**:
  - Run targeted checks:
    - `pdm run pytest-root scripts/tests/test_eng5_np_manifest_integration.py`
    - Any new ENG5-specific CLI/unit tests introduced in this work.
  - Optionally, run a full ENG5 end-to-end execute with `--await-completion` (and optionally `--auto-extract-eng5-db`) to verify:
    - Preflight behaviour.
    - Comparison limits.
    - Anchor precondition handling.
    - Manifest caching.

## Non-Goals

- The ENG5 runner **does not** become a secondary source of truth for:
  - Grade scales.
  - Assignment metadata.
  - Anchor persistence semantics.
- The ENG5 runner **does not** reach directly into CJ or Content Service databases; it uses CJ/Content APIs and admin tools as the authoritative surfaces.
- The ENG5 runner **does not** introduce new cross-service contracts beyond:
  - Canonical `batch_uuid` identifiers.
  - Clear, validated payloads that align with existing architectures.

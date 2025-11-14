# Task: Harden ENG5 Runner Assumptions

> **Autonomous AI Execution Prompt**
>
> 1. **Validate inputs aggressively.** Reject configurations that cannot yield valid CJ comparison batches before we publish to Kafka or touch downstream services.
> 2. **Keep business rules near the producer.** Changes should live in the ENG5 runner and its helper modules unless a shared contract must change.
> 3. **Demonstrate outcomes.** For each requirement, capture evidence (logs, test output, or CLI screenshots) showing the new behaviour.
>
> Follow `090-documentation-standards.mdc` when updating this file. Summaries must be action-oriented, not diary-style.

## Status

**IN PROGRESS** – Awaiting ENG5 anchor verification + runner implementation kickoff

## Context

Recent validation exposed several incorrect ENG5 runner assumptions that mask configuration bugs, duplicate assets, and block automated verification. The runner should guide contributors toward valid CJ Assessment requests rather than silently emitting unusable payloads.

## Prerequisite Status (2025-11-14)

- Anchor infrastructure fixes (Content Service PostgreSQL store, CJ anchor upsert + uniqueness) landed in commits `87b606dd`, `7d263334`, `4c67e549`, and `c405775b` and are ready for runner consumption.
- Manual verification from `TASK-FIX-ANCHOR-ESSAY-INFRASTRUCTURE-CHECKLIST.md` is pending (ENG5 dev DB migration rerun, anchor re-registration, ENG5 execute smoke test). Runner changes that assume canonical anchors should wait for this evidence or run in parallel with clear coordination.
- Proceed with runner hardening under the assumption that anchor uploads are now service-managed; remove any ENG5-side dedupe once verification confirms the DB contains the expected 12 anchors with valid `text_storage_id`s.

## Immediate Next Actions

1. Close out anchor verification checklist items (DB migration audit, ENG5 anchor re-registration, student-only ENG5 execute run, metadata passthrough proof) so the runner can rely on canonical anchors without fallback code.
2. Implement Checkpoint 1 (R1/R2) by enforcing comparison-count validation and switching `execute` runs to always emit a canonical `batch_uuid`, with updated artefacts/tests.
3. Implement Checkpoint 2 (R3) by wiring CJ assignment metadata lookups into `plan/execute/register-anchors`, surfacing slug + grade_scale, and hard-failing unknown assignments before Kafka publication.
4. Implement Checkpoint 3 (R4/R5) to remove automatic anchor uploads, add a CJ anchor preflight, and introduce `--auto-extract-eng5-db` tied to `--await-completion`, including smoke coverage.
5. Complete Checkpoint 4 (R6) by documenting grade-scale ownership in CJ, updating ENG5 examples accordingly, and filing any CJ-side follow-ups discovered during the research pass.
6. Complete Checkpoint 5 (R7 Phase 1–2) by documenting the current essay-upload flow, then adding manifest-level caching with a `--force-reupload` override plus unit coverage.

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
  - Unique constraint on `(assignment_id, grade, grade_scale)`.
  - Upsert behaviour in CJ’s `anchor_management` API.

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

### Checkpoint 1 – CLI validation & batch UUID (R1, R2)

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

### Checkpoint 2 – Assignment metadata preflight (R3)

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
  - Unit tests for:
    - Happy-path metadata resolution.
    - 404 → user-facing guidance to use `cj-admin instructions upsert/list`.
    - 401/403 → clear configuration/auth error messages.
  - Integration smoke test using a real CJ instance (dev stack):
    - `pdm run cj-admin instructions upsert ...` to seed data.
    - `pdm run python -m scripts.cj_experiments_runners.eng5_np.cli --mode plan ...` and assert preflight output.

### Checkpoint 3 – Anchors as precondition & optional DB extraction (R4, R5)

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

---
id: 'persist-text-storage-id-on-file-uploads-and-enable-mock-llm-for-functional-cj'
title: 'Persist text_storage_id on file uploads and enable mock LLM for functional CJ'
type: 'task'
status: 'in_progress'
priority: 'medium'
domain: 'infrastructure'
service: 'file_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-27'
last_updated: '2025-11-27'
related: []
labels: []
---
# Persist text_storage_id on file uploads and enable mock LLM for functional CJ

## Objective

Restore traceability of CJ assessment rankings to original uploaded files and ensure functional CJ runs complete quickly and deterministically by using the mock LLM provider during functional tests.

## Context

- Functional CJ runs completed, but `file_uploads` in File Service did not persist `text_storage_id`, so CJ `text_storage_id` → filename mapping is impossible (breaks auditability and test assertions).
- Functional tests are hitting real providers with ~150 comparisons per batch, taking 6–7 minutes; we want functional runs to stay fast and deterministic by overriding to mock LLM.

## Plan

1) File Service ingestion: persist `text_storage_id` (and/or essay_id) into `file_uploads` when text content is stored; add migration if schema needs nullability changes; ensure backfill not required for functional tests.  
2) Tests: add functional harness guard to set `CJ_ASSESSMENT_SERVICE_USE_MOCK_LLM=true` (or equivalent env) when running functional tests; document the override in tests/README.  
3) Re-run functional CJ tests (guest + regular/student-matching flows) to verify:  
   - Rankings are emitted and can be joined to filenames via `text_storage_id`.  
   - Functional runs complete within the existing slow timeout using mock LLM.  
4) Enforce functional CJ runs include `assignment_id` on uploads (needed for grade-projection/anchor pools) and swap the functional essay bundle to the same ENG5 runner student set to keep scenarios aligned with production.  
5) Add stability observability best-practice: keep events thin and avoid per-iteration bloat; persist only final BT scores plus small per-iteration delta summaries (or ring buffer) in processing_metadata, and emit optional stability progress events/metrics (no vectors) for diagnostics.  
6) Submission staging requirement (non-batch-API modes): submit comparisons in waves (e.g., N bundles), wait for callbacks, check stability (`SCORE_STABILITY_THRESHOLD`, `MIN_COMPARISONS_FOR_STABILITY_CHECK`), then decide whether to enqueue more. Do not flood the full comparison budget at once.  
   - Code touchpoints:  
     - `cj_core_logic/comparison_processing.py`: orchestrator should cap bundles per wave and surface wave sizing from settings.  
     - `cj_core_logic/workflow_continuation.py`: after each wave’s callbacks, run stability and stop submitting when stable/complete.  
     - Settings/env: add max_bundles_per_wave (or similar) and wire through DI.  
     - Tests: integration/functional to verify early stop when stability reached; unit to assert staged submissions.  
7) Update docs (handoff/session) with traceability fix, assignment_id requirement, mock-LLM guard, ENG5 bundle alignment, thin-event stability guidance, and staged submission requirement.

### PR declaration: staged submission for serial bundles (non-batch-API)
- Purpose: prevent flooding full comparison budget; send waves, wait for callbacks, check stability, then decide on next wave. Targets faster convergence, lower cost/latency, clearer observability.
- Scope: `cj_core_logic/comparison_processing.py` (wave cap from settings), `workflow_continuation.py` (stability/budget check post-wave), new setting (`MAX_BUNDLES_PER_WAVE` or similar) wired via DI; tests (unit + integration/functional) to prove early stop.

## Success Criteria

- `file_uploads` rows contain `text_storage_id` for new uploads; CJ rankings can be joined to filenames in functional runs.  
- Functional CJ tests pass with mock LLM enabled and finish within existing timeouts.  
- `assignment_id` present on functional uploads; ENG5 runner essay bundle used for CJ functional tests; grade-projection/anchor flows unblocked for testing.  
- Thin-event stability guidance captured; staged submission requirement documented; no per-iteration BT bloat in contracts; documentation updated; no regressions in format/lint/typecheck.

## Progress (2025-11-27)

- Added `assignment_id` column + indexes (text_storage_id, assignment_id) to `file_uploads` with migration `20251127_1200_add_assignment_id_and_text_storage_indexes.py`.
- File Service now persists `text_storage_id` and `assignment_id` during ingestion; processing status persisted for success/failure paths.
- API Gateway/file upload routes accept optional `assignment_id` and forward it to File Service; ServiceTestManager/pipeline helpers attach `FUNCTIONAL_ASSIGNMENT_ID` (default `test_eng5_writing_2025`) on functional uploads.
- Functional harness now enforces mock LLM mode (skips suite if mock disabled unless `ALLOW_REAL_LLM_FUNCTIONAL=1`), and docs updated to reflect assignment_id + mock-LLM requirements.

### Problem statement (expanded)
- Regular (class) batches: Assignment_id at upload is recommended for traceability but not required for pipeline execution or student mapping (ELS/Class Mgmt already ties `essay_id` → `student_id`). If assignment_id is added later (before CJ), CJ prep just needs it in BOS/ELS → CJ request metadata; uploads can remain without it unless filename-level audit is needed.
- Guest batches: Strongly recommended. There’s no student context, so filename↔CJ result joins rely on `file_uploads` having `text_storage_id` (now stored) and, for contextual reporting, `assignment_id`.

### Backfilling assignment_id onto file_uploads (pick one)
1. Service-layer patch (preferred): Add a small File Service API endpoint (e.g., `/v1/files/batch/{batch_id}/assignment`) that accepts `assignment_id`, validates ownership, and updates all `file_uploads` for that batch. BOS can call it right after the assignment_id becomes known.
2. BOS → File Service hook: emit an internal command/event when BOS captures assignment_id; File Service consumes it to update the batch’s uploads.
3. One-off backfill script: use File Service repository to update assignment_id for existing batches (transactional, with audit logs).

## Acceptance criteria (traceability)
1. New uploads store `text_storage_id` and, when provided, `assignment_id`; CJ ranking → `text_storage_id` → filename joins work in guest and class flows.
2. If assignment_id is provided after upload, it is propagated into the CJ request before batch prep. For filename-level audit, the chosen backfill path updates `file_uploads.assignment_id` for the batch.
3. Functional runs default to `FUNCTIONAL_ASSIGNMENT_ID` and use mock LLM; the suite skips if mock is disabled unless explicitly overridden.

## Related

- CJ functional tests (guest/regular flows)  
- File Service ingestion path  
- tests/README functional guidance

---
id: 'persist-text_storage_id-on-file-uploads-and-enable-mock-llm-for-functional-cj'
title: 'Persist text_storage_id on file uploads and enable mock LLM for functional CJ'
type: 'task'
status: 'research'
priority: 'medium'
domain: 'infrastructure'
service: ''
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

## Success Criteria

- `file_uploads` rows contain `text_storage_id` for new uploads; CJ rankings can be joined to filenames in functional runs.  
- Functional CJ tests pass with mock LLM enabled and finish within existing timeouts.  
- `assignment_id` present on functional uploads; ENG5 runner essay bundle used for CJ functional tests; grade-projection/anchor flows unblocked for testing.  
- Thin-event stability guidance captured; staged submission requirement documented; no per-iteration BT bloat in contracts; documentation updated; no regressions in format/lint/typecheck.

## Related

- CJ functional tests (guest/regular flows)  
- File Service ingestion path  
- tests/README functional guidance

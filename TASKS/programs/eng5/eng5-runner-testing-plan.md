---
id: eng5-runner-testing-plan
title: Eng5 Runner Testing Plan
type: task
status: research
priority: medium
domain: programs
owner_team: agents
created: '2025-11-21'
last_updated: '2025-11-21'
service: ''
owner: ''
program: ''
related: []
labels: []
---

# Task: ENG5 Runner Testing Plan

**Linked task**: `TASK-ENG5-RUNNER-ASSUMPTION-HARDENING.md`

This task captures the test layout and skeletons required to validate the ENG5 runner assumption hardening work.

## Test Modules & Responsibilities

- `scripts/tests/test_eng5_np_cli_validation.py`
  - Checkpoint 1 (R1, R2): CLI validation and batch UUID behaviour.
- `scripts/tests/test_eng5_np_assignment_preflight.py`
  - Checkpoint 2 (R3): CJ assignment metadata preflight.
- `scripts/tests/test_eng5_np_execute_flow.py`
  - Checkpoint 3 (R4, R5): anchor preconditions and optional DB extraction.
- `scripts/tests/test_eng5_np_manifest_caching.py`
  - Checkpoint 5 (R7 Phase 1–2): essay persistence and manifest-level caching.

## High-Level Test Cases

### 1. CLI validation & batch UUID (test_eng5_np_cli_validation.py)

- Reject `--max-comparisons < 2` even with adequate essays.
- Reject configurations where anchors×students `< 1`.
- Accept valid configurations and compute expected comparisons.
- Ensure `batch_uuid` is generated for `execute` runs.
- Ensure human `batch_id` label is preserved and surfaced correctly.

### 2. Assignment metadata preflight (test_eng5_np_assignment_preflight.py)

- Happy-path CJ admin metadata resolution for a valid assignment.
- 404 from CJ admin → user guidance to use `cj-admin instructions upsert/list`.
- 401/403 from CJ admin → configuration/auth error surfaced.
- Missing/invalid CJ admin URL or token → configuration error surfaced.

### 3. Anchors precondition & DB extraction (test_eng5_np_execute_flow.py)

- `execute` fails fast when required anchors are missing in CJ.
- `execute` does not upload anchors when anchors are present (student-only runs).
- `--auto-extract-eng5-db` triggers extraction after successful completion.
- Extraction is not run when the flag is omitted.
- Extraction failure is reported without hiding batch success.

### 4. Essay persistence & manifest caching (test_eng5_np_manifest_caching.py)

- First run uploads all essays and writes storage ID mapping.
- Second run reuses cached storage IDs without re-uploading.
- `--force-reupload` ignores cache and overwrites it with new IDs.
- Optional: partial cache behaviour (only missing essays uploaded).

## Skeletons

See `scripts/tests/test_eng5_np_assignment_preflight.py` for initial pytest skeleton functions wired to these cases.

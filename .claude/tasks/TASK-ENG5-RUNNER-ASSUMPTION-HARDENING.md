# Task: Harden ENG5 Runner Assumptions

> **Autonomous AI Execution Prompt**
>
> 1. **Validate inputs aggressively.** Reject configurations that cannot yield valid CJ comparison batches before we publish to Kafka or touch downstream services.
> 2. **Keep business rules near the producer.** Changes should live in the ENG5 runner and its helper modules unless a shared contract must change.
> 3. **Demonstrate outcomes.** For each requirement, capture evidence (logs, test output, or CLI screenshots) showing the new behaviour.
>
> Follow `090-documentation-standards.mdc` when updating this file. Summaries must be action-oriented, not diary-style.

## Status

**NOT STARTED** – Awaiting assignment

## Context

Recent validation exposed several incorrect ENG5 runner assumptions that mask configuration bugs, duplicate assets, and block automated verification. The runner should guide contributors toward valid CJ Assessment requests rather than silently emitting unusable payloads.

## Problem Statement

1. `--max-comparisons` values below 2 result in a single student essay. CJ pair generation then skips work and the batch stalls without a clear error.
2. `--batch-id` accepts arbitrary strings, but instructional docs require UUID batch identifiers; mismatches complicate tracing across services.
3. Assignment metadata is opaque: operators cannot easily confirm that a UUID corresponds to the intended assignment (e.g., `np_2017_vt`).
4. ENG5 runner still uploads anchors on every run even though anchors already exist in CJ/Content Service.
5. Successful executions require a manual follow-up step to run the ENG5 DB extraction script.
6. Anchor registration currently infers grades from filenames but never persists those grades alongside the anchors.

## Goals & Requirements

### R1. Enforce minimum comparison count

- Fail fast when `--max-comparisons < 2` (or computed anchor×student pairs < 1).
- Provide actionable CLI guidance ("set to at least 2" / "add more student essays").
- Add unit coverage for `apply_comparison_limit()` and CLI validation.

### R2. Auto-generate UUID batch identifiers

- Runner must generate a UUID (v4) for each execute run and surface it prominently in CLI output/logs.
- Allow optional override for reproducibility, but default to auto-generation so operators never handcraft IDs.
- Update artefact filenames/log summaries to mention the generated batch ID for easy cross-service tracing.

### R3. Expose assignment metadata for verification

- Add runner option (or default log output) that resolves `assignment_id` via CJ Assessment API and prints assignment name/slug (e.g., `np_2017_vt`).
- Ensure failures surface a helpful error explaining how to register/locate the assignment.
- Document the command/API endpoint used for the lookup.

### R4. Confirm anchor persistence and stop re-uploading duplicates

- Audit existing CJ/Content Service anchor state to confirm canonical storage (capture findings in task notes before code changes).
- Once confirmed, remove anchors from the ENG5 upload pool so execute runs only push student essays.
- Keep anchor registration opt-in only (e.g., explicit flag) and document the precondition that anchors already live in CJ.

### R5. Automate DB extraction on successful completion

- When `--await-completion` succeeds, invoke the existing ENG5 extraction script under `scripts/` automatically (flag to opt-out is acceptable).
- Capture script output in the run summary artefact.
- Add smoke coverage (CLI test or integration harness) to assert the script runs when completion events arrive.

### R6. Anchor grade metadata (research-first)

- Investigate current anchor registration flow to confirm how grade metadata is stored today (CJ API + Content Service).
- Summarise findings (routes, payloads, DB fields) before modifying code; only then enforce grade persistence or enhance payloads.
- After research, add tests/documentation that anchor grades are captured using the agreed taxonomy and retrievable for audits.

### R7. Student essay persistence & re-upload avoidance

- Document the current behaviour for student essay uploads (Content Service storage IDs, caching layers, dedupe strategy).
- Identify whether essays already persisted in Content Service can be re-used; design runner support to skip uploads when content exists.
- Provide configuration/tests demonstrating the new behaviour (e.g., caching by checksum with persisted map, or lookup via Content Service API).

## Deliverables / Acceptance Criteria

- All six requirements implemented and tested (unit + targeted integration where applicable).
- Updated CLI/docs describing new validation rules, UUID requirement, automated extraction behaviour, and anchor prerequisites.
- New/updated artefacts under `.claude/research/data/eng5_np_2016/` demonstrate failure handling and successful end-to-end run with automated extraction.
- Regression tests for ENG5 runner pass: `pdm run pytest-root scripts/tests/test_eng5_np_manifest_integration.py` plus any new suites.
- Handoff notes in this task document summarise changes, test commands, and follow-up actions (if any).

## Dependencies & References

- Runner sources: `scripts/cj_experiments_runners/eng5_np/cli.py`, `inventory.py`, `cj_client.py`, `requests.py`.
- Existing task: `TASK-FIX-CJ-LLM-PROMPT-CONSTRUCTION.md` (prompt correctness).
- CJ Assessment API docs for assignment lookup and anchor registration.

## Suggested Implementation Steps (Guidance)

1. Add CLI validation helpers (max comparisons, UUID batch ID) and extend associated unit tests.
2. Introduce assignment lookup helper (REST call to CJ service) and integrate with execute mode preflight.
3. Refactor upload pipeline to exclude anchors and adjust documentation accordingly.
4. Wire post-success hook to run the DB extraction script when completion events arrive; capture output in artefacts/logs.
5. Enhance `register_anchor_essays()` with grade persistence checks; add tests to confirm behaviour.
6. Update docs and task notes, then run targeted test suites.

---

### Open Questions for Assignee

- Should the assignment lookup run in plan/dry-run modes as well?
- Do we need a toggle for auto-running the extraction script in CI contexts?
- Is additional CJ API support required to store/retrieve anchor grades?

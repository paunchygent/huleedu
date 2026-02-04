---
id: 'essay-scoring-runner-mark-statusjson-failed-on-sigint-sigterm'
title: 'Essay-scoring runner: mark status.json failed on SIGINT/SIGTERM'
type: 'task'
status: 'proposed'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-04'
last_updated: '2026-02-04'
related: []
labels: []
---
# Essay-scoring runner: mark status.json failed on SIGINT/SIGTERM

## Objective

Make interrupted/killed research runs explicitly record `state=failed` in
`status.json` so they don’t look “hung” forever, and preserve the signal marker
even when the stage context manager handles `KeyboardInterrupt`/`SystemExit`.

## Context

We’ve repeatedly had long-running `pdm run essay-scoring-research ...` runs stop
mid-stage (SIGINT/SIGTERM). When this happens, `output/.../status.json` could
remain stuck at `state=running`, which makes post-mortems ambiguous (hang vs
termination) and slows iteration.

This task makes the runner write a best-effort failure marker on SIGINT/SIGTERM,
and ensures that marker is not overwritten by stage-level exception handling.

## Plan

- Add SIGINT/SIGTERM handlers in the run logging context to write `status.json`
  with `state=failed`, `failure_reason=signal`, and `signal=SIGINT|SIGTERM`.
- Update the stage timing context manager to:
  - Mark `failed` on exceptions (not “complete” in a `finally`), and
  - Preserve an existing signal failure marker rather than overwriting it with
    `KeyboardInterrupt` details.
- Add tests for both cases.

## Success Criteria

- When a run is interrupted with SIGINT/SIGTERM, `status.json` ends with
  `state=failed` and includes `failure_reason=signal` and `signal=...`.
- Stage-level exception handling does not overwrite the signal failure marker.
- Tests exist and pass.

## Related

- Code: `scripts/ml_training/essay_scoring/logging_utils.py`
- Tests: `scripts/ml_training/tests/test_runner_status_interrupt.py`

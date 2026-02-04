---
id: 'essay-scoring-sensible-progress-logs-for-feature-extraction'
title: 'Essay scoring: sensible progress logs for feature extraction'
type: 'task'
status: 'in_progress'
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
# Essay scoring: sensible progress logs for feature extraction

## Objective

Ensure long-running essay-scoring research runs emit “normal”, actionable progress logs during
feature extraction (especially when using the Hemma `/v1/extract` offload backend), so a detached
`nohup` run can be monitored via a single tailed log.

## Context

We run experiments detached via `nohup ... > output/essay_scoring/<run>.driver.log 2>&1 & disown`.
The CLI previously defaulted console logging to WARNING, and the Hemma extraction path produced very
few INFO logs. This makes it look like the run is stuck (even while work is happening), wasting
iteration time and undermining the “single tail” operational workflow.

## Plan

- Make console logging INFO by default when stdout/stderr are redirected (non-TTY).
- Add rate-limited, periodic progress logs during Hemma offload extraction:
  - cache scan summary (hits/misses, missing count)
  - fetch progress (ready/total, batches, throughput, ETA)
- Keep logs bounded (time-based throttling) and avoid per-essay spam.
- Add/adjust tests as needed for deterministic behavior.

## Success Criteria

- A detached Hemma run shows regular progress logs in `*.driver.log` within ~15 seconds.
- Feature extraction logs include: stage start, cache scan summary, periodic progress, stage complete.
- No per-essay logging; logs remain readable for large runs.
- Existing offload client HTTP tests still pass.

## Related

[List related tasks or docs]

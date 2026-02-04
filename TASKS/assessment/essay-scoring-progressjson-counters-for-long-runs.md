---
id: 'essay-scoring-progressjson-counters-for-long-runs'
title: 'Essay scoring: progress.json counters for long runs'
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
# Essay scoring: progress.json counters for long runs

## Objective

Add a **machine-readable** progress signal (`progress.json`) to essay-scoring research runs so
long-running stages can be monitored (processed/total + ETA) without tailing logs.

## Context

We already write `status.json` (stage-level state), and we improved human logs for long runs.
However, log-based monitoring is still brittle for tooling, dashboards, and "what is the ETA?"
questions. A single JSON counter file enables:
- quick ETA estimation
- stable progress extraction for scripts (`jq`, file watchers)
- consistent monitoring across local/offload backends

## Plan

- Implement a throttled, atomic `ProgressWriter` that updates `progress.json` in the run directory.
- Wire progress updates into the most time-consuming substages:
  - Tier1 (spaCy + LanguageTool)
  - Tier2 (parse, unique-text collection, embedding batch, per-essay features)
  - Tier3 (per-essay loop)
  - Hemma combined offload client (`/v1/extract` cache scan + fetch progress)
  - CV fold loop (folds processed/total)
- Document `progress.json` in the runbook.

## Success Criteria

- New runs create/update `output/essay_scoring/<RUN>/progress.json` during long stages.
- Payload includes: `stage`, `substage`, `processed`, `total`, `rate_per_s`, `eta_seconds`.
- Writes are throttled and atomic (no partially written JSON observed).
- Tests cover the writer semantics (stage inclusion + throttling).

## Related

- Runbook: `docs/operations/ml-nlp-runbook.md`
- Hub: `docs/reference/ref-essay-scoring-research-hub.md`
- Task: `TASKS/assessment/essay-scoring-sensible-progress-logs-for-feature-extraction.md`

---
id: 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
title: 'essay-scoring: residual diagnostics by prompt and grade band'
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
related:
  - 'improve-essay-scoring-prediction-power-ellipse-cv-first'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
labels: []
---
# essay-scoring: residual diagnostics by prompt and grade band

## Objective

Add diagnostics that show *where* the model fails:
- by prompt (topic)
- by grade band (tails vs middle)
- by key covariates (length / grammar error rate / prompt similarity)

## Context

Aggregate metrics (QWK/MAE) hide important failure modes:
- prompt-specific drift (common in prompt-based writing datasets)
- tail underperformance (rare labels)
- systematic biases (length effects, grammar density effects)

These diagnostics should guide which changes will actually improve prediction power instead of
just moving global averages slightly.

## Plan

Implementation (code + report):
- Persist per-essay predictions and residuals for evaluation splits (at least test; ideally per CV fold):
  - `record_id`, `prompt`, `y_true`, `y_pred`, `residual`, and a few key features (word_count, etc.)
- Add a report generator that outputs:
  - per-prompt MAE/QWK (top N prompts by volume)
  - per-band MAE
  - residual vs word_count scatter summary (and correlation)
  - “worst prompts” list with sample size safeguards

Target outputs:
- `reports/residual_diagnostics.md` under the run directory for single-run and CV runs.

## Success Criteria

- A run directory contains per-record predictions + a residual diagnostics report.
- The report is referenced from the story with a short “what to do next” section.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`

---
type: review
id: REV-statsmodels-diagnostics-catboost-baseline-dependencies
title: 'Review: essay scoring statsmodels diagnostics and catboost baseline dependencies'
status: pending
created: '2026-02-06'
last_updated: '2026-02-06'
story: essay-scoring-statsmodels-diagnostics--catboost-baseline
reviewer: agents
---
# Review: essay scoring statsmodels diagnostics and catboost baseline dependencies

## TL;DR

Track a formal review gate for two optional additions: `statsmodels` for stronger
comparison diagnostics and `catboost` as an alternate GBM baseline. This track is about
decision reliability, not guaranteed QWK lift.

## Problem Statement

Current CV deltas can be small enough that we risk selecting noise wins. We need a more
formal way to compare runs and an alternate tree baseline to sanity-check model
selection.

## Proposed Solution

Run a targeted review with three checks:

- Compare top XGBoost variants using paired fold summaries (and bootstrap intervals)
  powered by `statsmodels`.
- Train a CatBoost baseline on the same prepared feature matrices and splits used by
  XGBoost.
- Evaluate impact on both mean QWK and worst-prompt slices using current residual
  diagnostics.

## Scope

- In scope:
  - dependency decision for `statsmodels` and `catboost` in `ml-research`,
  - minimal diagnostic/reporting additions,
  - CatBoost baseline experiment plan.
- Out of scope:
  - replacing XGBoost workflow by default without evidence,
  - adding new feature extraction pipelines.

## Risks / Unknowns

- Added dependencies may increase lockfile churn with limited performance benefit.
- CatBoost could match but not exceed XGBoost, yielding low ROI if diagnostics are
  sufficient without it.
- Over-interpreting small fold deltas without robust uncertainty summaries.

## Verdict

**Reviewer:** `agents`
**Date:** `2026-02-06`

### Decision Checklist

- [ ] Paired fold comparison protocol defined (mean/std + uncertainty interval).
- [ ] CatBoost prompt-holdout CV baseline completed on existing feature stores.
- [ ] Worst-prompt slice deltas reviewed against selected XGBoost baseline.
- [ ] Recommendation recorded in ADR-0031 and dependency research doc.

**Status:** `pending`

## Links

- Story:
  `TASKS/assessment/essay-scoring-statsmodels-diagnostics--catboost-baseline.md`
- Hub:
  `docs/reference/ref-essay-scoring-research-hub.md`
- Decision gate:
  `TASKS/assessment/essay-scoring-decision-gate-for-experiment-optimization-dependencies.md`
- ADR:
  `docs/decisions/0031-essay-scoring-experiment-optimization-dependencies-optuna-hf-training-baselines.md`
- Research:
  `docs/research/research-essay-scoring-dependency-decision-research-optuna-hf-fine-tuning-baselines.md`

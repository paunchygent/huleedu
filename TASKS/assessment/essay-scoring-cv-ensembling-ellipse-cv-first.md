---
id: 'essay-scoring-cv-ensembling-ellipse-cv-first'
title: 'essay-scoring: CV ensembling (ELLIPSE CV-first)'
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
  - 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
  - 'essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse'
labels: []
---
# essay-scoring: CV ensembling (ELLIPSE CV-first)

## Objective

Improve **out-of-sample** essay score prediction by reducing variance via simple CV-time
ensembling (bagging) without changing feature quality. Selection remains **CV-first** (never
“optimize on test”).

## Context

The current single-model training setup can overfit strongly and can be high-variance given:
- a high-capacity representation (768 embeddings + handcrafted features)
- skewed label distribution (weak tail support)

Recent AES work often reports large gains from **cross-validation ensembling**; we should test a
lightweight version of that idea that is easy to reproduce and explain.

## Plan

Prereqs:
- Reusable `splits.json` exists (see dataset+splits task).
- Baseline CV metrics exist for `feature_set=combined` under both schemes.

Implementation:
- Extend the research runner so CV can train **N models per fold** (different `seed`) and ensemble
  their predictions:
  - average continuous predictions (then apply the existing half-band rounding + clipping)
  - compute metrics on the ensembled predictions
- Persist ensemble metadata and per-fold metrics so we can compare single-model vs ensemble.

Experiments:
- Run CV on ELLIPSE with:
  - `scheme=stratified_text`
  - `scheme=prompt_holdout`
- Compare `ensemble_size=1` vs `ensemble_size in {3, 5}` and pick the smallest ensemble that gives
  stable uplift on **prompt-holdout** without destabilizing `stratified_text`.

Reporting:
- Add a concise table to the CV-first story showing mean±std QWK/MAE for:
  - baseline single model
  - best ensemble setting
- Record final “best current” recommendation (ensemble size, seeds strategy) in the story.

## Success Criteria

- CV runner supports `ensemble_size > 1` and produces a fold-aggregated report.
- We have mean±std QWK for single-model vs ensemble under both schemes.
- A decision is recorded: either “ensemble helps” (with chosen size) or “no meaningful uplift”
  (with evidence).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Tasks:
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`

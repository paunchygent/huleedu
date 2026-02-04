---
id: 'essay-scoring-ordinal-custom-objective-experiments-qwk'
title: 'essay-scoring: ordinal/custom objective experiments (QWK)'
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
# essay-scoring: ordinal/custom objective experiments (QWK)

## Objective

Test whether training objectives that better match the **ordinal, half-band** nature of essay
scores improve **CV QWK**, with **prompt-holdout mean QWK** as the primary yardstick for selection,
and reduce tail failure modes, without reducing feature quality.

## Context

We currently optimize a regression objective (`reg:squarederror`) and select by QWK early stopping.
That is a sensible baseline, but it may leave performance on the table because:
- QWK depends on **discrete half-band** agreement, not continuous MSE.
- Score labels are ordered (ordinal) and class imbalance is strong in the tails.

We want a small, controlled set of experiments that can be compared apples-to-apples under the
CV-first story.

## Plan

Prereqs:
- Reusable `splits.json` exists (see dataset+splits task).
- Baseline CV metrics exist for `feature_set=combined` under both schemes.

Implementation (keep scope tight; 2–3 variants max):
- Add training-mode support for at least:
  1) **Ordinal-as-multiclass**:
     - map half-band labels to class IDs
     - train `multi:softprob`
     - predict either expected band (probability-weighted) or argmax band
     - evaluate with existing QWK/MAE logic
  2) **Robust regression control** (optional if fast):
     - try an L1-like or robust loss variant available in XGBoost, to test whether it reduces
       over-penalization in tails (still evaluated by QWK).

Experiments:
- Run CV comparisons on ELLIPSE under:
  - `scheme=stratified_text`
  - `scheme=prompt_holdout`
- Use identical feature stores and split definitions for comparability.

Reporting:
- Produce a small comparison table:
  - objective/training mode → mean±std QWK, MAE, and a short “when it helps” note (if any).
- Record a decision in the CV-first story: keep baseline regression or switch modes.

## Success Criteria

- We have CV results for the baseline objective and at least one ordinal/custom variant under both
  schemes.
- A decision is recorded with evidence (improvement on prompt-holdout or “no win, keep baseline”).

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Tasks:
  - `TASKS/assessment/essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words.md`
  - `TASKS/assessment/essay-scoring-cv-baseline-stratified-text--prompt-holdout-on-ellipse.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`

---
id: 'essay-scoring-construct-validity-audit--feature-candidates'
title: 'essay-scoring: construct validity audit + feature candidates'
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
  - 'essay-scoring-residual-diagnostics-by-prompt-and-grade-band'
labels: []
---
# essay-scoring: construct validity audit + feature candidates

## Objective

Ensure the essay scorer’s strongest signals are **construct-relevant** (teacher-meaningful) and
not dominated by superficial proxies (length, mechanics), and then add a small set of cheap,
construct-aligned feature candidates to test under CV.

## Context

Current importance signals show grammar/spelling error rates and length/readability features are
high-impact. That is plausibly valid, but also risks a “shortcut model” that:
- over-penalizes language errors even when content/argumentation is strong, or
- relies too much on essay length as a proxy for quality.

We need an explicit audit loop that connects:
- residuals (where the model is wrong) +
- SHAP/feature contributions (why it was wrong)
…and then proposes feature additions that represent higher-level writing constructs.

Gate C reminder:
- The current baseline shows strong grade compression (rarely predicts 4.5/5.0) and a small set of
  prompts repeatedly underperform. The audit must explicitly check whether those prompts are
  construct-aligned with our discourse-essay scope (or represent a genre mismatch that should be
  excluded or handled separately).

## Plan

Prereqs:
- Residual diagnostics exist (or are implemented) for at least ELLIPSE test and ideally per CV fold:
  `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`.

Audit deliverable:
- Produce a short “construct validity audit” report that includes:
  - residual slices where we suspect shortcuts (very short essays, high error-rate essays)
  - correlation summaries (`y_pred` vs word_count, `y_pred` vs grammar_errors_per_100_words)
  - prompt-level failure modes (worst prompts with sample-size safeguards)
  - example-driven review guidance (what to read next in the dataset when a slice looks suspicious)

Feature candidates (keep cheap, no new heavy deps, no LLM calls):
- Add 2–3 Tier2/Tier3-ish features that better proxy organization/argumentation:
  - discourse marker density per 100 words (e.g., contrast/causal/conclusion markers)
  - conclusion/claim markers beyond binary intro/conclusion presence
  - simple cohesion proxy improvements (e.g., adjacent sentence similarity summary statistics)

Evaluation:
- Run CV on ELLIPSE (`prompt_holdout` prioritized) to validate that:
  - candidates do not regress generalization
  - candidates produce interpretable, teacher-meaningful SHAP contributions in error slices
  - candidates do not worsen tail slices (`y_true <= 2.0` and `y_true >= 4.0`) without an explicit tradeoff decision

Documentation:
- Update the CV-first story with audit findings + which candidate features are worth keeping.

## Success Criteria

- A construct validity audit report exists (with specific slices to investigate next).
- At least one candidate feature is implemented and evaluated under CV with:
  - non-negative effect on prompt-holdout mean QWK, and
  - a justification for keeping/dropping based on interpretability + diagnostics.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Task: `TASKS/assessment/essay-scoring-residual-diagnostics-by-prompt-and-grade-band.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`
- Research hub: `docs/reference/ref-essay-scoring-research-hub.md`

---
id: 'essay-scoring-ablation-handcrafted-vs-embeddings-vs-combined-on-ellipse'
title: 'essay-scoring: ablation (handcrafted vs embeddings vs combined) on ELLIPSE'
type: 'task'
status: 'proposed'
priority: 'high'
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
labels: []
---
# essay-scoring: ablation (handcrafted vs embeddings vs combined) on ELLIPSE

## Objective

Quantify the incremental value of each feature set on ELLIPSE:
- handcrafted-only
- embeddings-only
- combined

Run under CV (not a single split) so we can make robust decisions about what to invest in.

## Context

We need to know whether LanguageTool/spaCy handcrafted features materially improve generalization
once embeddings are present. This determines whether future effort should prioritize:
- scaling/optimizing LanguageTool capacity (if it matters), or
- embedding model/representation work (if handcrafted adds little), or
- both (if combined consistently wins).

## Plan

Prereq: baseline CV splits exist (see `essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words`).

Option A (preferred, explicit CV per feature set):
- Run three CV jobs with the same `splits.json` and `scheme`:
  - `--feature-set handcrafted`
  - `--feature-set embeddings`
  - `--feature-set combined`

Option B (only if you explicitly want single-run ablation):
- `pdm run essay-scoring-research ablation --dataset-kind ellipse --backend hemma --offload-service-url http://127.0.0.1:19000 --run-name ellipse_ablation_hemma_single_split`

Deliverable reporting:
- Add a short comparison table (mean±std QWK per feature set per scheme) to the story and append to
  `.claude/work/reports/essay-scoring/2026-02-04-ellipse-full-hemma-post-run-analysis.md`.

## Success Criteria

- For each scheme (`stratified_text`, `prompt_holdout`), we have:
  - CV mean±std QWK for each feature set
  - a clear winner and effect size (ΔQWK vs baseline)
- Decision-ready conclusion: is `combined` worth the extra feature extraction cost?

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`

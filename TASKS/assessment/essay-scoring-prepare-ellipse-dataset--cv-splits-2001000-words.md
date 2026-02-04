---
id: 'essay-scoring-prepare-ellipse-dataset--cv-splits-2001000-words'
title: 'essay-scoring: prepare ELLIPSE dataset + CV splits (200–1000 words)'
type: 'task'
status: 'done'
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
labels: []
---
# essay-scoring: prepare ELLIPSE dataset + CV splits (200–1000 words)

## Objective

Create a stable, reusable dataset artifact + CV split definition for ELLIPSE (Overall) that all
subsequent experiments can share, to prevent “split drift” and make results comparable.

## Context

The runbook standardizes ELLIPSE experiments to:
- word window: 200–1000 words
- prompt-level exclusions (letters / confounding prompts)

The research CLI expects a `splits.json` for CV (`pdm run essay-scoring-research cv`), and those
splits must be generated once and reused to make ablation/tuning decisions meaningful.

## Plan

- Prepare dataset artifacts + integrity report:
  - `pdm run essay-scoring-research prepare-dataset --dataset-kind ellipse --min-words 200 --max-words 1000 --run-name ellipse_prep_200_1000`
- Generate split definitions for both generalization regimes:
  - `pdm run essay-scoring-research make-splits --dataset-kind ellipse --ellipse-train-path <prepared_train.csv> --ellipse-test-path <prepared_test.csv> --min-words 200 --max-words 1000 --n-splits 5 --run-name ellipse_splits_200_1000`
- Record outputs (paths) in the story and in the run log section of `docs/operations/ml-nlp-runbook.md`.

## Success Criteria

- A prepared train/test CSV exists under `output/essay_scoring/<RUN>/artifacts/datasets/`.
- A reusable `splits.json` exists under `output/essay_scoring/<RUN>/artifacts/splits.json`.
- Follow-up tasks can run CV using only `--splits-path <.../splits.json>` + `--reuse-cv-feature-store-dir ...`.

## Related

- Story: `TASKS/assessment/improve-essay-scoring-prediction-power-ellipse-cv-first.md`
- Runbook: `docs/operations/ml-nlp-runbook.md`

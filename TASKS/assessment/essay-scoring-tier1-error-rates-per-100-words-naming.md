---
id: 'essay-scoring-tier1-error-rates-per-100-words-naming'
title: 'essay-scoring tier1 error rates per 100 words naming'
type: 'task'
status: 'done'
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
# essay-scoring tier1 error rates per 100 words naming

## Objective

Make Tier 1 error-rate feature names explicitly include their units: “per 100 words”.

## Context

Tier 1 currently computes grammar/spelling/punctuation as densities per 100 words, but the feature
names (`grammar_density`, `spelling_density`, `punctuation_density`) do not encode the unit, which
is easy to misinterpret during analysis.

This repo is a prototype: changing feature names is acceptable, and the feature store schema is
versioned. The goal is clarity and preventing analytic mistakes.

## Plan

- Rename Tier 1 feature names and Pydantic fields:
  - `grammar_density` → `grammar_errors_per_100_words`
  - `spelling_density` → `spelling_errors_per_100_words`
  - `punctuation_density` → `punctuation_errors_per_100_words`
- Update Tier 1 extractor to populate the renamed fields.
- Update any tests and feature-schema ordering helpers.
- Add a small ADR documenting the decision (units encoded in names).

## Success Criteria

- Tier 1 counts are still computed via `density_per_100_words(...)`.
- Feature names written into `feature_schema.json` and feature stores include “per_100_words”.
- Pipeline tests pass and typecheck succeeds.

## Related

- Code: `scripts/ml_training/essay_scoring/features/tier1_error_readability.py`
- Code: `scripts/ml_training/essay_scoring/features/schema.py`
- Runbook: `docs/operations/ml-nlp-runbook.md` (Tier 1 notes)
- Decision: `docs/decisions/0030-essay-scoring-tier1-error-rate-feature-names-include-units.md`

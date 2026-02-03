---
id: 'essay-scoring-research-warm-cache-feature-store--10-90-scale-alignment'
title: 'Essay scoring research: warm-cache feature store + 1.0-9.0 scale alignment'
type: 'task'
status: 'done'
priority: 'medium'
domain: 'assessment'
service: ''
owner_team: 'agents'
owner: ''
program: ''
created: '2026-02-02'
last_updated: '2026-02-02'
related:
  - docs/product/epics/ml-essay-scoring-pipeline.md
  - docs/decisions/0021-ml-scoring-integration-in-nlp-service.md
  - docs/research/epic-010-ml-essay-scoring-source-traceability.md
  - TASKS/assessment/nlp_lang_tool/nlp-lang-tool-whitebox-research-build.md
labels:
  - nlp
  - essay-scoring
  - whitebox
  - research
  - performance
  - docs
---
# Essay scoring research: warm-cache feature store + 1.0-9.0 scale alignment

## Objective

Make essay-scoring research iterations fast and trustworthy by:
1) optimizing for warm-cache experimentation (reusing extracted features across runs), and
2) aligning the documented target scale to IELTS Overall bands 1.0–9.0.

## Context

The current research pipeline runs end-to-end but is too slow for systematic tuning:
- Latest full run (combined features + Hemma Tier2 offload) took ~14 minutes with feature
  extraction dominating runtime, while model training is ~seconds.
- The slowest parts are Tier3 and Tier1 feature extraction, which repeatedly re-run spaCy
  parsing.

Separately, the documentation is inconsistent about the target label scale:
- The research pipeline and grade-scale report operate on IELTS Overall 1.0–9.0.
- ADR/EPIC text still references 5.0–7.5 in places, which no longer matches the pipeline.

## Plan

1. Add a reusable “feature store” artifact format:
   - `featurize` command that writes split manifest + feature matrices + labels.
   - `run` command option to reuse a feature store for fast hyperparameter iteration.
2. Reduce feature extraction time:
   - Tier1: single-pass spaCy doc usage (no repeated `nlp(text)` calls).
   - Tier3: single-pass spaCy doc usage and tokenizer-only logic where possible.
   - Keep behavior stable and add focused unit tests.
3. Documentation alignment:
   - Update ADR-0021 and EPIC-010 to explicitly state the 1.0–9.0 target scale.

## Success Criteria

- Warm-cache loop supported:
  - `essay-scoring-research featurize ...` produces a reusable feature store directory.
  - `essay-scoring-research run --reuse-feature-store-dir <dir> ...` skips feature extraction.
- Feature extraction faster on repeated runs (measurable reduction in Tier1/Tier3 time).
- ADR-0021 and EPIC-010 consistently reference IELTS Overall 1.0–9.0.
- Tests added for the feature store and Tier refactors; test suite passes.

## Completed (2026-02-02)

- Added `featurize` + feature store persistence and `run --reuse-feature-store-dir` reuse path.
- Added `--skip-shap` and `--skip-grade-scale-report` flags for fast sweeps.
- Refactored Tier1/Tier3 to avoid repeated spaCy passes; Tier2/Tier3 now use a readability-free spaCy pipeline.
- Removed dataset row deduping that could drop legitimate essays; feature store now relies on per-row `record_id`
  to keep splits deterministic even with identical essay content.
- Bumped feature store schema to require re-featurize after record-id change.
- Updated ADR-0021 + EPIC-010 to 1.0–9.0 scale alignment.
- Verified:
  - `pdm run pytest-root scripts/ml_training/essay_scoring/tests -v`
  - `pdm run format-all`
  - `pdm run lint-fix --unsafe-fixes`
  - `pdm run typecheck-all`
  - `pdm run validate-tasks`
  - `pdm run validate-docs`
  - `pdm run index-tasks`

## Related

- `scripts/ml_training/essay_scoring/` (research pipeline implementation)
- `docs/product/epics/ml-essay-scoring-pipeline.md`
- `docs/decisions/0021-ml-scoring-integration-in-nlp-service.md`

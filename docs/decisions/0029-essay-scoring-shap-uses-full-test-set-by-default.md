---
type: decision
id: ADR-0029
status: accepted
created: '2026-02-04'
last_updated: '2026-02-04'
---
# ADR-0029: essay-scoring shap uses full test set by default

## Status

Accepted (2026-02-04)

## Context

The essay-scoring research runner generates SHAP artifacts after training to support post-run
analysis and feature diagnostics.

Previously, SHAP generation sampled at most 500 rows, producing `shap_values.npy` with shape
`(500, n_features)`. This sampling can miss behavior in the tails and makes SHAP-based summaries
less representative for post-run analysis.

User requirement for research runs:
- SHAP must be computed on the full evaluation set by default (the runner uses the test split).

## Decision

Change the default SHAP configuration to compute SHAP values for the full test split (no sampling).

Implementation detail:
- The SHAP helper keeps an explicit `max_samples` parameter for debugging/tests, but the default
  is now “no sampling”.

## Consequences

Positive:
- SHAP artifacts become representative by default and suitable for “full post-run” analysis.
- Eliminates ambiguity about whether SHAP is a subsample.

Negative / tradeoffs:
- SHAP runtime and artifact size increase with test set size.
  - For ELLIPSE (`n_test=2430`, `n_features=793`), `shap_values.npy` is feasible but larger than
    a 500-row sample.

Operational notes:
- Prefer `featurize` + `run --reuse-feature-store-dir ...` for SHAP runs so the SHAP computation is
  not conflated with feature extraction throughput.

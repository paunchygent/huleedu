---
type: decision
id: ADR-0030
status: accepted
created: '2026-02-04'
last_updated: '2026-02-04'
---
# ADR-0030: essay-scoring tier1 error-rate feature names include units

## Status

Accepted (2026-02-04)

## Context

Tier 1 features in the essay-scoring research pipeline include:
- counts of LanguageTool-detected issues (grammar/spelling/punctuation)
- normalized as densities per 100 words (so the feature values are length-normalized)

The implementation already computes these as `density_per_100_words(...)`, but the feature names
did not encode the unit, which is easy to misread during analysis and post-run reporting.

## Decision

Rename Tier 1 error-rate feature names to explicitly include the unit “per 100 words”:
- `grammar_density` → `grammar_errors_per_100_words`
- `spelling_density` → `spelling_errors_per_100_words`
- `punctuation_density` → `punctuation_errors_per_100_words`

## Consequences

Positive:
- Removes ambiguity in downstream analysis (SHAP, feature importance, regression diagnostics).
- Makes feature semantics self-documenting without requiring a separate unit table.

Tradeoffs:
- Feature names change in artifacts (`feature_schema.json`, feature stores), so older runs will not
  be directly comparable by name without mapping. This is acceptable in this prototype repo.

Operational:
- Feature store schema versions are bumped so older cached feature stores are rejected, preventing
  silent reuse of stale feature naming in new experiments.

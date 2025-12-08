---
type: decision
id: ADR-0017
status: proposed
created: 2025-11-27
last_updated: 2025-12-07
---

# ADR-0017: CJ Assessment Wave-Based Submission Pattern

## Status
Proposed

## Context
CJ Assessment must submit comparison tasks to LLM Provider. Options:
1. Submit all comparisons at once (flood approach)
2. Submit in waves with stability checks between

## Decision
Implement **wave-based staged submission** for serial bundle mode using the existing callback-first continuation path (no separate iterative helper in `comparison_processing`).

### Wave Pattern
1. Submit N comparisons (wave size configurable)
2. Wait for all callbacks in wave
3. Run BT scoring and stability check
4. If stable or budget exhausted: finalize
5. Else: dispatch next wave

### Configuration

Wave size (comparisons per callback iteration) is emergent from batch size,
the matching strategy, and `MAX_PAIRWISE_COMPARISONS`; there is no dedicated
per-wave cap. Stability is governed by:

- `MIN_COMPARISONS_FOR_STABILITY_CHECK`
- `SCORE_STABILITY_THRESHOLD`
- `MAX_PAIRWISE_COMPARISONS`

### Callback-First Completion
1. LLM requests are async
2. Callbacks update completed/failed counters + last_activity_at
3. Continuation triggers when `callbacks_received == submitted_comparisons` via `workflow_continuation.trigger_existing_workflow_continuation`
4. `trigger_existing_workflow_continuation` recomputes BT scores, checks stability, and decides whether to request additional comparisons via `comparison_processing.request_additional_comparisons_for_batch` or finalize

### Wave-Aligned Bundling Hints (CJ → LLM Provider)

Wave size is an internal CJ concept (how many comparisons are generated per
iteration), but LLM Provider owns the queue and bundle sizes used for actual
provider calls. To keep these aligned without coupling implementations:

- CJ emits a **soft hint** `preferred_bundle_size` in the metadata of each
  `LLMComparisonRequest`:
  - Initial waves use `preferred_bundle_size = len(comparison_tasks)` for that
    submission.
  - Retry waves use `preferred_bundle_size = len(retry_tasks)` for the retry
    bundle.
  - Hints are capped at `64` in CJ before being sent.
- LLM Provider Service reads this hint and computes an effective per-bundle
  limit as:

  ```text
  effective_limit = min(preferred_bundle_size or SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL,
                        SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL)
  ```

- `SERIAL_BUNDLE_MAX_REQUESTS_PER_CALL` remains the authoritative operational
  safety cap (default `64`, clamped to `[1, 64]` in settings). CJ hints can
  reduce the bundle size for a given wave but can never push it above this cap.

This keeps CJ’s wave semantics and LPS’s bundling behaviour loosely coupled:
wave size can evolve with matching strategies and budgets, while LPS preserves
global safeguards and multi-tenant resilience.

## Consequences

### Positive
- Earlier convergence detection
- Lower cost (stop early when stable)
- Better observability per wave
- Avoids flooding LLM provider

### Negative
- Latency between waves
- More complex state management
- Requires callback tracking

## Recovery
- BatchMonitor timeout: 4h prod, 1h dev
- Recovery-only safety net (not primary completion trigger)

## References
- docs/operations/cj-assessment-runbook.md
- services/cj_assessment_service/cj_core_logic/workflow_continuation.py

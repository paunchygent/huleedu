---
type: decision
id: ADR-0015
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0015: CJ Assessment Convergence Tuning Strategy

## Status
Proposed

## Context
CJ Assessment uses Bradley-Terry scoring to rank essays. The system must decide when scores have converged sufficiently to stop requesting more comparisons. Options:
1. Fixed comparison count (simple but wasteful)
2. Dynamic stability detection (stop early when scores stabilize)

## Decision
Implement **dynamic stability-based convergence** with tunable thresholds.

### Key Settings

| Setting | Default | Purpose |
|---------|---------|---------|
| SCORE_STABILITY_THRESHOLD | 0.025 | Max score change to consider stable |
| MIN_COMPARISONS_FOR_STABILITY_CHECK | 8 | Minimum before checking stability |
| COMPARISONS_PER_STABILITY_CHECK_ITERATION | 8 | Round size between checks |

### Convergence Logic
1. After each round of comparisons, recompute BT scores
2. Check if max score change < SCORE_STABILITY_THRESHOLD
3. Stop if stable AND sufficient comparisons completed
4. Otherwise dispatch next round

### Completion Denominator
```python
completion_denominator = min(
    total_budget or total_comparisons,
    nC2(expected_essay_count)  # n*(n-1)/2
)
```

## Consequences

### Positive
- Early convergence saves LLM costs
- Adaptive to dataset characteristics
- Per-assignment tuning possible

### Negative
- Threshold selection requires experimentation
- More complex than fixed count

## Tuning Plan
- Sweep SCORE_STABILITY_THRESHOLD (0.025–0.05) with ENG5 Runner
- Measure cost vs agreement vs iterations per assignment type

## References
- docs/operations/cj-assessment-foundation.md
- services/cj_assessment_service/

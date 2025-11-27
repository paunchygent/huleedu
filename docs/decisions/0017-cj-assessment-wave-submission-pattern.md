---
type: decision
id: ADR-0017
status: proposed
created: 2025-11-27
last_updated: 2025-11-27
---

# ADR-0017: CJ Assessment Wave-Based Submission Pattern

## Status
Proposed

## Context
CJ Assessment must submit comparison tasks to LLM Provider. Options:
1. Submit all comparisons at once (flood approach)
2. Submit in waves with stability checks between

## Decision
Implement **wave-based staged submission** for serial bundle mode.

### Wave Pattern
1. Submit N comparisons (wave size configurable)
2. Wait for all callbacks in wave
3. Run BT scoring and stability check
4. If stable or budget exhausted: finalize
5. Else: dispatch next wave

### Configuration
```python
MAX_BUNDLES_PER_WAVE: int = 10  # Comparisons per wave
```

### Callback-First Completion
1. LLM requests are async
2. Callbacks update completed/failed counters + last_activity_at
3. Continuation triggers when callbacks_received == submitted_comparisons
4. Recompute BT scores, check stability, decide next action

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
- docs/operations/cj-assessment-foundation.md
- services/cj_assessment_service/cj_core_logic/workflow_continuation.py

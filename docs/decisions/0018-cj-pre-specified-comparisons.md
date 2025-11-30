---
type: decision
id: ADR-0018
status: proposed
created: 2025-11-30
last_updated: 2025-11-30
---

# ADR-0018: CJ Pre-Specified Comparisons for Controlled Experiments

## Status
Proposed

## Context
Research experiments (e.g., ENG5 prompt tuning) require controlled pairwise comparisons with:
1. Exact pair control (specific essay A vs essay B)
2. Position control (which essay appears as position A vs B)
3. Iteration support (run same pair N times for statistical analysis)

Current CJ service generates pairs internally via `pair_generation.py` and randomizes A/B positions. No mechanism exists for caller-specified pairs.

### Options Considered
1. **Bypass CJ**: Call LLM Provider directly - loses cache-aware prompt composition and Kafka flow
2. **Multiple batches**: Submit 40 separate 2-essay batches - 40x overhead, still no position control
3. **Extend CJ**: Add `pre_specified_comparisons` field - full control while preserving CJ features

## Decision
Extend `ELS_CJAssessmentRequestV1` with optional `pre_specified_comparisons` field.

### Event Contract Extension
```python
@dataclass
class PreSpecifiedComparison:
    """Pre-specified comparison pair with explicit positions."""
    essay_a_id: str  # Position A essay ID
    essay_b_id: str  # Position B essay ID

# In ELS_CJAssessmentRequestV1:
pre_specified_comparisons: list[PreSpecifiedComparison] | None = None
```

### Pair Generation Bypass
When `pre_specified_comparisons` is provided:
1. Skip standard pair matching strategy
2. Map essay IDs to `EssayForComparison` objects
3. Build `ComparisonTask` for each specified pair
4. NO position randomization (caller controls positions)
5. Validate all essay IDs exist in request

### Use Case: Boundary Testing
```
--boundary-pairs "003_E-:001_F+,005_D-:004_E+"
--boundary-iterations 10

Result: 2 pairs × 10 iterations × 2 positions = 40 pre-specified comparisons
```

## Consequences

### Positive
- Full pair and position control for controlled experiments
- Preserves all CJ features (prompt caching, cost tracking, batch semantics)
- Single batch submission (efficient prompt caching across all comparisons)
- Reusable for any future controlled experiment scenarios

### Negative
- Event contract extension (backwards compatible - optional field)
- Additional code path in pair_generation.py
- Caller responsible for generating valid pair specifications

## References
- EPIC-008: ENG5 NP Runner Refactor & Prompt Tuning (US-008.4)
- services/cj_assessment_service/cj_core_logic/pair_generation.py
- libs/common_core/src/common_core/events/cj_assessment_events.py

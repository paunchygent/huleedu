# Investigation Report: Premature Batch Finalization Bug

## Investigation Summary

**Problem Statement**: A CJ assessment batch (ID unknown from log snippet) finalized at 72 comparisons despite:
- `stability_passed: False` (max_score_change: 1.48)
- `budget_exhausted: False` (78 pairs remaining from 150 budget)
- `callbacks_reached_cap: True` triggered finalization anyway

**Investigation Date**: 2025-11-29  
**Investigator**: Research-Diagnostic Agent  
**Scope**: CJ Assessment Service workflow_continuation.py finalization logic  
**Root Cause**: Incorrect finalization logic in `trigger_existing_workflow_continuation`

---

## Evidence Collected

### 1. Log Evidence (Provided by User)

```
stability_passed: False, max_score_change: 1.4828852269000299, 
pairs_remaining: 78, budget_exhausted: False, should_finalize: True,
callbacks_reached_cap: True, completion_denominator: 66
```

**Key Observations**:
- 72 callbacks received (inferred from 150 - 78 = 72)
- completion_denominator: 66
- callbacks_reached_cap: True (because 72 >= 66)
- This triggered finalization despite stability failure

### 2. Code Inspection: workflow_continuation.py

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/cj_core_logic/workflow_continuation.py`

#### Critical Lines (195-297):

```python
# Line 195: Calculate if callbacks reached the cap
callbacks_reached_cap = denominator > 0 and callbacks_received >= denominator

# Line 297: The problematic finalization decision
should_finalize = stability_passed or callbacks_reached_cap or budget_exhausted
```

**Evidence**: The logic uses **OR** between three conditions, meaning ANY single condition triggers finalization.

### 3. completion_denominator() Implementation

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/models_db.py`

**Lines 307-321**:
```python
def completion_denominator(self) -> int:
    """Return the denominator to use for completion math."""
    max_possible_pairs = self._max_possible_comparisons()

    if self.total_budget and self.total_budget > 0:
        if max_possible_pairs:
            return min(self.total_budget, max_possible_pairs)
        return self.total_budget

    if self.total_comparisons and self.total_comparisons > 0:
        if max_possible_pairs:
            return min(self.total_comparisons, max_possible_pairs)
        return self.total_comparisons

    return max_possible_pairs
```

**Lines 323-340**:
```python
def _max_possible_comparisons(self) -> int:
    """Compute the n-choose-2 upper bound for this batch."""
    try:
        essay_count = None
        if self.batch_upload and self.batch_upload.expected_essay_count:
            essay_count = self.batch_upload.expected_essay_count
        if isinstance(essay_count, int) and essay_count > 1:
            return (essay_count * (essay_count - 1)) // 2
    except Exception:
        return 0
    return 0
```

**Evidence**: For 12 essays, nC2 = (12 * 11) / 2 = 66, which matches the log entry's `completion_denominator: 66`.

### 4. Configuration Values

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/config.py`

```python
MAX_PAIRWISE_COMPARISONS: int = 150  # Line 194
MIN_COMPARISONS_FOR_STABILITY_CHECK: int = 12  # Line 203-205
SCORE_STABILITY_THRESHOLD: float = 0.05  # Line 207
```

### 5. Architectural Documentation

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/docs/architecture/cj-assessment-service-map.md`

**Lines 10-56** define the completion semantics:

> When an iteration completes, `trigger_existing_workflow_continuation` decides between three paths:
> 
> - **Finalize successfully** when stability has passed, **or** when the callback count has reached the batch's `completion_denominator()` [...], **or** when the global comparison budget is exhausted.

**Evidence**: The documentation explicitly states the OR logic is intentional.

### 6. Task Documentation

**File**: `/Users/olofs_mba/Documents/Repos/huledu-reboot/TASKS/assessment/us-0052-score-stability-semantics-and-early-stopping.md`

**Lines 35-38** (Acceptance Criteria):

> Finalization happens only when **one** of these is true:
> - Stability passed (as above), or
> - `callbacks_received` has reached the `completion_denominator()`, or
> - Global budget is exhausted (`submitted_comparisons >= MAX_PAIRWISE_COMPARISONS`)

**Evidence**: The current task documentation defines the SAME behavior as the bug. This is the expected behavior according to US-0052.

---

## Root Cause Analysis

### Primary Cause: Semantic Mismatch Between completion_denominator and Budget

The `completion_denominator()` represents the **maximum possible unique pairs** for the batch (nC2), which is:
- For 12 essays: 66 pairs
- This is LESS than the global budget (150 pairs)

**The Logic Flow**:
1. Batch has 12 essays → completion_denominator = 66
2. Batch processes comparisons and receives 72 callbacks (completed + failed)
3. Line 195: `callbacks_reached_cap = 72 >= 66` → **True**
4. Line 297: `should_finalize = False OR True OR False` → **True**
5. Batch finalizes despite:
   - Not reaching stability (max_score_change: 1.48 > 0.05)
   - Having 78 pairs remaining in budget (150 - 72 = 78)

### Contributing Factors

1. **completion_denominator vs Budget Confusion**:
   - `completion_denominator()` returns `min(total_budget, nC2)` = min(150, 66) = 66
   - This makes sense for small batches (don't inherit large global budgets)
   - BUT it means "cap reached" triggers at 66 callbacks, not 150

2. **Phase-1 vs Phase-2 Semantics Not Implemented**:
   - According to handoff.md (lines 156-180), there should be a Phase-2 resampling mode
   - Phase 1: Unique coverage of nC2 graph
   - Phase 2: Resample same graph for stability
   - **Current code has no Phase-2 logic**, so hitting nC2 triggers finalization

3. **Success-Rate Guard is Separate**:
   - PR-2 added success-rate checking (lines 198-215, 300-371)
   - This ONLY applies when `should_finalize` is already True
   - It can route to `finalize_failure` but doesn't prevent finalization decision

### Evidence Chain

```
12 essays → nC2 = 66
↓
completion_denominator() returns min(150, 66) = 66
↓
72 callbacks received (completed + failed)
↓
callbacks_reached_cap = (72 >= 66) = True
↓
should_finalize = (False OR True OR False) = True
↓
Batch finalizes at 72 comparisons despite:
  - stability_passed: False (1.48 > 0.05 threshold)
  - budget_exhausted: False (78 pairs remaining)
```

### Eliminated Alternatives

**Alternative Hypothesis 1**: Bug in completion_denominator calculation
- **Ruled Out**: Math is correct: 12 essays → 66 pairs = (12 * 11) / 2
- **Evidence**: Line 336 in models_db.py is mathematically sound

**Alternative Hypothesis 2**: Incorrect callback counting
- **Ruled Out**: The log shows 72 callbacks received vs 66 denominator
- **Evidence**: check_workflow_continuation (lines 43-80) correctly sums completed + failed

**Alternative Hypothesis 3**: Configuration error
- **Ruled Out**: MAX_PAIRWISE_COMPARISONS: 150 is reasonable
- **Evidence**: The issue is semantic, not configurational

---

## Architectural Compliance

### Pattern Violations

**Violation**: The current implementation **does not align with EPIC-005 intent**

From `.claude/work/session/handoff.md` (lines 156-180):

> - Phase 1: spend comparison budget on **unique coverage** of the n-choose-2 essay graph
> - Phase 2: once unique coverage is complete and stability has not passed, spend additional budget on **resampling the same graph**

**Current Behavior**: 
- No Phase-2 resampling exists
- `callbacks_reached_cap` triggers immediate finalization at nC2
- This wastes the remaining 78 pairs of budget (150 - 72)

### Rule Conflicts

**Conflict with US-0052 Acceptance Criteria** (lines 35-38):

The task doc states finalization should happen when ONE of:
1. Stability passed
2. callbacks_reached_cap
3. Budget exhausted

**BUT** this doesn't account for the fact that:
- `callbacks_reached_cap` means "reached nC2 unique pairs"
- `budget_exhausted` means "reached MAX_PAIRWISE_COMPARISONS"
- These are DIFFERENT thresholds for small batches

**The Intent** (from handoff.md) seems to be:
- Phase 1: Fill nC2 unique pairs (what completion_denominator represents)
- Phase 2: If still unstable, use remaining budget to resample
- Finalize only when: stability OR (Phase-2 exhausted) OR (no budget)

### Best Practice Gaps

1. **Missing Phase-2 Logic**: No resampling implementation exists
2. **Premature Optimization**: Small batches can't leverage full budget for convergence
3. **Semantic Naming**: `callbacks_reached_cap` should be `unique_pairs_saturated`
4. **Documentation Gap**: No clear explanation of Phase-1 vs Phase-2 in code comments

---

## Recommended Next Steps

### 1. Immediate Actions (Clarification Required)

**Question for User**: What is the intended behavior when:
- stability_passed: False
- unique pairs saturated (callbacks >= nC2)
- budget remaining (callbacks < MAX_PAIRWISE_COMPARISONS)

**Option A**: Current behavior is correct
- Finalize after unique coverage complete, ignore remaining budget
- Accept that small batches may be unstable
- Document this explicitly

**Option B**: Implement Phase-2 resampling
- After nC2 saturated, continue requesting comparisons (resampling same pairs)
- Use remaining budget to improve stability
- Finalize only when: stability OR budget_exhausted OR max_iterations

### 2. Implementation Tasks (If Option B)

**Task 1**: Add Phase-2 state tracking
- Add `phase: Literal["unique_coverage", "resampling"]` to CJBatchState
- Track when unique coverage is complete
- Switch to resampling mode when `callbacks >= completion_denominator` but stability not reached

**Task 2**: Modify finalization logic
```python
# Current (Line 297)
should_finalize = stability_passed or callbacks_reached_cap or budget_exhausted

# Proposed
unique_pairs_saturated = denominator > 0 and callbacks_received >= denominator
should_finalize = (
    stability_passed 
    or (unique_pairs_saturated and budget_exhausted)
    or budget_exhausted
)
```

**Task 3**: Update comparison_processing.py
- When in resampling phase, allow re-requesting already-compared pairs
- Track resampling passes with small-net guards (see handoff.md lines 168-180)

**Task 4**: Update tests
- Add test for "unique pairs saturated but budget remains → continues"
- Add test for "resampling phase reaches max budget → finalizes"
- Add test for "resampling phase reaches stability → finalizes early"

### 3. Testing Requirements

**Validation Scenario 1**: 12-essay batch (nC2 = 66)
- Submit 66 unique comparisons
- stability_passed: False
- Expect: Request additional comparisons up to 150 budget
- Verify: Does not finalize until stability OR budget exhausted

**Validation Scenario 2**: 4-essay batch (nC2 = 6)
- Submit 6 unique comparisons
- stability_passed: False
- MAX_PAIRWISE_COMPARISONS: 150
- Expect: Enter resampling mode with small-net guard
- Verify: Caps resampling passes (see MAX_RESAMPLING_PASSES_FOR_SMALL_NET)

### 4. Documentation Updates

**File**: `services/cj_assessment_service/cj_core_logic/workflow_continuation.py`
- Add docstring explaining Phase-1 vs Phase-2 semantics
- Document completion_denominator as "unique pairs saturation point"
- Clarify budget vs denominator distinction

**File**: `TASKS/assessment/us-0052-score-stability-semantics-and-early-stopping.md`
- Update acceptance criteria to distinguish Phase-1 and Phase-2
- Add explicit scenario for "unique coverage complete but unstable"

**File**: `docs/architecture/cj-assessment-service-map.md`
- Expand completion semantics section (lines 10-56)
- Add Phase-2 resampling explanation
- Include example calculations for small vs large batches

### 5. Agent Handoffs

**To Implementation Agent** (if Option B chosen):
- Read this report
- Review handoff.md lines 156-180 for Phase-2 spec
- Implement Phase-2 state tracking and resampling logic
- Update workflow_continuation.py finalization conditions
- Create tests per Validation Scenarios above

**To Documentation Agent**:
- Update architectural docs with Phase-1/Phase-2 distinction
- Add examples to runbook for small batch behavior
- Update US-0052 acceptance criteria

---

## Supporting Evidence

### Code Locations

| Component | File Path | Line Numbers |
|-----------|-----------|--------------|
| Finalization Logic | `/services/cj_assessment_service/cj_core_logic/workflow_continuation.py` | 195, 297, 300-371 |
| completion_denominator | `/services/cj_assessment_service/models_db.py` | 307-340 |
| Configuration | `/services/cj_assessment_service/config.py` | 194, 203-207 |
| Architecture Doc | `/docs/architecture/cj-assessment-service-map.md` | 10-56 |
| Task Spec | `/TASKS/assessment/us-0052-score-stability-semantics-and-early-stopping.md` | 35-38 |
| Handoff Context | `/.claude/work/session/handoff.md` | 156-180 |

### Bash Commands Used

```bash
# Verified CJ service files exist
ls -la /Users/olofs_mba/Documents/Repos/huledu-reboot/services/cj_assessment_service/

# Searched for completion_denominator references
grep -r "completion_denominator" services/cj_assessment_service/

# Searched for callbacks_reached_cap logic
grep -r "callbacks_reached_cap" services/cj_assessment_service/
```

---

## Conclusion

**Root Cause**: The finalization logic in `workflow_continuation.py` (line 297) uses an OR condition that triggers finalization when `callbacks_reached_cap` is True, regardless of stability or remaining budget. For small batches where `completion_denominator < MAX_PAIRWISE_COMPARISONS`, this causes premature finalization.

**Is This a Bug?**: **Ambiguous**
- According to current task docs (US-0052), this is **expected behavior**
- According to EPIC-005 intent (handoff.md Phase-2 spec), this is a **missing feature**

**Recommended Action**: 
1. Clarify with user whether Option A (current) or Option B (Phase-2 resampling) is desired
2. If Option B: Implement Phase-2 resampling logic per Implementation Tasks above
3. If Option A: Document current behavior explicitly and close as "working as designed"

**Next Agent**: Implementation specialist (if Option B) or Documentation specialist (if Option A)

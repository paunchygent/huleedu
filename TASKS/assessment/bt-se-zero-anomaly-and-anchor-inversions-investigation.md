---
id: 'bt-se-zero-anomaly-and-anchor-inversions-investigation'
title: 'BT SE Zero Anomaly and Anchor Inversions Investigation'
type: 'task'
status: 'in_progress'
priority: 'high'
domain: 'assessment'
service: 'cj_assessment_service'
owner_team: 'agents'
owner: ''
program: ''
created: '2025-11-29'
last_updated: '2025-11-29'
related: ['.claude/work/reports/2025-11-29-bt-se-anchor-inversion-analysis.md']
labels: ['bug', 'quality']
---
# BT SE Zero Anomaly and Anchor Inversions Investigation

## Objective

Investigate and fix two issues discovered during ENG5 batch validation:
1. **SE = 0 Bug**: Student essay TUVA_KARLSSON has exactly zero standard error
2. **Anchor Inversions**: Several anchor essays ranked contrary to their assigned grades

## Context

During validation of batch `364d4746-b34e-4038-b825-0f6f9d7e2251` (2025-11-29), two anomalies were detected:

### Issue 1: SE = 0 for Student Essay

TUVA_KARLSSON has `current_bt_se = 0.0` despite having 17 comparisons. Standard error should never be exactly zero for a well-connected node.

**Root Cause:** BT inference uses the last item (by index) as the reference parameter for model identifiability. Reference items have SE = 0 by mathematical construction. TUVA_KARLSSON happened to sort last alphabetically in the essay ID array, making it the unintended reference.

**Code Location:** `services/cj_assessment_service/cj_core_logic/bt_inference.py:56-57, 121`

### Issue 2: Anchor Grade Inversions (ROOT CAUSE IDENTIFIED)

Three anchor grade inversions detected:
- ANCHOR_3 (C-) ranked below ANCHOR_9 (D+)
- ANCHOR_8 (D-) ranked below ANCHOR_11 (E+)
- ANCHOR_7 (E-) ranked below F+ anchors

**Root Cause: LLM-Expert Judgment Misalignment**

Investigation revealed systematic divergence between LLM holistic judgment and expert grading criteria, specifically in the lower grade range (C-/D/E/F).

**Evidence:**

| Grade | Anchor | Win Rate | Expected | Status |
|-------|--------|----------|----------|--------|
| A | ANCHOR_12 | 82% | ~80% | ✓ |
| A | ANCHOR_10 | 71% | ~80% | ❌ Matches B |
| B | ANCHOR_2,5 | 71% | ~70% | ✓ |
| C-| ANCHOR_3 | 25% | ~35% | ❌ Matches E+ |
| D+ | ANCHOR_9 | 38% | ~30% | ❌ Higher than C- |
| E+ | ANCHOR_11 | 25% | ~20% | ❌ Matches C- |
| E- | ANCHOR_7 | 0% | ~15% | ❌ Lost ALL 17 |
| F+ | ANCHOR_1,4 | 6-12% | ~10% | ✓ |

**Analysis:**
- Upper grades (A/B) calibrate correctly
- Lower grades (C-/D/E/F) systematically misaligned
- LLM favors narrative structure, argumentation breadth over expert criteria
- Expert graders use subject-specific E/F boundary criteria not captured in rubric

**Implication:** CJ assumes pairwise judgments align with anchor grading criteria. When LLM systematically diverges in certain grade regions, calibration breaks down.

### Complete Win-Loss Statistics (Batch 108)

#### All Anchors

| Anchor | Grade | Wins | Losses | Total | Win Rate | BT Score | BT SE | Expected Rank | Actual Rank |
|--------|-------|------|--------|-------|----------|----------|-------|---------------|-------------|
| ANCHOR_12 | A | 14 | 3 | 17 | 82% | 3.72 | 1.00 | 1 | 1 ✓ |
| ANCHOR_10 | A | 12 | 5 | 17 | 71% | 2.31 | 0.93 | 2 | 4 ❌ |
| ANCHOR_2 | B | 12 | 5 | 17 | 71% | 2.95 | 0.95 | 3 | 2 |
| ANCHOR_5 | B | 12 | 5 | 17 | 71% | 2.94 | 0.95 | 4 | 3 |
| ANCHOR_6 | C+ | 7 | 10 | 17 | 41% | -0.03 | 1.05 | 5 | 5 ✓ |
| ANCHOR_3 | C- | 4 | 12 | 16 | 25% | -1.99 | 1.26 | 6 | 7 ❌ |
| ANCHOR_9 | D+ | 6 | 10 | 16 | 38% | -1.88 | 1.28 | 7 | 6 ❌ |
| ANCHOR_8 | D- | 3 | 14 | 17 | 18% | -4.05 | 1.67 | 8 | 9 ❌ |
| ANCHOR_11 | E+ | 4 | 12 | 16 | 25% | -3.24 | 1.49 | 9 | 8 ❌ |
| ANCHOR_7 | E- | 0 | 17 | 17 | 0% | -7.99 | 2.00 | 10 | 12 ❌ |
| ANCHOR_4 | F+ | 2 | 15 | 17 | 12% | -5.04 | 1.90 | 11 | 10 |
| ANCHOR_1 | F+ | 1 | 16 | 17 | 6% | -6.31 | 2.00 | 12 | 11 |

#### Inverted Anchor Head-to-Head Comparisons

| Essay A | Grade A | Essay B | Grade B | Winner | Confidence | LLM Justification |
|---------|---------|---------|---------|--------|------------|-------------------|
| ANCHOR_10 | A | ANCHOR_2 | B | B ❌ | 3.5 | "Essay B better addresses assignment scope with diverse examples and deeper exploration of role model influence" |
| ANCHOR_10 | A | ANCHOR_5 | B | B ❌ | 4.0 | "B better addresses prompt requirements, has stronger structure and fewer errors despite minor issues" |
| ANCHOR_11 | E+ | ANCHOR_8 | D- | E+ ❌ | 3.5 | "Essay A better addresses assignment requirements with clearer structure, deeper analysis of role model influence, and more coherent argumentation despite language errors" |
| ANCHOR_7 | E- | ANCHOR_1 | F+ | F+ ❌ | 3.5 | "Better structure, addresses more rubric points, discusses role model influence despite language errors" |
| ANCHOR_4 | F+ | ANCHOR_7 | E- | F+ ❌ | 3.5 | "Essay A better addresses assignment requirements: introduces specific role model (Leila), discusses influence on values, explores societal impact. Essay B lacks depth on role model influence and societal contribution" |

#### Unexpected Wins/Losses by Essay

**Unexpected Losses (lost to lower-graded essay):**

| Essay | Grade | Lost To | Opponent Grade | Confidence |
|-------|-------|---------|----------------|------------|
| ANCHOR_10 | A | ANCHOR_2 | B | 3.5 |
| ANCHOR_10 | A | ANCHOR_5 | B | 4.0 |
| ANCHOR_3 | C- | ANCHOR_9 | D+ | (transitive) |
| ANCHOR_8 | D- | ANCHOR_11 | E+ | 3.5 |
| ANCHOR_7 | E- | ANCHOR_1 | F+ | 3.5 |
| ANCHOR_7 | E- | ANCHOR_4 | F+ | 3.5 |

**Correct Head-to-Head (ANCHOR_3 vs ANCHOR_9):**
- ANCHOR_3 (C-) beat ANCHOR_9 (D+) with confidence 3.0 ✓
- But C- still ranked below D+ due to transitive effects from other comparisons

#### Statistical Summary

- **Total inversions:** 5 direct head-to-head errors
- **Worst performer:** ANCHOR_7 (E-) - 0 wins in 17 comparisons
- **Region affected:** C-/D/E/F range (lower grades)
- **Region unaffected:** A/B range (upper grades) - calibration correct

## Findings Summary

| Metric | Value | Status |
|--------|-------|--------|
| Batch Status | COMPLETE_STABLE | Pass |
| Failed comparisons | 0 | Pass |
| Mean SE | 1.177 | Healthy (<1.5) |
| Isolated items | 0 | Pass |
| Items at SE cap | 2 | Warning |
| Min comparisons/item | 16 | Pass |
| Student with SE=0 | TUVA_KARLSSON | Bug |
| Anchor inversions | 3 | Quality issue |

## Plan

### Phase 0: Documentation (Complete)
- [x] Update task document with findings
- [x] Create diagnostic report with all raw data

### Phase 1: Fix SE=0 Bug (Complete)
- [x] Add `is_anchor: bool` to `EssayForComparison` model (`models_api.py:34`)
- [x] Modify `bt_inference.py` to prefer anchors as reference (lines 26, 60-67)
- [x] Update `scoring_ranking.py` to pass anchor indices (lines 105-106, 148-150)
- [x] Update all callers to populate `is_anchor` (5 files)
- [x] Add unit tests: `tests/unit/test_bt_se_computation.py` (10 tests, all pass)

### Phase 2: Anchor Inversion Root Cause (Complete)
- [x] Analyze win/loss rates for all anchors
- [x] Review head-to-head comparison results
- [x] Read essay content for anomalous anchors (E-, C-, E+, F+)
- [x] Identify root cause: LLM-expert judgment misalignment in C-/D/E/F range
- [x] Document findings in task and plan files

### Phase 3: Anchor Inversion Detection (Pending)
- [ ] Implement anchor monotonicity check in grade projection
- [ ] Add `anchor_inversions` count to `bt_se_summary`
- [ ] Log warnings when inversions detected

### Phase 4: Rubric Enhancement (Future Work)
- [ ] Add grade-level descriptors to rubric, especially for E/F boundary
- [ ] Consider hybrid human-LLM approach for lower grades
- [ ] Evaluate domain-specific LLM fine-tuning

## Success Criteria

1. No student essay ever has SE = 0 (reference is always an anchor)
2. Anchor inversions detected and logged in `bt_se_summary`
3. All existing tests pass
4. New unit tests for reference selection logic

## Related

- Diagnostic report: `.claude/work/reports/2025-11-29-bt-se-anchor-inversion-analysis.md`
- BT inference code: `services/cj_assessment_service/cj_core_logic/bt_inference.py`
- Scoring ranking: `services/cj_assessment_service/cj_core_logic/scoring_ranking.py`
- SE unit tests: `services/cj_assessment_service/tests/unit/test_bt_se_computation.py`

## Notes

- Database batch `364d4746-b34e-4038-b825-0f6f9d7e2251` contains pre-fix data (TUVA_KARLSSON still shows SE=0)
- Fix verified via 10 unit tests covering reference selection behavior
- Next batch run will use anchor as reference, preventing SE=0 on students

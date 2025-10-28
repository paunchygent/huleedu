# Research Task: Optimal Pairing Distribution for CJ Assessment with Anchor Essays

## Your Mission

Research and recommend the optimal distribution of pairwise comparisons for a Comparative Judgement (CJ) assessment session that integrates pre-graded anchor essays with previously assessed student essays. Provide evidence-based recommendations grounded in CJ assessment literature and statistical principles.

---

## Context: The Assessment Problem

### What We Have Done (Session 1)
- **12 student essays** were assessed using Comparative Judgement
- **14 teacher raters** completed pairwise comparisons
- **58 total teacher ratings with absolute grades (e.g., D+, C-, E+ and so on)** were collected
- Bayesian Bradley-Terry model produced posterior ability estimates for each essay
- Result: Relative ordering established, but NO connection to absolute grade scale

### What We Need to Do (Session 2)
- Add **12 anchor essays** with official grades (F+1, F+2, E-, E+, D-, D+, C-, C+, B, B, A1, A2)
- Conduct a Comparative Judgement session with **84 total comparisons** (14 raters × 6 comparisons each)
- Connect student essays to anchor grade scale via pairwise comparisons
- Use comparative judgements (NOT absolute grades) to establish the bridging

### Current Constraints
- **24 essays total** in pool (12 student + 12 anchors)
- **84 minimum comparison budget** (fixed by rater availability)
- **Combined dataset**: Will merge Session 2 (84 pairs) with Session 1 (58 absolute assessments)
- **Single session format**: All 84 comparisons collected Wednesday, no ensured adaptive rounds, but it is not impossible either. 

---

## Current Session 1 Results

### Student Essay Posterior Estimates (from Bayesian Model)

| Essay ID | Current Grade | Ability Score | Confidence | Sample Size |
|----------|---------------|---------------|------------|-------------|
| JA24     | B             | 8.50          | 0.39       | 6           |
| II24     | B             | 7.83          | 0.37       | 5           |
| ES24     | C+            | 7.43          | 0.31       | 6           |
| EK24     | C+            | 6.70          | 0.25       | 4           |
| ER24     | C-            | 6.04          | 0.38       | 4           |
| TK24     | C-            | 5.85          | 0.36       | 5           |
| SN24     | C-            | 5.52          | 0.30       | 4           |
| HJ17     | D+            | 5.38          | 0.30       | 5           |
| SA24     | D+            | 4.72          | 0.38       | 4           |
| LW24     | D+            | 4.65          | 0.23       | 8           |
| JF24     | D+            | 4.61          | 0.29       | 5           |
| JP24     | E+            | 3.43          | 0.12       | 4           |

**Key Observations:**
- Grade clustering: 4 essays at D+, 3 essays at C-
- High uncertainty essays (confidence <0.30): JP24, LW24, EK24, JF24, SN24, HJ17
- Moderate uncertainty: ES24, ER24, TK24
- Relatively stable: JA24, II24, SA24 (but still only 0.37-0.39 confidence)
- Sparse coverage: Most essays have only 4-6 comparisons from Session 1

### Grade Scale Mapping (Swedish System)
```
Numeric Index | Grade | Expected Ability Range
0             | F     | ~0.0
1             | F+    | ~1.0
2             | E-    | ~2.0
3             | E+    | ~3.0
4             | D-    | ~4.0
5             | D+    | ~5.0
6             | C-    | ~6.0
7             | C+    | ~7.0
8             | B     | ~8.0
9             | A     | ~9.0
```

---

## Goal and Desired Outcome

### Primary Goal
**Establish reliable connections between student essay abilities and the official grade scale** through comparative judgements, enabling the Bayesian model to:
1. Translate student posterior estimates onto the absolute grade scale
2. Reduce uncertainty (increase confidence) for all student essays
3. Resolve grade boundaries for clustered essays (D+ and C- groups)
4. Provide defensible, evidence-based final grades

### Success Metrics
- **Confidence improvement**: Target >0.50 confidence for all essays (vs. current 0.12-0.39)
- **Graph connectivity**: Every student has multiple independent comparison paths to anchors
- **Grade resolution**: Distinguish essays within clusters (e.g., can we order the 4 D+ essays?)
- **Scale anchoring**: Posterior grade assignments align with where essays naturally fall on F+ to A scale
- **Model stability**: Combined 142-comparison dataset produces convergent Bayesian posteriors

### Secondary Goals
- Validate anchor consistency: Verify anchor-anchor comparisons align with official grade ordering
- Identify problematic essays: Flag any student essays that don't fit cleanly into the grade structure
- Rater efficiency: Maximize information gain per comparison (high-value pairs)

---

## Problems and Lessons Learned

### Issue 1: Bayesian Model Has Known Bugs ⚠️
**Problem**: The current Bayesian model (OrderedLogistic likelihood) produces incorrect consensus grades when ratings are mixed. Example: Essay ES24 received C+(×3), B(×1), A(×1), C-(×1) but model output C- with 81% confidence instead of expected C+.

**Impact on Session 2**:
- Session 1 posteriors may not be fully trustworthy as priors
- We're using relative ability rankings (which are more stable) rather than absolute grade assignments
- Session 2 design should be robust even if Session 1 estimates are somewhat noisy

**Mitigation**: 
- Focus on relative ordering, not precise ability values
- Ensure sufficient anchor connections to override any Session 1 errors
- Consider Session 2 as partially corrective

### Issue 2: Sparse Coverage in Session 1
**Problem**: Most essays received only 4-6 comparisons, resulting in low confidence (0.12-0.39).

**Impact**: 
- Wide posterior distributions
- Grade assignments near boundaries are uncertain
- Some essays may not have been compared to each other at all

**Lesson**: Session 2 must balance:
- Adding NEW information (student-anchor comparisons)
- Reinforcing EXISTING information (more student-student comparisons to tighten ordering)

### Issue 3: Grade Clustering
**Problem**: 4 essays clustered at D+ (ability 4.61-5.38), 3 essays at C- (ability 5.52-6.04).

**Questions**:
- Are these truly "ties" that should receive the same grade?
- Or is the clustering an artifact of insufficient comparisons in Session 1?
- Do we need more within-cluster comparisons to resolve local ordering?

**Implication**: Session 2 should include targeted student-student pairs within clusters, not just student-anchor bridging.

### Issue 4: Anchor Integration Strategy Uncertain
**Problem**: Initial session design was over-engineered with unclear theoretical justification.

**Distribution attempted**:
- 71% student-anchor pairs (60/84)
- 15% student-student pairs (13/84)
- 14% anchor-anchor pairs (11/84)

**Questions raised**:
- Should anchors be treated as "just more essays" and positioned naturally?
- How many anchor-anchor comparisons are actually needed? (We already know their grades)
- Is the 3:1 ratio of student-anchor to student-student optimal?
- Should distribution be adaptive based on uncertainty (prioritize low-confidence essays)?

---

## Your Research Task

### Primary Question
**What is the optimal distribution of comparison types (student-anchor, student-student, anchor-anchor) in an 84-comparison CJ session to bridge 12 previously-assessed student essays to 11 pre-graded anchor essays?**

### Specific Sub-Questions

1. **Anchor-Anchor Comparisons**:
   - How many anchor-anchor pairs are needed to validate scale consistency?
   - Are they necessary at all if anchor grades are known and trusted?
   - Literature on "parameter anchors" vs. "reference standards" in CJ?

2. **Student-Anchor Comparisons**:
   - What minimum coverage ensures every student connects to the anchor scale?
   - Should high-uncertainty students get MORE anchor comparisons?
   - Best practice: bracket students with anchors above/below, or use nearest anchor?
   - Literature on "bridging" or "linking" in IRT/Rasch models?

3. **Student-Student Comparisons**:
   - When prior session data exists, how much should we reinforce vs. expand?
   - Is it valuable to repeat critical comparisons from Session 1 for reliability?
   - Literature on "within-set" vs. "cross-set" comparisons in adaptive CJ?

4. **Uncertainty-Driven Allocation**:
   - Should low-confidence essays (JP24: 0.12, LW24: 0.23, EK24: 0.25) receive disproportionate attention?
   - How to balance Fisher information gain across the pool?
   - Literature on adaptive pair generation in CJ (e.g., D-optimality criteria)?

5. **Graph Connectivity**:
   - What minimum connectivity ensures stable posterior estimation?
   - Can we formalize "multiple independent paths" requirement?
   - Literature on comparison graph topology in CJ/Bradley-Terry models?

6. **Combined Dataset Strategy**:
   - When merging Session 1 (58 student-student) + Session 2 (84 mixed) data:
     - Does prior student-student data reduce need for new student-student pairs?
     - Can Session 2 focus primarily on student-anchor bridging?
     - Or does sparse Session 1 coverage require reinforcement?

### Research Sources to Consult

**Comparative Judgement Literature**:
- Pollitt (2012) - CJ assessment methodology
- Bramley (2007, 2015) - Rank-ordering and paired comparisons
- Bartholomew & Bramley (2015) - Adaptive CJ algorithms
- Jones & Alcock (2014) - CJ in educational assessment
- Steedle & Ferrara (2016) - Standard setting with CJ

**Psychometric Foundations**:
- Bradley-Terry model literature on graph connectivity
- IRT/Rasch linking studies (common-item design, anchor test forms)
- D-optimal design for paired comparison experiments
- Fisher information and optimal allocation in ordinal models

**Practical Implementations**:
- No More Marking platform documentation (if available)
- CompaRater or similar CJ software whitepapers
- Published case studies of CJ with anchor/reference essays

---

## Deliverables Requested

### 1. Evidence-Based Recommendation
Provide a specific distribution (with rationale):
```
Recommended Distribution for 84 Comparisons:
- Student-Anchor: X pairs (Y%)
- Student-Student: X pairs (Y%)
- Anchor-Anchor: X pairs (Y%)
Total: 84 pairs (100%)
```

### 2. Allocation Strategy
- How should the X student-anchor pairs be distributed across 12 students?
  - Equal coverage (7 per student)?
  - Weighted by uncertainty (more for low-confidence essays)?
  - Adaptive bracketing (based on current ability estimates)?

- Which student-student pairs should be prioritized?
  - Cluster resolution (within D+/C- groups)?
  - Boundary pairs (between adjacent grades)?
  - Replication (repeating Session 1 critical pairs)?

- Which anchor-anchor pairs are essential?
  - Only adjacent grades (C- vs C+, D+ vs C-)?
  - Full spanning tree across all anchors?
  - Minimal validation set?

### 3. Theoretical Justification
- Cite specific literature supporting the recommended distribution
- Explain the statistical/psychometric principles at play
- Address trade-offs between competing objectives

### 4. Alternative Scenarios
If research reveals multiple viable approaches, present 2-3 options with pros/cons:
- Conservative approach (heavy anchor coverage)
- Efficient approach (minimal anchoring, maximize student refinement)
- Hybrid approach (balanced)

### 5. Implementation Notes
- Any specific pairing patterns to avoid (e.g., transitivity violations)
- Recommendations for rater assignment (does it matter which raters see which types?)
- Stopping criteria or quality checks to validate the approach post-session

---

## Constraints and Practical Considerations

### Hard Constraints
- Exactly 84 comparisons (cannot change)
- 14 raters × 6 comparisons each
- Single session (no adaptive rounds)
- Manual administration (no algorithmic real-time pair generation)

### Soft Constraints
- Minimize rater fatigue (mix easy/hard comparisons per rater)
- Ensure every rater sees mix of comparison types (for calibration)
- Prefer simpler patterns for manual administration

### Data Integration Note
- Session 1 data (58 comparisons) will be merged with Session 2 (84 comparisons)
- Combined graph will have 142 edges
- Node count: 23 essays total (12 student + 11 anchor)
- Existing Session 1 edges are all student-student (no anchors involved yet)

---

## Context Files Available

If you need additional context, these files are available:
- `scripts/bayesian_consensus_model/session_2_planning/20251027-143747/essay_consensus.csv` - Session 1 Bayesian output
- `scripts/bayesian_consensus_model/anchor_essay_input_data/eng_5_np_16_bayesian_assessment_v2.csv` - Session 1 raw ratings
- `scripts/bayesian_consensus_model/SESSION_2_PAIRING_PLAN.md` - Initial (possibly flawed) session design

---

## Success Criteria for Your Response

A successful research response will:

1. **Ground recommendations in literature**: Cite at least 3-5 relevant sources
2. **Provide specific numbers**: Not "some anchor-anchor pairs" but "8 anchor-anchor pairs (9.5%)"
3. **Explain trade-offs**: Why this distribution over alternatives
4. **Address uncertainty**: If research is inconclusive, explain what's known vs. unknown
5. **Be actionable**: I should be able to directly implement the recommended distribution
6. **Validate assumptions**: Question or confirm assumptions I've made (e.g., "treating anchors as known" vs. "estimating anchor positions")

---

## Final Note

This is a real assessment session happening Wednesday. The research will directly inform how 12 student essays receive their final grades. Prioritize practical, evidence-based recommendations over theoretical perfection. If CJ literature is sparse on this exact scenario, draw on analogous methods (IRT linking, standard setting, etc.) and explain the connection.

Thank you for your thorough research!
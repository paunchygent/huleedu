# TASK: Mathematical Quality Review & Validation of CJ Assessment Confidence Calculations

**Status**: Not Started
**Priority**: High
**Type**: Research + Mathematical Validation
**Estimated Effort**: 11-16 hours
**Created**: 2025-01-03

---

## Progress Log

### 2025-11-03 – Phase 1 (Scope Review & Context Gathering)
- Read core CJ service modules (`confidence_calculator`, `bt_inference`, `scoring_ranking`, `grade_projector`) and service README to document current heuristics, boundary handling, and SE computation patterns.
- Reviewed Bayesian consensus documentation (`README`, `ordinal_kernel.py`) plus pairing utilities to understand current human CJ workflow and to ensure we avoid adaptive pairing for this validation.
- Located available empirical artifacts (Session 1 summary, session 2 planning CSVs, anchor rating CSV) and confirmed existing integration tests covering BT scoring/stability.
- Noted key heuristic assumptions requiring validation: logistic comparison-count curve (50% @5, 90% @15), fixed weight mix (0.35/0.20/0.35/0.10), boundary distance cap at 0.15, anchor bonus of 0.15, and comparison estimate heuristic `k * n * log n`.
- Outstanding needs: confirm availability of raw Session 1 comparison logs (pair-level data) for bootstrap SE analysis and clarify preferred repository location for newly created assessment scripts/tests.

### 2025-11-03 – Phase 2 (Theoretical Validation Framework Draft)
- Derived analytical Fisher Information for Bradley–Terry abilities under random non-adaptive pairing: per-item information accumulates as `∑_j p_ij (1 - p_ij)`; with balanced abilities (p≈0.5) each comparison contributes ≈0.25, giving `SE_i ≈ 2 / √n_i` where `n_i` counts distinct comparisons touching essay *i*.
- Established that the current logistic mapping in `confidence_calculator` implicitly assumes SE scaling proportional to comparison count but overstates confidence: matching `SE=2/√n` to 50% confidence at 5 comparisons implies `SE≈0.89`, far looser than grade-boundary tolerances, and 90% at 15 comparisons (`SE≈0.52`) still exceeds the 0.15 boundary distance heuristic.
- Defined a confidence calibration pathway: compute SE from Fisher Information (or a bootstrap equivalent), translate to probability of crossing nearest grade boundary via normal/logistic tail (`confidence = 1 - 2·Φ(-|Δ|/SE)`), and combine with weightings only after grounding each factor in statistical evidence.
- Identified literature alignment tasks: collect references on CJ design variance (Pollitt 2012; Bramley & Johnson, 2012) and Bayesian SE approximations for pairwise comparisons to justify the `n·log n` heuristic or replace it with information-based targets.

### 2025-11-03 – Phase 3 (Assessment Tooling & Initial Analysis)
- Created `.claude/research/scripts/cj_confidence_analysis.py`, reproducing production heuristics alongside Fisher-based SE estimates, the grade-boundary stay probability model, and JSON table generation for downstream plotting.
- Added complementary unit tests `.claude/research/scripts/test_cj_confidence_analysis.py` covering logistic monotonicity, SE scaling, boundary confidence trends, and serialization; tests pass via `pdm run pytest-root .claude/research/scripts/test_cj_confidence_analysis.py`.
- Generated baseline summary output (`.claude/research/scripts/cj_confidence_summary.json`) spanning 1–30 comparisons and boundary distances of 0.05–0.20, highlighting that the heuristic logistic reaches the “HIGH” label while boundary-stay probabilities remain below 70% for the 0.15 threshold.
- Confirmed future empirical calibration should rely on grade boundaries derived by `GradeProjector`, aligning the probability calculations with the service’s existing calibration step.

### 2025-11-03 – Phase 4 (Synthesis & Next Steps)
- Summarized findings and outstanding tasks in `.claude/HANDOFF.md`, capturing Phase 1–3 outputs, tooling locations, and follow-up actions for literature review, simulation, and integration planning.
- Identified immediate Phase 4+ priorities: (1) gather comparative judgement confidence literature/framework references, (2) extract GradeProjector-derived boundaries for simulations, (3) evaluate justification for factor weights and anchor bonus, and (4) outline integration of SE-based confidence into both LLM and human CJ pipelines.
- No production code changes were made; all artefacts remain under `.claude/research/`.

### 2025-11-03 – Literature Survey Kickoff
- Queried Crossref for seminal CJ confidence sources: Pollitt (2012), Bramley & Vitello (2019), Verhavert et al. (2019), Bartholomew & Jones (2022), and Wheadon & Jones (2020), capturing DOIs and abstracts for reference.
- Created `.claude/research/CJ-CONFIDENCE-VALIDATION.md` with a literature matrix summarising each source’s key findings and their relevance to confidence validation, plus a to-do list for deeper extraction (SE formulas, tool heuristics, factor weighting evidence).
- Remaining literature actions: pull full texts (where accessible), document published heuristics from ACJ platforms, and map evidence for/against current weightings and anchor bonus assumptions.
- **New TODOs**:
  - Extract explicit SE / reliability expressions and recommended thresholds from each cited source.
  - Catalogue any tool-specific heuristics (No More Marking, Comproved, etc.) referenced in the literature.
  - Crosswalk reported reliability targets (e.g., SSR ≥ 0.75) with current confidence thresholds for later calibration.

### 2025-11-07 – Phase 1 Extension (Expanded Literature Integration)
- Reviewed the additional research artefacts in `.claude/research/` (Kinnear et al. 2025, Bartholomew & Jones 2021, Verhavert et al. 2022, van Daal et al. 2022) to solidify SSR/SE benchmarks and adaptivity considerations.
- Updated `.claude/research/CJ-CONFIDENCE-VALIDATION.md` with the new findings, added action items for the framework comparison matrix, and confirmed that the literature requirements for Phase 2 are satisfied.
- Ready to proceed into Phase 2 (Mathematical Validation) with sufficient theoretical and practitioner evidence gathered.

### 2025-11-07 – Phase 2 (Theoretical Validation Progress)
- Added the full Fisher-information derivation and boundary-stay probability mapping to `.claude/research/CJ-CONFIDENCE-VALIDATION.md`, providing closed-form targets for SE vs. comparison count and confidence.
- Audited `compute_bt_standard_errors()` with synthetic random-pair datasets (via `pdm run python`), confirming monotonic SE shrinkage while documenting the observed ~20–30 % inflation relative to the naive \(2/\sqrt{n}\) rule due to pairing imbalance and reference constraints.
- Captured the planned sensitivity-analysis methodology (correlation/regression/ablation) to reassess factor weights once empirical CJ batches are available in Phase 3.

---

## Context & Motivation

The CJ Assessment Service (`services/cj_assessment_service/`) currently uses a confidence calculator (`cj_core_logic/confidence_calculator.py`) with **hardcoded thresholds** that appear to be assumptions rather than validated statistical calculations:

- Sigmoid curve: `1/(1 + exp(-(n-5)/3))` → "5 comparisons = 50%, 15 = 90%"
- Factor weights: 35% (comparisons), 20% (distribution), 35% (boundaries), 10% (anchors)
- Thresholds: 0.3 std, 0.15 boundary distance

**Problem**: These numbers lack mathematical or empirical justification. We need to validate or replace them with **statistically rigorous, evidence-based calculations**.

**Why This Matters**:
1. We're building a TUI for human CJ assessment based on these calculations
2. Confidence scores determine when essays are ready to become anchors
3. The Bayesian consensus model relies on these confidence metrics
4. Users trust the system to provide accurate quality indicators

---

## Objectives

### Primary Research Questions

1. **Are the thresholds justified?**
   - Where do 5, 15, 0.3, 0.15 come from?
   - Should they be based on Fisher Information / Standard Error instead?

2. **Are the factor weights evidence-based?**
   - Why 35%, 20%, 35%, 10%?
   - Should they be equal or data-driven?

3. **How do CJ frameworks on GitHub handle confidence?**
   - What are industry best practices?
   - Do they use SE, rater agreement, or other metrics?

4. **What does our empirical data show?**
   - Session 1: 58 comparisons, 12 essays → SE 0.12-0.39
   - What's the actual n → SE → confidence relationship?

5. **Should score stability be a factor?**
   - For multi-session assessments, is drift more important than count?

### Deliverables

1. **Mathematical Analysis Report** (`.claude/research/CJ-CONFIDENCE-VALIDATION.md`):
   - Theoretical derivation: Fisher Information → SE → Confidence
   - Validation of current thresholds using real data
   - Comparison to GitHub CJ frameworks
   - Statistical test results

2. **Framework Comparison Matrix** (in report):
   - 3-5 GitHub CJ implementations analyzed
   - How they calculate confidence
   - Thresholds they use
   - Validation approaches

3. **Empirical Validation** (Python scripts in `.claude/research/scripts/`):
   - Bootstrap validation using Session 1/2 data
   - SE vs comparison count analysis
   - Confidence calibration tests

4. **Recommendations**:
   - Keep current or revise (with justification)
   - If revising: New formulas with mathematical proofs
   - Implementation plan

5. **Documentation Updates**:
   - Accurate CJ Assessment process logic description
   - Bayesian inference model documentation
   - README corrections for TUI

---

## Background: CJ Assessment Service Architecture

### Key Components

**Services**:
- **CJ Assessment Service** (`services/cj_assessment_service/`): LLM-based comparative judgment
- **Bayesian Consensus Model** (`scripts/bayesian_consensus_model/`): Human rater consensus grading

**Core Logic**:
- **Bradley-Terry Model** (`cj_core_logic/bt_inference.py`): Score calculation using `choix` library
- **Confidence Calculator** (`cj_core_logic/confidence_calculator.py`): 4-factor confidence scoring
- **Grade Projector** (`cj_core_logic/grade_projector.py`): Maps BT scores to Swedish 8-grade scale

**Data Flow**:
1. Essays compared pairwise (LLM judges or human raters)
2. Bradley-Terry scores computed via `choix.ilsr_pairwise()`
3. Standard errors calculated via Fisher Information Matrix
4. Confidence scores from 4 factors (comparisons, distribution, boundaries, anchors)
5. Grade projections using Bayesian inference with population priors

### Important Distinction

**Two Separate Systems**:

1. **CJ Assessment Service** (LLM judges):
   - Event-driven microservice
   - LLM comparisons via centralized LLM Provider Service
   - Bradley-Terry scoring with `choix`
   - Used for automated essay assessment

2. **Bayesian Consensus Model** (Human judges):
   - Standalone Python scripts
   - Human rater pairwise comparisons
   - D-optimal pair generation
   - Ordinal kernel smoothing + empirical Bayes
   - Used for anchor essay validation

**Both use Bradley-Terry models but in different contexts.** This task focuses on validating the confidence calculations that apply to BOTH systems.

---

## Task Phases

### Phase 1: Code & Literature Review

**1.1 Read Required Files** (CRITICAL - Do this first!)

**Architecture & Rules**:
- `.claude/rules/020.7-cj-assessment-service.mdc` - Service architecture
- `.claude/rules/070-testing-and-quality-assurance.mdc` - Testing standards
- `services/cj_assessment_service/README.md` - Service documentation

**Implementation Files**:
- `services/cj_assessment_service/cj_core_logic/confidence_calculator.py` - Current implementation
- `services/cj_assessment_service/cj_core_logic/bt_inference.py` - Bradley-Terry scoring & SE
- `services/cj_assessment_service/cj_core_logic/grade_projector.py` - Grade mapping
- `services/cj_assessment_service/cj_core_logic/scoring_ranking.py` - Score convergence logic

**Bayesian Model**:
- `scripts/bayesian_consensus_model/models/ordinal_kernel.py` - Kernel smoothing
- `scripts/bayesian_consensus_model/d_optimal_optimizer.py` - Pair generation
- `scripts/bayesian_consensus_model/README.md` - Workflow documentation

**Existing Tests**:
- `services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py`
- `services/cj_assessment_service/tests/integration/test_incremental_scoring_integration.py`

**Session Data** (for empirical validation):
- `.claude/research_prompts/RESEARCH_PROMPT_CJ_ANCHOR_PAIRING.md` - Session 1 results
- Look for CSV files with actual comparison data

**1.2 Review Statistical Theory**

**Required Reading**:
- Bradley-Terry model: Maximum likelihood estimation
- Fisher Information Matrix: Relationship to parameter variance
- Cramér-Rao bound: Variance lower bound = `1/I(θ)`
- Standard Error: `SE = sqrt(diag(FIM^-1))`

**Key Formula to Validate**:
```
SE ∝ 1/sqrt(n_comparisons)
```

If this holds, then:
- 5 comparisons → SE ≈ 0.45
- 15 comparisons → SE ≈ 0.26
- 50 comparisons → SE ≈ 0.14

**Check if the sigmoid curve matches this theoretical relationship.**

**1.3 Search GitHub for CJ Frameworks**

**Search Queries**:
```
"bradley terry" AND "comparative judgment" AND python
"pairwise comparison" AND "confidence" AND educational
"choix" AND assessment
"no more marking" AND algorithm
```

**What to Extract**:
- Repository URLs
- Confidence calculation methods
- Threshold values used
- Validation approaches
- Any references to psychometric literature

**Create comparison table.**

---

### Phase 2: Mathematical Validation

**2.1 Derive Theoretical Confidence Formula**

**Task**: Prove or disprove the current sigmoid curve.

**Steps**:
1. Write down Fisher Information for Bradley-Terry:
   ```
   I(θ) = Σ p_ij(1-p_ij) × (e_i - e_j)(e_i - e_j)^T
   ```
2. For connected graph with n comparisons per item, derive SE
3. Map SE → confidence using a principled approach (e.g., classification error rate)
4. Compare to current sigmoid: `1/(1 + exp(-(n-5)/3))`

**Output**: Mathematical proof or counterexample.

**2.2 Validate Using `choix` Library**

**Task**: Check what `choix` actually provides.

**Steps**:
1. Read `choix` documentation for SE calculation
2. Check if `bt_inference.py` uses it correctly
3. Validate that `compute_bt_standard_errors()` matches theory
4. Run test cases: n=5, 10, 15, 20 → what SE do we get?

**Output**: Empirical SE values for different comparison counts.

**2.3 Analyze Factor Weights**

**Current**: 35% comparisons, 20% distribution, 35% boundaries, 10% anchors

**Task**: Determine if these are justified.

**Approaches**:
1. **Correlation analysis**: Which factors predict grade accuracy?
2. **Sensitivity analysis**: How does confidence change with each factor?
3. **Principal components**: Are factors independent?

**Use Session 1/2 data if available, otherwise simulate.**

**Output**: Recommended weights with statistical justification.

---

### Phase 3: Empirical Validation

**3.1 Analyze Session 1 Data**

**Data**: 12 essays, 58 comparisons → SE 0.12-0.39

**Tasks**:
1. Load actual comparison results (find CSV files)
2. For each essay: count comparisons, measure SE
3. Fit model: `SE ~ f(n_comparisons)`
4. Plot theoretical vs empirical SE curves
5. Check if sigmoid curve aligns with data

**Code**:
```python
import numpy as np
import pandas as pd
from scipy.optimize import curve_fit

# Load Session 1 data
# comparisons = load_session_data()

# Fit SE ~ a/sqrt(n) + b
def se_model(n, a, b):
    return a / np.sqrt(n) + b

# params, _ = curve_fit(se_model, comparison_counts, observed_ses)
# Compare to sigmoid: confidence = 1/(1 + exp(-(n-5)/3))
```

**Output**: Plots + statistical fit quality (R²).

**3.2 Bootstrap Validation**

**Task**: Validate SE calculations via resampling.

**Steps**:
1. For each essay with n comparisons:
   - Resample comparison results 1000x
   - Recalculate BT scores
   - Measure SE empirically
2. Compare empirical SE to analytical SE from `bt_inference.py`
3. Validate confidence thresholds

**Output**: Confidence intervals for SE estimates.

**3.3 Grade Accuracy Validation**

**IF Session 2 data with anchors is available**:

**Task**: Check if HIGH confidence → accurate grades.

**Steps**:
1. For each student essay:
   - Calculate confidence score
   - Project grade
   - Compare to true grade (if known from anchors)
2. Measure: P(correct grade | HIGH confidence)
3. Measure: P(correct grade | LOW confidence)

**Expected**: HIGH confidence should have >80% accuracy.

**Output**: Classification accuracy by confidence level.

---

### Phase 4: Code Implementation & Testing

**4.1 Create Validation Scripts**

**Location**: `.claude/research/scripts/validate_cj_confidence.py`

**Contents**:
```python
"""Validation scripts for CJ confidence calculations."""

def theoretical_se(n_comparisons: int, n_items: int) -> float:
    """Calculate theoretical SE based on Fisher Information."""
    # Implement using Cramér-Rao bound
    pass

def empirical_se_from_bootstrap(comparisons: list, n_bootstrap: int = 1000) -> float:
    """Calculate SE via bootstrap resampling."""
    pass

def validate_sigmoid_curve(comparison_counts: list[int], observed_ses: list[float]):
    """Compare current sigmoid to theoretical/empirical SE."""
    pass

def compare_to_frameworks(frameworks: list[dict]):
    """Compare our approach to GitHub CJ frameworks."""
    pass
```

**Run tests and generate report.**

**4.2 Document Findings**

**Location**: `.claude/research/CJ-CONFIDENCE-VALIDATION.md`

**Structure**:
```markdown
# Mathematical Validation: CJ Confidence Calculations

## Executive Summary
- Current implementation: [Valid / Flawed / Partially correct]
- Key finding: [Main result]
- Recommendation: [Keep / Revise]

## Theoretical Analysis
### Fisher Information Derivation
[LaTeX math]

### Sigmoid Curve Validation
[Proof or counterexample]

## Empirical Validation
### Session 1 Analysis
[Plots, statistical tests]

### Bootstrap Results
[Confidence intervals]

## GitHub Framework Comparison
| Framework | Method | Thresholds | Validation |
|-----------|--------|-----------|-----------|
| ... | ... | ... | ... |

## Recommendations
### Current Implementation
- Strengths: [...]
- Weaknesses: [...]

### Proposed Revisions (if needed)
[New formulas with proofs]

## Implementation Plan
[Migration strategy]
```

---

### Phase 5: Recommendations & Future Work

**5.1 Immediate Recommendations**

Based on validation results:

**If current thresholds are valid**:
- Document mathematical justification
- Add unit tests validating thresholds
- Update README with evidence

**If current thresholds are invalid**:
- Propose corrected formula
- Provide mathematical proof
- Create migration plan
- Estimate impact on existing assessments

**5.2 Future Enhancements**

**Score Stability Factor** (for multi-session):
```python
# Add to confidence calculator
if previous_bt_score is not None:
    drift = abs(current_bt_score - previous_bt_score)
    stability_confidence = max(0, 1 - drift/threshold)
    # Incorporate into weighted average
```

**Rater Agreement Metrics**:
- Inter-rater reliability (for Bayesian model with human raters)
- Transitivity violations (A>B, B>C, C>A)

**Adaptive Confidence**:
- Update confidence as more comparisons arrive
- Stopping criterion: achieve target confidence level

**5.3 Live Testing Plan** (Future Goal)

**Prerequisites**:
- Working CJ Assessment Service API
- Test harness for full HuleEdu pipeline
- Docker services running
- Real anchor essays in database

**Test Scenarios**:
1. Upload anchor essays via API
2. Submit comparison requests
3. Collect real BT scores and SEs
4. Validate confidence calculations in production
5. A/B test old vs new formulas

**Implementation**: After initial validation is complete.

---

## Key Constraints & Requirements

### MUST DO Before Starting

1. **Read all required files** listed in Phase 1.1
2. **Understand the distinction** between CJ Assessment Service (LLM) and Bayesian Consensus Model (human)
3. **Review existing tests** to understand current validation approach
4. **Search GitHub** for at least 3 reference implementations

### Testing Standards

From `.claude/rules/070-testing-and-quality-assurance.mdc`:
- All validation scripts must have unit tests
- Statistical tests must report p-values and effect sizes
- Plots must include error bars / confidence intervals
- Code must follow project Python standards (Ruff, MyPy)

### Documentation Standards

From `.claude/rules/090-documentation-standards.mdc`:
- All formulas must have mathematical justification
- All thresholds must have empirical or theoretical evidence
- All claims must be falsifiable (provide test cases)
- Use LaTeX for mathematical notation

### Code Quality

- **No handrolled numbers** without proof
- **No assumptions** without validation
- **Every threshold** must be justified
- **Every weight** must be evidence-based

---

## Integration with Bayesian Consensus Model

### Current State

**Bayesian Model** (`scripts/bayesian_consensus_model/`):
- Uses ordinal kernel smoothing
- Empirical Bayes shrinkage for sparse data
- Population priors for Swedish grading scale
- **Does NOT currently use CJ-style confidence from comparisons**

### Priors from Low-Confidence Session

**Problem**: We have Session 1 data with low confidence (SE 0.12-0.39).

**Question**: How to incorporate this into Bayesian priors for human CJ assessment?

**Options**:
1. **Use BT scores as informative priors**:
   - Prior mean = Session 1 BT score
   - Prior variance = f(SE) - higher SE → higher variance
2. **Treat as weak priors**:
   - Downweight Session 1 data due to low confidence
   - Let human comparisons dominate
3. **Hierarchical model**:
   - Meta-prior from LLM assessments
   - Updated with human judgments

**This task should propose a framework** for integrating low-confidence CJ priors into the Bayesian model.

---

## Deliverables Checklist

- [ ] Mathematical analysis report (`.claude/research/CJ-CONFIDENCE-VALIDATION.md`)
- [ ] Framework comparison matrix (3-5 GitHub implementations)
- [ ] Empirical validation scripts (`.claude/research/scripts/`)
- [ ] Statistical test results (plots, p-values, effect sizes)
- [ ] Recommendations: Keep or revise (with justification)
- [ ] If revising: New formulas with proofs
- [ ] Documentation: CJ Assessment process logic
- [ ] Documentation: Bayesian inference model description
- [ ] Proposal: Incorporating CJ priors into Bayesian framework
- [ ] Unit tests for validation scripts
- [ ] README updates for TUI (accurate thresholds)

---

## Success Criteria

✅ **Every threshold has mathematical or empirical justification**
✅ **Comparison to at least 3 GitHub CJ frameworks**
✅ **Validation using actual Session 1/2 data (if available)**
✅ **Clear recommendation: Keep current or revise**
✅ **If revising: Concrete formulas with mathematical proofs**
✅ **Falsifiable claims: Provide test cases that could disprove findings**
✅ **No handrolled numbers without evidence**

---

## Files to Create/Update

### New Files

- `.claude/research/CJ-CONFIDENCE-VALIDATION.md` - Main report
- `.claude/research/scripts/validate_cj_confidence.py` - Validation code
- `.claude/research/scripts/test_confidence_validation.py` - Unit tests
- `.claude/research/data/` - Plots and empirical results

### Files to Update (After Validation)

**If current implementation is flawed**:
- `services/cj_assessment_service/cj_core_logic/confidence_calculator.py` - Corrected formulas
- `services/cj_assessment_service/tests/unit/test_confidence_calculator.py` - New tests
- `services/cj_assessment_service/README.md` - Document validation

**Documentation**:
- `scripts/bayesian_consensus_model/TUI_README.md` - Accurate threshold guidance
- `.claude/rules/020.7-cj-assessment-service.mdc` - Update with validation results

---

## Notes & Warnings

### What This Task Is NOT

- **NOT a standard code review** - This is mathematical quality review
- **NOT about code style** - Focus is on statistical validity
- **NOT about implementation details** - Focus is on theoretical correctness

### What This Task IS

- **Rigorous statistical validation** of confidence calculations
- **Evidence-based analysis** using theory + empirical data
- **Comparison to industry best practices** from GitHub
- **Falsifiable recommendations** with clear test cases

### Important Considerations

1. **LLM vs Human CJ**:
   - CJ Assessment Service uses LLM judges
   - Bayesian model uses human raters
   - Principles are the same (Bradley-Terry)
   - But error distributions may differ

2. **Multi-Session Context**:
   - Score stability may be more important than comparison count
   - Need framework for incorporating priors across sessions

3. **Practical Constraints**:
   - Can't run live tests without API setup
   - Must rely on existing Session 1/2 data
   - Future: Plan for live validation

---

## Timeline Estimate

- **Phase 1** (Literature review): 2-3 hours
- **Phase 2** (Mathematical validation): 3-4 hours
- **Phase 3** (Empirical validation): 3-4 hours
- **Phase 4** (Code + documentation): 2-3 hours
- **Phase 5** (Recommendations): 1-2 hours

**Total**: 11-16 hours

---

## Contact & Questions

If clarification needed:
- Review `.claude/HANDOFF.md` for project context
- Check `.claude/README_FIRST.md` for critical issues
- Consult `.claude/rules/` for coding standards

---

**CRITICAL**: This task requires MATHEMATICAL RIGOR. Every number must be justified. No assumptions without proof. Show your work with LaTeX math and runnable Python code.

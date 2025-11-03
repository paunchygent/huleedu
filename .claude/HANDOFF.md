# Handoff: Mathematical Validation of CJ Confidence Calculations

**Date**: 2025-11-03
**From**: Codex (CJ Confidence Validation Session)
**To**: Next Assistant / Maintainer
**Task**: `TASKS/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`

---

## Session Summary (2025-11-03) - Phase 3.1 Partial Completion

**Status**: Phase 3.1 (Grade Scale Registry + Migrations) is 40% complete (4 of 10 steps)

### Completed Components:

1. ✅ **Grade Scale Registry** (`libs/common_core/src/common_core/grade_scales.py` - 260 LoC):
   - `GradeScaleMetadata` dataclass with comprehensive validation
   - Three scales implemented: `swedish_8_anchor`, `eng5_np_legacy_9_step`, `eng5_np_national_9_step`
   - Helper functions: `get_scale()`, `validate_grade_for_scale()`, `list_available_scales()`, `get_grade_index()`, `get_uniform_priors()`
   - Exported from `common_core.__init__`

2. ✅ **Unit Tests** (`libs/common_core/tests/test_grade_scales.py` - 365 LoC):
   - 59 behavioral tests (all passing)
   - Comprehensive coverage: scale validation, error cases, edge cases
   - Parametrized tests for all three scales

3. ✅ **Database Migration** (revision: `bf559b4a86bf`):
   - Added `grade_scale` column to `anchor_essay_references` and `grade_projections`
   - Type: `String(50)`, default: `swedish_8_anchor`, indexed
   - Migration applied and verified via psql
   - File: `services/cj_assessment_service/alembic/versions/20251103_2222_bf559b4a86bf_add_grade_scale_columns.py`

4. ✅ **ORM Models Updated** (`services/cj_assessment_service/models_db.py`):
   - `AnchorEssayReference.grade_scale` field added
   - `GradeProjection.grade_scale` field added
   - Type checking passes (pdm run typecheck-all: Success)

### Remaining Work (Steps 5-10):

5. **Pydantic API Models**: Create `RegisterAnchorRequest` with scale validation
6. **API Endpoint**: Update anchor registration to accept grade_scale parameter
7. **Repository Layer**: Add scale-aware anchor queries
8. **GradeProjector**: Refactor to load scales dynamically from registry
9. **ContextBuilder**: Thread grade_scale parameter through workflow
10. **Tests & Documentation**: Update fixtures, create ENG5 NP tests, document changes

### Configuration Decisions (User-Confirmed):
- ENG5 NP Legacy: `F+, E-, E+, D-, D+, C-, C+, B, A` (below F+ → F, uniform priors 1/9)
- ENG5 NP National: `1-9` (below 1 → 0, uniform priors 1/9)
- CLI tooling deferred to Phase 3.2
- Backward compatibility: Swedish 8-anchor remains default
- Assignment metadata (instructions table) is the source of truth for `grade_scale`; anchor registration and grade projection must resolve scale via `assignment_id` rather than trusting client input.

### Quality Gates Met:
- All tests passing (59 new + existing)
- Type checking clean (1171 files)
- Migration applied successfully
- Files under 500 LoC limit
- Database schema verified

### Next Session Tasks:
1. Complete remaining Phase 3.1 steps (5-10)
2. Run integration tests with ENG5 NP scales
3. Update service README with grade scale documentation
4. Plan Phase 3.2 (CLI + enhanced integration)

---

## Session Summary (2025-11-07) - Phase 2 Theoretical Validation

- Phase 1 research inputs are complete: core service files reviewed, initial analytical tooling created, and the expanded literature set (Pollitt 2012 through Kinnear et al. 2025) summarised in `.claude/research/CJ-CONFIDENCE-VALIDATION.md`.
- Phase 2 theoretical work captured in the same notebook: Fisher-information derivation, SE → boundary probability mapping, audit notes for `compute_bt_standard_errors`, and the planned factor-weight sensitivity analysis.
- Baseline analysis scripts (`cj_confidence_analysis.py`, `test_cj_confidence_analysis.py`) reproduce production heuristics and generate comparison tables for theoretical benchmarking.
- Existing empirical logs are single-essay rating records (58 assessments for 12 essays) – **no pairwise CJ comparisons currently exist**, so fresh CJ batches must be executed via the CJ Assessment Service to collect comparison data for validation.
- Phase 3 implementation plan recorded in `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`, outlining grade-scale registry work, service integration, and ENG5 NP batch tooling per rule 110.7.
- Grade-scale implementation will introduce `eng5_np_legacy_9_step` (grade codes `F+, E-, E+, D-, D+, C-, C+, B, A`; anchor IDs such as `F+1`, `F+2` map to the same `F+` code, essays below `F+` treated as `F`) and `eng5_np_national_9_step` (ordered `1`–`9`); SV3’s multi-aspect scale is deferred. Legacy anchors remain on the current Swedish 8-grade default until migration.
- ENG5 NP 2016 artefacts: student essays (`test_uploads/ANCHOR ESSAYS/ROLE_MODELS_ENG5_NP_2016/anchor_essays/`), anchors from `scripts/bayesian_consensus_model/d_optimal_workflow/models.py::DEFAULT_ANCHOR_ORDER`, exam instructions (`.../eng5_np_vt_2017_essay_instruction.md`), LLM comparison prompt (`.../llm_prompt_cj_assessment_eng5.md`).
- Phase 3 data capture will persist machine-readable JSON bundles under `.claude/research/data/eng5_np_2016/` (metadata, essay registry, comparisons, BT stats, grade projections) to avoid repeated LLM runs.
- Progress and research notebooks have been refreshed with the new findings; ready to proceed into grade-scale implementation and data generation.

Outstanding next steps:
1. Execute Phase 3.1 (grade-scale registry + migrations) per `TASKS/TASK-CJ-CONFIDENCE-PHASE3-GRADE-SCALE-DATA-PIPELINE.md`.
2. Update CJ anchor API, GradeProjector, and helper CLI for scale awareness (Phase 3.2).
3. Build/run the ENG5 NP ingestion CLI, capture outputs using the agreed JSON schema (Phase 3.3), then move to confidence recalibration/testing (Phase 4).

---

## Why You're Doing This Task

### The Problem

During a code quality review of the CJ Pair Generator TUI application, the user challenged me on **hardcoded numerical thresholds** in the confidence calculator that appear to be **assumptions rather than validated calculations**:

```python
# From services/cj_assessment_service/cj_core_logic/confidence_calculator.py:59
comparison_confidence = 1.0 / (1.0 + math.exp(-(comparison_count - 5) / 3))
# ↑ Where do 5 and 3 come from? Why does 15 comparisons = 90% confidence?
```

**The user's exact words**:
> "Your numbers still feel handrolled and not based on the statistical calculations needed. We can not say that 15 comparisons must result in 90% contribution? Please create a proper research and code quality review (math quality - not a standard code quality task) task, where we test these assumptions properly using best practice guidance and CJ Assessment frameworks on Github to achieve real data and numbers supported by statistics and the models used."

### Why This Matters

1. **We're building a TUI** for human CJ assessment based on these calculations
2. **Confidence scores** determine when essays can become anchor essays
3. **The Bayesian consensus model** relies on these metrics
4. **Users trust the system** to provide accurate quality indicators
5. **No mathematical justification exists** for the current thresholds

### What You Need to Do

**Validate or replace** every numerical threshold in the confidence calculator using:
- **Statistical theory** (Fisher Information, Cramér-Rao bounds)
- **Empirical validation** (using actual Session 1/2 comparison data)
- **Industry best practices** (GitHub CJ frameworks)
- **Rigorous mathematical proofs** (LaTeX derivations)

---

## Critical Files You MUST Read First

### Before You Write Any Code

**1. Read the task document** (this tells you exactly what to do):
```
.claude/tasks/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md
```

**2. Read the service architecture** (understand the system):
```
.claude/rules/020.7-cj-assessment-service.mdc
```

**3. Read the current implementation** (what needs validation):
```
services/cj_assessment_service/cj_core_logic/confidence_calculator.py
services/cj_assessment_service/cj_core_logic/bt_inference.py
services/cj_assessment_service/cj_core_logic/grade_projector.py
```

**4. Read the Bayesian model** (related but separate system):
```
scripts/bayesian_consensus_model/README.md
scripts/bayesian_consensus_model/models/ordinal_kernel.py
```

**5. Read testing standards** (how to validate):
```
.claude/rules/070-testing-and-quality-assurance.mdc
.claude/rules/090-documentation-standards.mdc
```

**6. Read existing tests** (current validation approach):
```
services/cj_assessment_service/tests/integration/test_bt_scoring_integration.py
```

**7. Find empirical data** (for validation):
```
.claude/research_prompts/RESEARCH_PROMPT_CJ_ANCHOR_PAIRING.md
```
Look for Session 1 results: 12 essays, 58 comparisons → SE 0.12-0.39

---

## Context You Need to Understand

### Two Separate CJ Systems

**IMPORTANT**: There are TWO CJ assessment systems in this codebase:

#### 1. CJ Assessment Service (LLM Judges)
**Location**: `services/cj_assessment_service/`
- **Microservice** for automated essay assessment
- **LLM judges** perform pairwise comparisons
- **Bradley-Terry scoring** via `choix` library
- **Event-driven** architecture (Kafka, PostgreSQL)
- **4-factor confidence** calculator (the one we're validating)

#### 2. Bayesian Consensus Model (Human Judges)
**Location**: `scripts/bayesian_consensus_model/`
- **Standalone scripts** for human rater assessments
- **Human raters** perform pairwise comparisons
- **D-optimal pair generation** (optimizer for comparison schedules)
- **Ordinal kernel smoothing** + Empirical Bayes
- **Used for** creating anchor essays from student work

**Both use Bradley-Terry models**, but in different contexts. **This task validates the confidence calculations that could apply to BOTH**.

### The Confidence Calculator (What Needs Validation)

**Current Implementation** (`confidence_calculator.py:36-115`):

```python
def calculate_confidence(
    bt_score: float,
    comparison_count: int,
    score_distribution: list[float],
    grade_boundaries: dict[str, float],
    has_anchors: bool,
) -> tuple[float, str]:
    """4-factor weighted confidence calculation."""

    # Factor 1: Comparison count (35% weight)
    # Sigmoid: 50% at 5 comparisons, 90% at 15
    comparison_confidence = 1.0 / (1.0 + math.exp(-(comparison_count - 5) / 3))

    # Factor 2: Score distribution (20% weight)
    # Higher batch variance = easier to distinguish
    distribution_confidence = min(score_std / 0.3, 1.0)

    # Factor 3: Boundary distance (35% weight)
    # Max confidence at distance >= 0.15 from grade boundaries
    boundary_confidence = min_distance / 0.15

    # Factor 4: Anchor presence (10% weight)
    anchor_bonus = 0.15 if has_anchors else 0.0

    # Weighted average
    confidence = (
        0.35 * comparison_confidence +
        0.20 * distribution_confidence +
        0.35 * boundary_confidence +
        0.10 * (1.0 if has_anchors else 0.0)
    ) + anchor_bonus
```

**Questions to answer**:
1. Where do **5, 3, 15, 0.3, 0.15** come from?
2. Are the weights **35%, 20%, 35%, 10%** justified?
3. Should we use **Standard Error** instead of comparison count?
4. Should **score stability** (across sessions) be a factor?

### Bradley-Terry Model Background

**From `bt_inference.py`**:

The service uses the `choix` library for Bradley-Terry maximum likelihood estimation:

```python
# Compute BT scores
params = choix.ilsr_pairwise(n_items, comparisons, alpha=0.01)

# Compute Standard Errors via Fisher Information Matrix
se_vec = compute_bt_standard_errors(n_items, comparisons, params)
```

**Theoretical relationship**:
```
SE ∝ 1/sqrt(n_comparisons)
```

**Your job**: Validate if the sigmoid curve matches this relationship.

### Session 1 Empirical Data

**From research prompts**:
- **12 student essays**
- **58 pairwise comparisons** (LLM judges)
- **Result**: SE range 0.12-0.39 (low confidence)
- **Average**: ~4.8 comparisons per essay

**Use this data** to validate theoretical predictions.

---

## What Success Looks Like

### Deliverables

1. **Mathematical Analysis Report**:
   - Location: `.claude/research/CJ-CONFIDENCE-VALIDATION.md`
   - Contents: Theoretical derivations, empirical validation, GitHub comparison
   - Format: Markdown with LaTeX math + Python code

2. **Validation Scripts**:
   - Location: `.claude/research/scripts/validate_cj_confidence.py`
   - Contents: Runnable Python code testing all thresholds
   - Tests: Bootstrap validation, SE curves, accuracy metrics

3. **Clear Recommendation**:
   - **Keep current implementation** (if valid) + add documentation
   - **Revise implementation** (if flawed) + provide corrected formulas with proofs

4. **Framework Comparison**:
   - Analyze 3-5 CJ implementations from GitHub
   - Document how they handle confidence
   - Extract best practices

### Success Criteria

✅ **Every threshold** has mathematical or empirical justification
✅ **Comparison** to at least 3 GitHub CJ frameworks
✅ **Validation** using actual Session 1 data
✅ **Clear recommendation** with statistical evidence
✅ **Runnable code** that tests all claims
✅ **No handrolled numbers** without proof

---

## How to Approach This Task

### Phase 1: Research (Don't Code Yet!)

**Step 1**: Read all required files (listed above)

**Step 2**: Search GitHub for CJ frameworks:
```
"bradley terry" AND "comparative judgment" AND python
"pairwise comparison" AND "confidence"
"choix" AND educational assessment
```

**Step 3**: Review statistical theory:
- Fisher Information Matrix for Bradley-Terry
- Cramér-Rao bound: Var(θ̂) ≥ 1/I(θ)
- Relationship: SE = sqrt(1/I(θ))

**Step 4**: Document what you find in your report

### Phase 2: Theoretical Validation

**Derive** the relationship between n_comparisons and SE:

1. Write Fisher Information formula for Bradley-Terry
2. For connected graph, calculate I(θ) as function of n
3. Compute SE = sqrt(1/I(θ))
4. Check if `1/(1 + exp(-(n-5)/3))` matches

**Use LaTeX** for math, **show your work**.

### Phase 3: Empirical Validation

**Use Session 1 data** (if you can find the CSV files):

```python
# Load actual comparison data
# For each essay: count comparisons, measure SE
# Plot: SE vs n_comparisons
# Fit model: SE ~ a/sqrt(n) + b
# Compare to sigmoid
```

If data not available, **simulate** using `choix`.

### Phase 4: Framework Comparison

**Search GitHub**, analyze 3-5 implementations:
- How do they calculate confidence?
- What thresholds do they use?
- Do they validate their approach?

**Create comparison table**.

### Phase 5: Recommendations

Based on findings:

**If current is valid**:
- Document mathematical justification
- Add unit tests
- Update README

**If current is flawed**:
- Propose corrected formula with proof
- Provide migration plan
- Estimate impact

---

## Important Warnings

### What This Task Is NOT

❌ **NOT a code style review** - Focus on math, not formatting
❌ **NOT about implementation patterns** - Focus on statistical validity
❌ **NOT about adding features** - Focus on validating existing logic

### What This Task IS

✅ **Mathematical quality review** - Every number needs justification
✅ **Statistical validation** - Use theory + empirical data
✅ **Evidence-based recommendations** - No assumptions without proof
✅ **Rigorous analysis** - Show your work with LaTeX + runnable code

### Critical Requirements

1. **Read the required files FIRST** (don't guess the implementation)
2. **Use actual data** (Session 1 results if available)
3. **Compare to frameworks** (GitHub search is mandatory)
4. **Show your math** (LaTeX derivations required)
5. **Test your claims** (provide runnable Python code)
6. **Be rigorous** (every threshold must be justified or rejected)

---

## Specific Thresholds to Validate

### From `confidence_calculator.py`

| Threshold | Current Value | Question |
|-----------|--------------|----------|
| Sigmoid midpoint | 5 comparisons | Why 5? Should it be based on SE threshold? |
| Sigmoid slope | 3 | Why 3? What does this parameter control? |
| "90% confidence" | 15 comparisons | Is this accurate? Does 15 → SE=0.1? |
| Std threshold | 0.3 | Why 0.3? Where does this come from? |
| Boundary dist | 0.15 | Why 0.15? Is this grade-scale dependent? |
| Weights | 35%, 20%, 35%, 10% | Why these? Should they be equal or data-driven? |

**Validate or replace each one.**

### From `bt_inference.py`

```python
def estimate_required_comparisons(
    n_items: int,
    target_se: float = 0.1,
    connectivity: float = 2.0,
) -> int:
    """Heuristic: k*n*log(n) comparisons for SE ≈ 1/sqrt(k*n)"""
    k = (1.0 / target_se) ** 2 / n_items
    estimated = int(k * n_items * np.log(n_items) * connectivity)
    return max(estimated, n_items * connectivity)
```

**This formula claims**: For 24 essays, SE=0.1 requires ~636 comparisons.

**Question**: Is this accurate for CJ assessment? (The user challenged this)

**Your task**: Validate using:
- Theoretical derivation
- Empirical Session 1 data (12 essays, 58 comparisons → SE 0.12-0.39)
- GitHub framework comparison

---

## Integration with Bayesian Model

### Current Gap

**Bayesian Consensus Model** doesn't currently use CJ-style confidence from comparison counts. It uses:
- Rater severity adjustments
- Empirical Bayes shrinkage
- Population priors

**Question**: How should we incorporate **low-confidence CJ priors** (Session 1: SE 0.12-0.39) into the Bayesian framework for human CJ assessment?

**Your task** (in recommendations section):

Propose a framework for:
1. Using LLM CJ results as informative priors for human CJ
2. Weighting priors by confidence (low SE → strong prior, high SE → weak prior)
3. Updating priors as human judgments accumulate

**This is a future enhancement** but should be addressed in your report.

---

## Files You'll Create

```
.claude/research/
├── CJ-CONFIDENCE-VALIDATION.md          # Main report
└── scripts/
    ├── validate_cj_confidence.py        # Validation code
    ├── test_confidence_validation.py    # Unit tests
    └── data/
        ├── se_vs_comparisons.png        # Plots
        ├── sigmoid_validation.png
        └── framework_comparison.png
```

---

## Timeline & Effort

**Estimated**: 11-16 hours total

**Breakdown**:
- Research (literature + GitHub): 4-6 hours
- Mathematical derivation: 3-4 hours
- Empirical validation: 3-4 hours
- Report writing: 1-2 hours

**Don't rush this** - Mathematical rigor is more important than speed.

---

## Questions to Answer in Your Report

### Theoretical Questions

1. What is the theoretical relationship between n_comparisons and SE?
2. Does the sigmoid `1/(1 + exp(-(n-5)/3))` match Fisher Information theory?
3. Should confidence be based on SE instead of comparison count?
4. Are the factor weights (35%, 20%, 35%, 10%) justified?

### Empirical Questions

5. What does Session 1 data (58 comparisons, 12 essays → SE 0.12-0.39) tell us?
6. Does "15 comparisons = 90% confidence" hold empirically?
7. How do SE values actually decay with comparison count?

### Framework Questions

8. How do other CJ implementations calculate confidence?
9. What thresholds do industry leaders (No More Marking, etc.) use?
10. Are there validated best practices we should adopt?

### Integration Questions

11. Should score stability (across sessions) be a confidence factor?
12. How should we incorporate low-confidence CJ priors into Bayesian models?
13. What's the path from current implementation to validated implementation?

---

## Final Checklist Before You Start

- [ ] Read `.claude/tasks/TASK-CJ-CONFIDENCE-MATHEMATICAL-VALIDATION.md`
- [ ] Read `.claude/rules/020.7-cj-assessment-service.mdc`
- [ ] Read `services/cj_assessment_service/cj_core_logic/confidence_calculator.py`
- [ ] Read `services/cj_assessment_service/cj_core_logic/bt_inference.py`
- [ ] Read `scripts/bayesian_consensus_model/README.md`
- [ ] Understand the difference between LLM CJ and Human CJ systems
- [ ] Located Session 1 empirical data (or prepared to simulate)
- [ ] Planned GitHub search strategy
- [ ] Ready to write LaTeX math and Python code

---

## Contact & Support

If you need clarification:
- Review `README.md` for overall project context
- Review `.claude/HANDOFF.md` for the previous handoff
- Check `.claude/README_FIRST.md` for critical issues
- Consult `.claude/rules/` for coding standards
- Search codebase for `SCORE_STABILITY_THRESHOLD` to understand multi-session logic

---

**Remember**: This is a **mathematical quality review**, not a code review. Every number needs a proof or empirical validation. No assumptions. Show your work. Be rigorous.

**Good luck!**

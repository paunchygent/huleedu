---
type: epic
id: EPIC-006
title: Grade Projection Quality & Anchors
status: draft
phase: 1
sprint_target: TBD
created: 2025-11-28
last_updated: 2025-11-28
---

# EPIC-006: Grade Projection Quality & Anchors

## Summary

Ensure grade projection calibration is robust, well-documented, and produces reliable confidence scores under various anchor configurations including edge cases.

**Business Value**: Teachers receive accurate grade projections with clear confidence indicators, even when anchor coverage is imperfect.

**Scope Boundaries**:
- **In Scope**: Anchor calibration semantics, isotonic constraints, degenerate anchor handling, confidence model unification
- **Out of Scope**: Stability/reliability (EPIC-005), developer tooling (EPIC-007)

## User Stories

### US-006.1: Anchor Calibration Semantics & Isotonic Constraints

**As a** teacher
**I want** grade projections to respect anchor grade ordering
**So that** my anchor essays correctly calibrate the grading scale.

**Acceptance Criteria**:
- [ ] For a scale where each grade has ≥ `min_anchors_for_empirical` anchors:
  - `CalibrationEngine.calibrate` uses pure empirical mean and variance per grade
  - Isotonic regression enforces non-decreasing grade centers; tests confirm means are monotone in anchor grade order
- [ ] For grades with `0 < n_anchors < min_anchors_for_empirical`:
  - The mean is a weighted blend of empirical mean and expected position (centered between neighbouring grades)
  - The variance inflates according to `pooled_variance * (min_anchors_for_empirical / n_anchors)`
  - Unit tests check both weighting and variance inflation
- [ ] For grades with `n_anchors == 0`:
  - Calibration logs a warning including `grade` and `correlation_id`
  - Expected-position mean is used and variance is inflated (≥ `2 * pooled_variance`)
  - Tests assert warnings are issued and parameters are sane (variance ≥ 0.01)
- [ ] Grade boundaries `(lower, upper)` are computed as midpoints between adjacent grade means, with first lower bound = `-inf` and last upper bound = `+inf`
- [ ] Docs describe:
  - How calibration uses anchors
  - How isotonic regression may move empirical means to preserve ordering
  - How boundaries are derived from means

**Task**: `TASKS/assessment/cj-us-006-1-anchor-calibration-semantics.md`

---

### US-006.2: Robust Projection Behaviour with Missing or Degenerate Anchors

**As a** teacher
**I want** clear feedback when anchor configuration prevents grade projection
**So that** I understand why projections are unavailable and can take corrective action.

**Acceptance Criteria**:
- [ ] When no anchors are available for the batch:
  - `GradeProjector.calculate_projections` returns `projections_available = False`
  - A structured log entry explains why (no anchors / context source)
  - No `GradeProjection` rows are persisted for that batch
- [ ] When anchors exist but all share the same grade:
  - `GradeProjector.calculate_projections` returns `projections_available = False` with a warning log containing the unique grade set
- [ ] With a normal mixed-anchor scenario:
  - `projections_available = True`
  - `calibration_info` contains:
    - `grade_centers`
    - `grade_boundaries`
    - `anchor_count`
    - `anchor_grades` (set of unique anchor grades)
- [ ] Tests cover all three scenarios:
  - 0 anchors
  - Single-grade anchors
  - Multi-grade anchors
- [ ] Epic doc includes a short table: "anchor patterns → projection behaviour"

**Task**: `TASKS/assessment/cj-us-006-2-degenerate-anchor-handling.md`

---

### US-006.3: Confidence Semantics for Grade Projections

**As a** teacher
**I want** confidence scores that reflect actual uncertainty in grade assignments
**So that** I can prioritize manual review for low-confidence essays.

**Acceptance Criteria**:
- [ ] A single "source of truth" is defined for confidence:
  - Either the entropy-based confidence from `ProjectionEngine`, or
  - The multi-factor `ConfidenceCalculator`
- [ ] Only that source is used to populate `GradeProjection.confidence_score` and `confidence_label`; any unused mechanism is clearly marked deprecated or removed
- [ ] Confidence labels obey these invariants in tests:
  - Essays with many comparisons and BT scores far from boundaries are overwhelmingly `HIGH`
  - Essays near grade boundaries or with few comparisons tend to be `LOW` or `MID`
- [ ] `calculate_batch_confidence_stats` is used to produce per-batch stats (mean, std, counts) for observability, and a test verifies counts match the labels
- [ ] Docs:
  - Describe the factors contributing to confidence
  - Provide guidance for teachers on interpreting HIGH/MID/LOW

**Task**: `TASKS/assessment/cj-us-006-3-confidence-semantics-and-stats.md`

## Technical Architecture

### Data Flows
```
Rankings (BT scores) → GradeProjector
    ↓
_split_and_map_anchors → CalibrationEngine.calibrate
    ↓
[if sufficient unique anchor grades]
    ↓
Isotonic regression → Grade boundaries → ProjectionEngine
    ↓
Per-essay grade probabilities → Confidence calculation → GradeProjection
```

### Key Services
- **CJ Assessment Service**: `services/cj_assessment_service/`
- **Grade Projector**: `services/cj_assessment_service/src/grade_projector.py`
- **Calibration Engine**: `services/cj_assessment_service/src/grade_projection/calibration_engine.py`
- **Projection Engine**: `services/cj_assessment_service/src/grade_projection/projection_engine.py`
- **Confidence Calculator**: `services/cj_assessment_service/src/grade_projection/confidence_calculator.py`

### Configuration Points
- `MIN_ANCHORS_REQUIRED`: Minimum anchor essays for projection
- `min_anchors_for_empirical`: Per-grade threshold for empirical vs blended calibration (default: 3)
- Confidence thresholds: 0.40 (LOW→MID), 0.75 (MID→HIGH)

### Anchor Patterns → Projection Behaviour

| Anchor Configuration | Projection Available | Notes |
|---------------------|---------------------|-------|
| No anchors | No | Log warning, no projections persisted |
| Single grade (all anchors same) | No | Log warning with grade set |
| < 2 unique grades | No | Insufficient calibration points |
| ≥ 2 unique grades, sparse coverage | Yes | Variance inflation for missing grades |
| Full coverage (≥3 per grade) | Yes | Pure empirical calibration |

For batch-level diagnostics, CJ reuses the BT SE metadata from EPIC‑005 and the
merged PR‑4 scoring refactor:

- `bt_se_summary` on `CJBatchState.processing_metadata` captures SE and comparison coverage
  information for the full CJ graph.
- `bt_quality_flags` exposes lightweight batch quality indicators:
  - `bt_se_inflated` – BT SE inflated (high uncertainty)
  - `comparison_coverage_sparse` – sparse comparison coverage (mean comparisons per essay low)
  - `has_isolated_items` – presence of isolated items in the comparison graph

These indicators are intended for ops/analysis dashboards and grade‑projection diagnostics; they
do **not** change when or how batches are finalized or how grades are assigned. BT SE computation
and the `bt_se_summary` structure are provided by `BTScoringResult` /
`compute_bt_scores_and_se(...)` as introduced in PR‑4 (now merged), so EPIC‑006 can treat them as
stable inputs when designing projection quality and confidence semantics.

## RAS / analytics alignment (forward-looking)

- Result Aggregator Service (RAS) remains the authoritative surface for CJ/ENG5 outputs.
- When surfacing batch health in RAS or analytics pipelines, prefer:
  - `bt_se_summary` and `bt_quality_flags` from CJ (or RAS’ copy once threaded) as the canonical
    BT SE diagnostics and comparison coverage indicators.
  - Keep these fields **diagnostic-only** in reporting until EPIC‑006 explicitly defines any
    user-facing semantics.
- Suggested future work (not implemented in this PR):
  - Thread `bt_quality_flags` through the existing CJ→RAS result path for internal dashboards.
  - Add RAS-side reporting views or exports that slice ENG5 runs by `bt_se_inflated`,
    `comparison_coverage_sparse`, and `has_isolated_items` for exam-level QA.

## Related ADRs
- ADR-0015: CJ Assessment Convergence Tuning Strategy (mentions grade projection)

## Dependencies
- BT scoring from CJ workflow
- Anchor essays with known grades

## Notes
- Runbook: `docs/operations/cj-assessment-runbook.md`
- Related to EPIC-004 (core CJ features)
- Grade projections require assignment context (assignment_id, scale)

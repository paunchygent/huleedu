---
id: us-0061-anchor-calibration-semantics-and-isotonic-constraints
title: 'US-006.1: Anchor calibration semantics and isotonic constraints'
type: task
status: proposed
priority: medium
domain: assessment
service: cj_assessment_service
owner_team: agents
owner: ''
program: ''
created: '2025-11-28'
last_updated: '2026-02-01'
related: []
labels: []
---
# US-006.1: Anchor calibration semantics and isotonic constraints

## Objective

Ensure grade projections respect anchor grade ordering through isotonic regression and proper calibration semantics, so anchor essays correctly calibrate the grading scale.

## Context

Part of EPIC-006 (Grade Projection Quality & Anchors). The calibration engine uses isotonic regression to enforce monotonic grade centers, with variance handling for sparse anchor coverage.

## Acceptance Criteria

- [ ] For a scale where each grade has >= `min_anchors_for_empirical` anchors:
  - `CalibrationEngine.calibrate` uses pure empirical mean and variance per grade
  - Isotonic regression enforces non-decreasing grade centers; tests confirm means are monotone in anchor grade order
- [ ] For grades with `0 < n_anchors < min_anchors_for_empirical`:
  - The mean is a weighted blend of empirical mean and expected position (centered between neighbouring grades)
  - The variance inflates according to `pooled_variance * (min_anchors_for_empirical / n_anchors)`
  - Unit tests check both weighting and variance inflation
- [ ] For grades with `n_anchors == 0`:
  - Calibration logs a warning including `grade` and `correlation_id`
  - Expected-position mean is used and variance is inflated (>= `2 * pooled_variance`)
  - Tests assert warnings are issued and parameters are sane (variance >= 0.01)
- [ ] Grade boundaries `(lower, upper)` are computed as midpoints between adjacent grade means, with first lower bound = `-inf` and last upper bound = `+inf`
- [ ] Docs describe:
  - How calibration uses anchors
  - How isotonic regression may move empirical means to preserve ordering
  - How boundaries are derived from means

## Implementation Notes

Key files to modify:
- `services/cj_assessment_service/src/grade_projection/calibration_engine.py`
- `services/cj_assessment_service/src/grade_projection/models.py`

## Related

- Parent epic: [EPIC-006: Grade Projection Quality & Anchors](../../../docs/product/epics/cj-grade-projection-quality.md)
- Related stories: US-006.2 (Degenerate anchor handling), US-006.3 (Confidence semantics)

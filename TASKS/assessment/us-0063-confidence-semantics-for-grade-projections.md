---
id: us-0063-confidence-semantics-for-grade-projections
title: 'US-006.3: Confidence semantics for grade projections'
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
# US-006.3: Confidence semantics for grade projections

## Objective

Ensure confidence scores reflect actual uncertainty in grade assignments, enabling teachers to prioritize manual review for low-confidence essays.

## Context

Part of EPIC-006 (Grade Projection Quality & Anchors). Currently there are two confidence mechanisms: entropy-based (`ProjectionEngine`) and multi-factor (`ConfidenceCalculator`). This story unifies them into a single source of truth.

## Acceptance Criteria

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

## Implementation Notes

Key files to modify:
- `services/cj_assessment_service/src/grade_projection/projection_engine.py`
- `services/cj_assessment_service/src/grade_projection/confidence_calculator.py`
- `services/cj_assessment_service/src/grade_projector.py`

## Related

- Parent epic: [EPIC-006: Grade Projection Quality & Anchors](../../../docs/product/epics/cj-grade-projection-quality.md)
- Related stories: US-006.1 (Anchor calibration), US-006.2 (Degenerate anchor handling)
